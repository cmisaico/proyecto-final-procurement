# Guía de Administrador — Autonomous Procurement Intelligence Platform

**Versión:** 3.0.0  
**Plataforma:** Azure AKS (Fase 5) / Kubernetes local (Fase 4)  
**Fecha:** Junio 2026  
**Audiencia:** Administradores de infraestructura, DevOps, SRE

---

## Tabla de contenido

1. [Arquitectura del sistema](#1-arquitectura-del-sistema)
2. [Acceso administrativo](#2-acceso-administrativo)
3. [Gestión del cluster Kubernetes](#3-gestión-del-cluster-kubernetes)
4. [Gestión de Helm charts](#4-gestión-de-helm-charts)
5. [Pipeline CI/CD — GitHub Actions](#5-pipeline-cicd--github-actions)
6. [Canary Deployments con Argo Rollouts](#6-canary-deployments-con-argo-rollouts)
7. [Autoscaling](#7-autoscaling)
8. [Gestión de secretos — Azure Key Vault](#8-gestión-de-secretos--azure-key-vault)
9. [Observabilidad y alertas](#9-observabilidad-y-alertas)
10. [Seguridad](#10-seguridad)
11. [Backup y Disaster Recovery](#11-backup-y-disaster-recovery)
12. [Tareas administrativas frecuentes](#12-tareas-administrativas-frecuentes)
13. [Troubleshooting avanzado](#13-troubleshooting-avanzado)
14. [Variables de entorno de referencia](#14-variables-de-entorno-de-referencia)

---

## 1. Arquitectura del sistema

### Namespaces Kubernetes

| Namespace | Contenido |
|-----------|-----------|
| `ai-platform` | API Gateway, LangGraph, Embeddings, vLLM/Ollama, Qdrant, OTel Collector |
| `monitoring` | Prometheus, Grafana, Loki, Promtail, kube-state-metrics, DCGM Exporter |
| `ingress-nginx` | NGINX Ingress Controller (Load Balancer público) |
| `argo-rollouts` | Controlador de canary deployments |
| `gpu-operator` | NVIDIA GPU Operator + Device Plugin |
| `velero` | Backups (opcional, ver §11) |

### Node Pools (AKS — Fase 5 dev)

| Pool | SKU | Nodos | Uso |
|------|-----|-------|-----|
| `systempool` | DS2_v2 | 1–3 | Componentes del sistema (Prometheus, Ingress, etc.) |
| `userpool` | D4s_v3 | 1–4 | Workloads de aplicación (API Gateway, LangGraph) |
| `gpupool` | NC4as_T4_v3 | 0–2 | Inferencia LLM (vLLM con Qwen2.5-7B-Instruct-AWQ) |

### Servicios y puertos internos (Fase 4 — K8s local)

| Servicio | Puerto interno | NodePort |
|----------|---------------|----------|
| `api-gateway` | 8000 | 30080 |
| `langgraph` | — (worker, sin HTTP) | — |
| `embeddings` | 8002 | — |
| `ollama` / `vllm` | 11434 / 8000 | — |
| `postgres` | 5432 | — |
| `qdrant` | 6333 | — |
| `minio` | 9000 | — |
| `grafana` | 80 | 30300 |
| `prometheus` | 9090 | — |
| `loki` | 3100 | — |

---

## 2. Acceso administrativo

### Fase 4 — Kubernetes local (WSL2)

```bash
# Verificar contexto activo
kubectl config current-context

# Si el cluster corre en WSL2 con kubeadm en puerto 6444
export KUBECONFIG=/etc/kubernetes/admin.conf   # dentro de WSL2
# o copiar el kubeconfig a ~/.kube/config
```

### Fase 5 — AKS

```bash
# Cargar variables de entorno
source ~/.procurement_env

# Obtener credenciales del cluster
az aks get-credentials \
  --resource-group $RG_NAME \
  --name $AKS_NAME \
  --overwrite-existing

# Verificar acceso
kubectl get nodes
kubectl get pods -n ai-platform
```

### Comandos desde fuera del cluster (az aks command invoke)

Para ejecutar comandos sin kubeconfig local:

```bash
az aks command invoke \
  --resource-group $RG_NAME \
  --name $AKS_NAME \
  --command "kubectl get pods -n ai-platform"
```

---

## 3. Gestión del cluster Kubernetes

### Verificar estado general

```bash
# Estado de todos los nodos
kubectl get nodes -o wide

# Pods por namespace
kubectl get pods -n ai-platform
kubectl get pods -n monitoring
kubectl get pods -n ingress-nginx
kubectl get pods -n argo-rollouts

# Uso de recursos por nodo
kubectl top nodes

# Uso de recursos por pod
kubectl top pods -n ai-platform
```

### Estado de node pools (AKS)

```bash
az aks nodepool list \
  --resource-group $RG_NAME \
  --cluster-name $AKS_NAME \
  --query "[].{name:name, count:count, min:minCount, max:maxCount, state:provisioningState}" \
  -o table
```

### Forzar un nodo a entrar/salir de servicio

```bash
# Cordon — impide que se agenden nuevos pods en el nodo
kubectl cordon <nombre-nodo>

# Drain — evacua pods del nodo antes de mantenimiento
kubectl drain <nombre-nodo> --ignore-daemonsets --delete-emptydir-data

# Uncordon — devolver el nodo al pool activo
kubectl uncordon <nombre-nodo>
```

### Reiniciar un deployment

```bash
kubectl rollout restart deployment/<nombre> -n ai-platform

# Ejemplos
kubectl rollout restart deployment/api-gateway -n ai-platform
kubectl rollout restart deployment/langgraph -n ai-platform
```

### Ver logs de un servicio

```bash
# Últimas 100 líneas
kubectl logs -n ai-platform deployment/api-gateway --tail=100

# Seguimiento en tiempo real
kubectl logs -n ai-platform deployment/api-gateway -f

# Pod específico (si hay múltiples réplicas)
kubectl logs -n ai-platform <pod-name> -f
```

---

## 4. Gestión de Helm charts

### Estructura de charts del proyecto

```
k8s/charts/
├── api-gateway/        ← FastAPI backend + HPA + ServiceMonitor
├── langgraph/          ← LangGraph worker
├── embeddings/         ← Sentence-transformers service
├── postgres/           ← PostgreSQL (solo Fase 4 local)
├── vllm/               ← vLLM inference server (AKS)
├── ollama/             ← Ollama inference (local)
├── qdrant/             ← Vector store
├── minio/              ← Object storage (solo Fase 4 local)
└── monitoring/         ← kube-prometheus-stack + loki-stack + dashboards

k8s/azure/              ← Overrides de values para AKS (Fase 5)
k8s/manifests/          ← Recursos adicionales (Rollout, VPA, AnalysisTemplate)
```

### Verificar releases instalados

```bash
helm list -n ai-platform
helm list -n monitoring
helm list -n ingress-nginx
```

### Actualizar un chart

```bash
# api-gateway con values de AKS
helm upgrade api-gateway k8s/charts/api-gateway \
  -n ai-platform \
  -f k8s/azure/api-gateway.yaml \
  --wait --timeout 3m

# Monitoring stack
helm upgrade monitoring k8s/charts/monitoring \
  -n monitoring \
  --wait --timeout 5m
```

### Ver historial de un release

```bash
helm history api-gateway -n ai-platform
```

### Rollback de Helm

```bash
# Rollback a la revisión anterior
helm rollback api-gateway -n ai-platform

# Rollback a una revisión específica
helm rollback api-gateway 3 -n ai-platform
```

### Ver los values efectivos de un release

```bash
helm get values api-gateway -n ai-platform
```

---

## 5. Pipeline CI/CD — GitHub Actions

### Archivo: `.github/workflows/deploy.yml`

### Secrets requeridos en GitHub

| Secret | Descripción |
|--------|-------------|
| `AZURE_CLIENT_ID` | Client ID del Service Principal |
| `AZURE_CLIENT_SECRET` | Contraseña del Service Principal |
| `AZURE_TENANT_ID` | Tenant ID de Azure AD |
| `AZURE_SUBSCRIPTION_ID` | ID de la suscripción Azure |
| `ACR_NAME` | Nombre del Azure Container Registry (sin `.azurecr.io`) |
| `AKS_NAME` | Nombre del cluster AKS |
| `AKS_RESOURCE_GROUP` | Resource group donde vive el AKS |

Configurar en: `GitHub repo → Settings → Secrets and variables → Actions`

### Flujo del pipeline

```
push a main
    │
    ├─[Job 1]─ build-and-test ──────────────────────────────────────────────────
    │           ├─ Azure Login + ACR Login
    │           ├─ Install Python dependencies
    │           ├─ Run pytest (continue-on-error: true)
    │           ├─ docker build (sin push) + guarda imagen como artifact
    │           └─ Upload artifact
    │
    ├─[Job 1b]─ build-frontend ─────────────────────────────────────────────────
    │            └─ docker build + push frontend a ACR (si es main)
    │
    ├─[Job 2]─ security-scan (necesita: build-and-test) ────────────────────────
    │           └─ Trivy scan — CRITICAL/HIGH (exit-code: 0, no bloquea)
    │
    ├─[Job 3]─ push-to-acr (necesita: build-and-test + security-scan) ──────────
    │           └─ Push imagen con SHA y :latest a ACR
    │
    ├─[Job 4]─ deploy (necesita: push-to-acr + build-frontend) ─────────────────
    │           ├─ GPU Operator (helm upgrade)
    │           ├─ Frontend (kubectl apply)
    │           ├─ API Gateway Helm chart (helm upgrade)
    │           ├─ Canary deployment (argo rollouts set image)
    │           ├─ Smoke tests (curl /health → HTTP 200)
    │           ├─ K6 load tests (error rate < 5%)
    │           └─ Promote canary a 100%
    │
    └─[Job 5]─ rollback (si deploy falla) ──────────────────────────────────────
                └─ kubectl argo rollouts undo api-gateway
```

### Triggerar el pipeline manualmente

```bash
# Desde CLI con GitHub CLI
gh workflow run deploy.yml --ref main

# O hacer un push vacío
git commit --allow-empty -m "trigger deploy"
git push origin main
```

### Ver estado del pipeline

```bash
gh run list --workflow=deploy.yml --limit 5
gh run view <run-id> --log
```

---

## 6. Canary Deployments con Argo Rollouts

### Verificar estado del Rollout

```bash
kubectl argo rollouts get rollout api-gateway -n ai-platform
kubectl argo rollouts status api-gateway -n ai-platform
```

### Actualizar imagen manualmente (sin CI/CD)

```bash
kubectl argo rollouts set image api-gateway \
  api-gateway=<ACR_NAME>.azurecr.io/procurement-api:<nuevo-tag> \
  -n ai-platform
```

### Promover canary manualmente

```bash
# Promover al siguiente paso del canary
kubectl argo rollouts promote api-gateway -n ai-platform

# Promover directamente al 100% (saltarse los pasos)
kubectl argo rollouts promote api-gateway -n ai-platform --full
```

### Abortar un canary

```bash
kubectl argo rollouts abort api-gateway -n ai-platform
```

### Rollback a la revisión anterior

```bash
kubectl argo rollouts undo api-gateway -n ai-platform
```

### Estrategia de canary configurada

La estrategia está definida en `k8s/manifests/api-gateway-rollout.yaml`:

- **Paso 1:** 20% del tráfico al canary
- **Pause:** espera análisis automático (success-rate desde Prometheus)
- **Paso 2:** 50% si el análisis es exitoso
- **Paso 3:** 100% (promote completo)
- **Abort automático:** si error rate > 5% o el smoke test falla

---

## 7. Autoscaling

### HPA (Horizontal Pod Autoscaler)

```bash
# Ver HPAs activos
kubectl get hpa -n ai-platform

# Descripción detallada (incluye eventos de escalado)
kubectl describe hpa api-gateway -n ai-platform
```

Configuración actual del `api-gateway`:
- `minReplicas: 2`, `maxReplicas: 8`
- `targetCPUUtilizationPercentage: 70`

Para modificar sin tocar el chart, editar `k8s/azure/api-gateway.yaml`:

```yaml
hpa:
  enabled: true
  minReplicas: 2
  maxReplicas: 10        # aumentar si se necesita mayor capacidad
  targetCPUUtilizationPercentage: 65
```

Luego aplicar:
```bash
helm upgrade api-gateway k8s/charts/api-gateway \
  -n ai-platform -f k8s/azure/api-gateway.yaml
```

### Cluster Autoscaler (AKS)

El autoscaler está gestionado por AKS. Ver actividad:

```bash
# Eventos de scale-up
kubectl get events -A \
  --field-selector reason=TriggeredScaleUp \
  --sort-by='.lastTimestamp'

# Estado del autoscaler
kubectl get configmap cluster-autoscaler-status -n kube-system -o yaml
```

Modificar límites del GPU pool:

```bash
az aks nodepool update \
  --resource-group $RG_NAME \
  --cluster-name $AKS_NAME \
  --name gpupool \
  --enable-cluster-autoscaler \
  --min-count 0 \
  --max-count 3     # aumentar si se necesita más capacidad GPU
```

### VPA (Vertical Pod Autoscaler) — modo observación

```bash
# Ver recomendaciones (no aplica automáticamente en modo Off/Recreate para Qdrant)
kubectl describe vpa -n ai-platform
```

---

## 8. Gestión de secretos — Azure Key Vault

### Secretos almacenados en Key Vault

| Secret | Descripción |
|--------|-------------|
| `postgres-password` | Contraseña de la base de datos |
| `qdrant-api-key` | API key de Qdrant (si está habilitada) |
| `minio-access-key` | Access key de MinIO/Blob |
| `minio-secret-key` | Secret key de MinIO/Blob |

### Verificar que los secretos están montados en los pods

```bash
# Los secretos se montan vía CSI Driver como volúmenes
kubectl get secretproviderclass -n ai-platform
kubectl describe pod <api-gateway-pod> -n ai-platform | grep -A5 "Volumes"
```

### Rotar un secreto

```bash
# 1. Actualizar el valor en Key Vault
az keyvault secret set \
  --vault-name $KV_NAME \
  --name postgres-password \
  --value "<nueva-contraseña>"

# 2. Reiniciar los pods que montan ese secreto (el CSI Driver recarga al reiniciar)
kubectl rollout restart deployment/api-gateway -n ai-platform
```

### Crear un nuevo secreto en Key Vault

```bash
az keyvault secret set \
  --vault-name $KV_NAME \
  --name <nombre-secreto> \
  --value "<valor>"
```

---

## 9. Observabilidad y alertas

### Acceso a Grafana

**Fase 4 (local):**
```
URL: http://172.19.137.191:30300
User: admin
Password: procurement123
```

**Fase 5 (AKS):**
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
# URL: http://localhost:3000  |  admin / admin123
```

### Dashboards disponibles

| Dashboard | Carpeta Grafana | Métricas clave |
|-----------|-----------------|----------------|
| LLM & RAG | AI Procurement Platform | Tokens/s, latencia P50/P90/P99 LLM |
| Platform API | AI Procurement Platform | Req/s, HTTP latencia, error rate |
| GPU & Infrastructure | AI Procurement Platform | GPU util, VRAM%, temperatura |
| Agents | AI Procurement Platform | Workflow runs, éxito/fallo por agente |

### Prometheus — queries útiles

Acceder via port-forward:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
```

Queries frecuentes:

```promql
# Throughput actual de la API (req/s)
sum(rate(procurement_http_requests_total[5m]))

# Latencia P99 de la API
histogram_quantile(0.99, sum(rate(procurement_http_request_duration_seconds_bucket[5m])) by (le))

# Tokens por segundo del LLM
max(procurement_llm_tokens_per_second)

# GPU utilization
DCGM_FI_DEV_GPU_UTIL

# Pods reiniciados en los últimos 15 min
rate(kube_pod_container_status_restarts_total{namespace="ai-platform"}[15m]) > 0
```

### Alertas configuradas (PrometheusRules)

| Alerta | Condición | Severidad |
|--------|-----------|-----------|
| `GPUThrottling` | GPU util > 95% por 5 min | critical |
| `APIHighLatency` | P99 latencia > 800ms por 2 min | warning |
| `PodCrashLooping` | Reinicios de pod en ai-platform | critical |

Ver estado de alertas:
```bash
kubectl get prometheusrule -n monitoring
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093
# Abrir: http://localhost:9093
```

### Loki — consultar logs

En Grafana, ir a **Explore** → datasource **Loki**:

```logql
# Logs del api-gateway (todos)
{namespace="ai-platform", app="api-gateway"}

# Solo errores
{namespace="ai-platform", app="api-gateway"} |= "ERROR"

# Logs de un workflow específico
{namespace="ai-platform"} |= "correlation_id=<uuid>"

# Logs de inferencia LLM
{namespace="ai-platform", app="langgraph"} |= "tokens"
```

### ServiceMonitors activos

```bash
kubectl get servicemonitor -n monitoring
kubectl get servicemonitor -n ai-platform
```

Si un dashboard aparece sin datos, verificar que el ServiceMonitor correspondiente existe y que Prometheus tiene el target activo en `http://localhost:9090/targets`.

---

## 10. Seguridad

### Pod Security Standards

Los namespaces están etiquetados con el nivel de seguridad apropiado:

| Namespace | enforce | warn |
|-----------|---------|------|
| `ai-platform` | baseline | restricted |
| `monitoring` | baseline | — |
| `gpu-operator` | privileged | — |

Verificar etiquetas:
```bash
kubectl get ns ai-platform monitoring gpu-operator \
  -o custom-columns='NS:.metadata.name,ENFORCE:.metadata.labels.pod-security\.kubernetes\.io/enforce,WARN:.metadata.labels.pod-security\.kubernetes\.io/warn'
```

Aplicar o actualizar etiquetas:
```bash
kubectl label namespace ai-platform \
  pod-security.kubernetes.io/enforce=baseline \
  pod-security.kubernetes.io/warn=restricted \
  --overwrite
```

### Escaneo de vulnerabilidades con Trivy

El pipeline CI/CD ejecuta Trivy automáticamente en cada push. Para ejecutar manualmente:

```bash
# Escanear imagen local
docker pull <ACR_NAME>.azurecr.io/procurement-api:latest
trivy image \
  --severity CRITICAL,HIGH \
  <ACR_NAME>.azurecr.io/procurement-api:latest

# Escanear imágenes en el ACR
az acr repository list --name $ACR_NAME -o tsv | while read repo; do
  echo "=== Escaneando $repo ==="
  trivy image --severity CRITICAL,HIGH \
    $ACR_NAME.azurecr.io/$repo:latest 2>/dev/null || true
done
```

### Network Policies (si están habilitadas)

```bash
# Ver políticas activas
kubectl get networkpolicies -n ai-platform

# Verificar que no hay pods privilegiados
kubectl get pods -n ai-platform -o jsonpath='{range .items[*]}{.metadata.name}: {.spec.containers[*].securityContext.privileged}{"\n"}{end}'
```

### RBAC — Roles y permisos

```bash
# Ver ClusterRoleBindings relevantes
kubectl get clusterrolebindings | grep procurement

# Ver permisos de un ServiceAccount
kubectl auth can-i --list --as=system:serviceaccount:ai-platform:api-gateway
```

---

## 11. Backup y Disaster Recovery

### Objetivos RPO/RTO

| Componente | RPO | RTO | Estrategia |
|------------|-----|-----|-----------|
| PostgreSQL | 15 min | 30 min | Azure backups automáticos + PITR |
| Qdrant | 1 hora | 2 horas | Velero snapshot |
| Config K8s | 24 horas | 1 hora | Velero daily |
| Blob Storage | 24 horas | 30 min | Azure LRS |
| Aplicación | N/A | 15 min | Multi-replica + GitOps |

### Velero — gestión de backups

```bash
# Ver backups disponibles
velero backup get

# Crear backup manual
velero backup create manual-$(date +%Y%m%d) \
  --include-namespaces ai-platform,monitoring \
  --snapshot-volumes \
  --storage-location azure-default \
  --wait

# Ver schedules activos
velero schedule get
```

Schedules configurados:
- `daily-ai-platform` — diario a las 02:00 UTC, retención 30 días
- `config-backup-6h` — cada 6 horas (solo config, sin PVs), retención 7 días

### Restore con Velero

```bash
# Listar backups disponibles
velero backup get

# Restore completo de un namespace
velero restore create \
  --from-backup daily-ai-platform-<TIMESTAMP> \
  --include-namespaces ai-platform \
  --restore-volumes true \
  --wait

# Restore de un recurso específico
velero restore create \
  --from-backup daily-ai-platform-<TIMESTAMP> \
  --include-namespaces ai-platform \
  --include-resources deployments \
  --selector app=api-gateway
```

### PostgreSQL — backup y restore (Azure)

```bash
# Ver backups disponibles
az postgres flexible-server backup list \
  --resource-group $RG_NAME \
  --name $PSQL_NAME \
  --output table

# Point-in-Time Restore a un nuevo servidor
az postgres flexible-server restore \
  --resource-group $RG_NAME \
  --name "${PSQL_NAME}-restored" \
  --source-server $PSQL_NAME \
  --restore-time "2026-06-01T02:00:00Z"
```

---

## 12. Tareas administrativas frecuentes

### Actualizar la imagen del API Gateway

```bash
# Via CI/CD (recomendado): push a main en GitHub
git push origin main

# Manual (sin CI/CD)
kubectl argo rollouts set image api-gateway \
  api-gateway=<ACR_NAME>.azurecr.io/procurement-api:<nuevo-sha> \
  -n ai-platform

kubectl argo rollouts promote api-gateway -n ai-platform --full
```

### Escalar manualmente un deployment

```bash
# Escalar a 4 réplicas (HPA retomará el control después)
kubectl scale deployment/api-gateway --replicas=4 -n ai-platform
```

### Aplicar una migración de base de datos

```bash
# Conectarse al pod de postgres
kubectl exec -it -n ai-platform deployment/postgres -- psql -U procurement -d procurement_db

# O aplicar un script SQL
kubectl exec -i -n ai-platform deployment/postgres -- \
  psql -U procurement -d procurement_db < scripts/nueva_migration.sql
```

### Actualizar la contraseña de Grafana

```bash
# Fase 4 — editar el values.yaml del chart de monitoring
# Fase 5 — actualizar el secret de Kubernetes
kubectl create secret generic kube-prometheus-stack-grafana \
  --from-literal=admin-password=<nueva-contraseña> \
  -n monitoring \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/kube-prometheus-stack-grafana -n monitoring
```

### Verificar que el GPU pool tiene nodos activos

```bash
kubectl get nodes --show-labels | grep gpu

# Ver si vLLM tiene el modelo cargado
kubectl logs -n ai-platform deployment/vllm --tail=50 | grep -E "loaded|model|error"
```

### Activar/desactivar el GPU pool (para ahorrar costos)

```bash
# Escalar a 0 nodos GPU (vLLM quedará en Pending)
az aks nodepool scale \
  --resource-group $RG_NAME \
  --cluster-name $AKS_NAME \
  --name gpupool \
  --node-count 0

# Volver a activar
az aks nodepool scale \
  --resource-group $RG_NAME \
  --cluster-name $AKS_NAME \
  --name gpupool \
  --node-count 1
```

> El nodo T4 tarda ~5-10 minutos en estar disponible y ~15 min adicionales para que vLLM cargue el modelo AWQ.

### Verificar y limpiar imágenes huérfanas en ACR

```bash
# Listar tags del repositorio principal
az acr repository show-tags \
  --name $ACR_NAME \
  --repository procurement-api \
  --orderby time_desc \
  --output table

# Eliminar tags antiguos (mantener los últimos 5)
az acr repository delete \
  --name $ACR_NAME \
  --image procurement-api:<tag-a-eliminar> \
  --yes
```

---

## 13. Troubleshooting avanzado

### Pod en estado `Pending`

```bash
# Ver por qué no se agenda
kubectl describe pod <pod-name> -n ai-platform | grep -A20 Events

# Causas frecuentes:
# - "Insufficient cpu/memory" → HPA no tiene nodos disponibles, revisar Cluster Autoscaler
# - "no nodes available for GPU" → GPU pool en 0 nodos, escalar gpupool
# - "pod has unbound immediate PersistentVolumeClaims" → PVC sin provisionar
```

### Pod en estado `CrashLoopBackOff`

```bash
# Ver logs del crash anterior
kubectl logs -n ai-platform <pod-name> --previous

# Ver eventos
kubectl describe pod <pod-name> -n ai-platform
```

### vLLM no responde / inferencia muy lenta

```bash
# Verificar que el GPU está visible
kubectl exec -n ai-platform deployment/vllm -- nvidia-smi

# Ver uso de VRAM
kubectl exec -n ai-platform deployment/vllm -- nvidia-smi --query-gpu=memory.used,memory.total --format=csv

# Logs de inicio del modelo
kubectl logs -n ai-platform deployment/vllm --tail=100 | grep -E "model|cuda|error|warning"
```

Si VRAM está al límite:
- El modelo AWQ (~4.2 GB) requiere T4 con 16 GB VRAM
- Si hay otro proceso ocupando VRAM, reiniciar el nodo GPU: `kubectl drain <gpu-node> && kubectl uncordon <gpu-node>`

### Prometheus no scrapea métricas de la aplicación

```bash
# Verificar ServiceMonitors existentes
kubectl get servicemonitor -A | grep api-gateway

# Verificar que el pod expone /metrics
kubectl exec -n ai-platform deployment/api-gateway -- curl -s localhost:8000/api/v1/metrics | head -20

# Verificar que Prometheus tiene el target activo
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# Ir a: http://localhost:9090/targets → buscar "api-gateway"
```

### Canary deployment atascado

```bash
# Ver estado detallado
kubectl argo rollouts get rollout api-gateway -n ai-platform --watch

# Si está en Paused esperando análisis y quieres forzar la promoción
kubectl argo rollouts promote api-gateway -n ai-platform

# Si el AnalysisRun falló por razones de infraestructura (no de la app)
kubectl argo rollouts abort api-gateway -n ai-platform
kubectl argo rollouts undo api-gateway -n ai-platform
# Luego corregir el problema y volver a hacer push
```

### Loki no recibe logs de un servicio

```bash
# Verificar que Promtail está corriendo en el nodo del pod
kubectl get pods -n monitoring | grep promtail

# Ver si Promtail tiene errores
kubectl logs -n monitoring daemonset/loki-stack-promtail --tail=50

# Verificar que el pod tiene labels correctos (app=<nombre>)
kubectl get pod <pod-name> -n ai-platform --show-labels
```

### Ingress no llega a los pods

```bash
# Ver estado del Ingress Controller
kubectl get pods -n ingress-nginx
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller --tail=50

# Ver IP del Load Balancer (AKS)
kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Ver reglas de Ingress
kubectl get ingress -n ai-platform
kubectl describe ingress -n ai-platform
```

---

## 14. Variables de entorno de referencia

Estas variables deben estar configuradas antes de ejecutar comandos de administración en Fase 5.  
Guardar en `~/.procurement_env` y ejecutar `source ~/.procurement_env`:

```bash
export AZURE_SUBSCRIPTION_ID="<id>"
export AZURE_TENANT_ID="<id>"

export PROJECT="procurement"
export ENVIRONMENT="dev"
export LOCATION="brazilsouth"

export RG_NAME="rg-${PROJECT}-${ENVIRONMENT}"
export RG_MONITORING_NAME="rg-${PROJECT}-monitoring-${ENVIRONMENT}"
export AKS_NAME="aks-${PROJECT}-${ENVIRONMENT}"
export ACR_NAME="acr${PROJECT}${ENVIRONMENT}"
export KV_NAME="kv-${PROJECT}-az-${ENVIRONMENT}"
export PSQL_NAME="psql-${PROJECT}-${ENVIRONMENT}"
export STORAGE_NAME="st${PROJECT}${ENVIRONMENT}"
export LAW_NAME="law-${PROJECT}-${ENVIRONMENT}"
export GRAFANA_NAME="graf-${PROJECT}-${ENVIRONMENT}"

export K8S_VERSION="1.33.0"
export NAMESPACE="ai-platform"

export GPU_NODE_SKU="Standard_NC4as_T4_v3"
export VLLM_MODEL="Qwen/Qwen2.5-7B-Instruct-AWQ"
```

---

## Apéndice — Checklist de deployment post-cambio

Después de cada deployment significativo, verificar:

```bash
# 1. Todos los pods Running
kubectl get pods -n ai-platform

# 2. Health check de la API
curl -s http://<INGRESS_IP>/api/v1/health | jq .

# 3. Readiness probe (todos los servicios ok)
curl -s http://<INGRESS_IP>/api/v1/ready | jq .

# 4. Rollout completado (no en canary parcial)
kubectl argo rollouts get rollout api-gateway -n ai-platform

# 5. Sin alertas activas en Prometheus
curl -s http://localhost:9093/api/v1/alerts | jq '[.data[] | .labels.alertname]'

# 6. HPAs sin saturación
kubectl get hpa -n ai-platform

# 7. Últimos errores en logs (últimos 5 min)
kubectl logs -n ai-platform deployment/api-gateway --since=5m | grep -i error
```
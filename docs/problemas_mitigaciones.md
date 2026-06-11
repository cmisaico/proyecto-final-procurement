# Problemas Encontrados y Mitigaciones

**Proyecto:** Autonomous Procurement Intelligence Platform  
**Fecha:** Junio 2026

---

## Categorías

1. [GPU / Inferencia LLM](#1-gpu--inferencia-llm)
2. [Kubernetes / Helm](#2-kubernetes--helm)
3. [Base de datos / ORM](#3-base-de-datos--orm)
4. [Observabilidad](#4-observabilidad)
5. [CI/CD](#5-cicd)
6. [Networking](#6-networking)
7. [Azure / Cloud](#7-azure--cloud)

---

## 1. GPU / Inferencia LLM

### P-01: vLLM no soporta RTX 5080 (Blackwell sm_120)

**Síntoma:** `vLLM` lanzaba `CUDA error: no kernel image available for execution on the device` al intentar cargar el modelo en el RTX 5080.

**Causa:** La RTX 5080 usa arquitectura Blackwell (sm_120). La imagen vLLM publicada incluía PyTorch compilado para CUDA 12.1/12.4, que no tiene kernels para sm_120.

**Mitigación:** Reemplazar vLLM por **Ollama** en el ambiente local (Fase 4). Ollama usa CUDA 12.0+ con soporte nativo para Blackwell. En producción (AKS) se usa vLLM en T4 (Ampere sm_75), que sí es soportado.

**Impacto:** Ninguno en funcionalidad. Ollama expone la misma API OpenAI-compatible que vLLM. El código del API Gateway no requirió cambios (`VLLM_BASE_URL` apunta a Ollama localmente).

**Archivos afectados:** `app/core/config.py` → `VLLM_BASE_URL`, memoria del proyecto.

---

### P-02: Modelo FP16 (Qwen2.5-7B) no cabe en T4 de 16 GB

**Síntoma:** vLLM en AKS crasheaba con `CUDA out of memory` al cargar el modelo FP16.

**Causa:** Qwen2.5-7B en FP16 ocupa ~14.5 GB de VRAM. Con el overhead del KV cache y el runtime de vLLM, excede los 16 GB disponibles en el T4.

**Mitigación:** Usar cuantización **AWQ 4-bit** (`Qwen/Qwen2.5-7B-Instruct-AWQ`), que ocupa ~4.2 GB de VRAM, dejando ~11.8 GB para KV cache.

**Impacto en calidad:** -2 a -5% en benchmarks de calidad de respuesta (MMLU, MT-Bench) según estudios de AWQ. Para el caso de uso de licitaciones (texto en español, estructura bien definida), la degradación es imperceptible.

**Archivos afectados:** `k8s/charts/vllm/values.yaml`, `docker/vllm/Dockerfile`, `docs/fase05_manual/22-quantization.md`.

---

### P-03: vLLM se cuelga al descargar modelo sin PVC persistente

**Síntoma:** Al reiniciar el pod de vLLM, tardaba ~20 min en estar disponible (descarga del modelo desde HuggingFace Hub en cada reinicio).

**Causa:** Sin un PersistentVolumeClaim, el modelo (~4.2 GB) se descargaba en el directorio temporal del contenedor, que se perdía al reiniciar el pod.

**Mitigación:** Configurar `persistence.enabled=true` en el Helm chart de vLLM, montando un PVC de 20 GB en `/data/cache` (path configurado en `HF_HOME`). Con el modelo cacheado, el tiempo de arranque baja de ~20 min a ~2-3 min.

**Archivos afectados:** `k8s/charts/vllm/values.yaml`, `docker/vllm/Dockerfile`.

---

## 2. Kubernetes / Helm

### P-04: kubeadm en WSL2 — conflicto de puerto 6443

**Síntoma:** `kubectl get pods` devolvía `connection refused` al intentar conectar al API server en el puerto 6443.

**Causa:** Docker Desktop ya ocupa el puerto 6443 en WSL2 para su propio API server de Kubernetes.

**Mitigación:** Configurar kubeadm para exponer el API server en el puerto **6444** con `--apiserver-bind-port=6444`. Actualizar el kubeconfig con el puerto correcto.

**Archivos afectados:** `/etc/kubernetes/admin.conf` dentro de WSL2.

---

### P-05: node-exporter falla en WSL2

**Síntoma:** El pod `node-exporter` crasheaba con `mountinfo: no mount found at "/"` en el namespace de monitoring.

**Causa:** WSL2 no monta "/" como un shared mount, que es un requisito del node-exporter para leer métricas del sistema de archivos del host.

**Mitigación:** Deshabilitar node-exporter en el values.yaml del chart de monitoring (`nodeExporter.enabled: false`). Las métricas de nodos se obtienen via `kube-state-metrics` que no tiene esta limitación.

**Archivos afectados:** `k8s/charts/monitoring/values.yaml`.

---

### P-06: `az aks command invoke --file` no aplica el YAML correctamente

**Síntoma:** El comando reportaba `Operation returned an invalid status 'OK'` y el recurso no se creaba en el cluster.

**Causa:** Bug conocido de `az aks command invoke` con el flag `--file` en ciertas versiones del Azure CLI. El comando termina con status 'OK' pero no aplica el contenido.

**Mitigación:** Usar `kubectl apply` directamente desde WSL2 con las credenciales del cluster obtenidas via `az aks get-credentials`, sin pasar por `az aks command invoke`. Para manifiestos inline, usar heredoc dentro del `--command`.

**Archivos afectados:** Ninguno en el código. Documentado en `docs/fase05_manual/12-canary-rollouts.md` §12.3.

---

### P-07: Loki necesita montar en `/loki`, no en `/tmp/loki`

**Síntoma:** El pod de Loki crasheaba con `permission denied` al intentar escribir en el directorio de datos.

**Causa:** La configuración por defecto de Loki montaba el PVC en `/tmp/loki`, que en algunas versiones de la imagen tenía permisos de solo lectura para el usuario no-root.

**Mitigación:** Cambiar el mount path del PVC de `/tmp/loki` a `/loki` en la configuración de Loki. Este path tiene permisos correctos en la imagen oficial.

**Archivos afectados:** `k8s/charts/monitoring/values.yaml` (loki-stack sub-chart, `persistence.mountPath`).

---

### P-08: AnalysisTemplate con métrica de latencia causa falsos abort

**Síntoma:** El canary deployment abortaba automáticamente durante el análisis porque la métrica de latencia P95 superaba el threshold configurado (800 ms).

**Causa:** Para una API LLM con inferencia RAG, el P95 puede superar cualquier threshold fijo razonable, especialmente bajo carga moderada (~2,000-5,000 ms). El threshold de 800 ms era diseñado para APIs REST sin LLM.

**Mitigación:** Eliminar la métrica de latencia del `AnalysisTemplate` y conservar únicamente `success-rate` (error rate < 5%). La latencia se monitorea vía Grafana/Prometheus pero no bloquea el canary.

**Archivos afectados:** `k8s/manifests/analysis-template.yaml`.

---

## 3. Base de datos / ORM

### P-09: Enums PostgreSQL con SQLAlchemy — error en migración

**Síntoma:** Al aplicar la migración `fase02_migration.sql`, SQLAlchemy lanzaba `DuplicateObject: type "documentstatus" already exists`.

**Causa:** SQLAlchemy intentaba crear los tipos ENUM de PostgreSQL (`DocumentStatus`, `WorkflowStatus`, etc.) que ya habían sido creados por `init_db.sql`.

**Mitigación:** Agregar `create_type=False` a la declaración de los tipos Enum en los modelos SQLAlchemy:
```python
status = Column(Enum(DocumentStatus, create_type=False))
```

**Archivos afectados:** `app/infrastructure/database/models.py`, `app/infrastructure/database/models_fase02.py`.

---

### P-10: `_to_entity()` falla si el campo status viene como string

**Síntoma:** `AttributeError: 'str' object has no attribute 'value'` al leer registros de PostgreSQL.

**Causa:** En algunos casos, SQLAlchemy devuelve el valor del campo ENUM como string en lugar del objeto Enum Python, dependiendo de la versión del driver asyncpg y el estado de la caché de tipos.

**Mitigación:** Agregar un check `isinstance(m.status, str)` en el método `_to_entity()` de cada repositorio:
```python
status = DocumentStatus(m.status) if isinstance(m.status, str) else m.status
```

**Archivos afectados:** `app/infrastructure/repositories/pg_document_repository.py`, `pg_workflow_repository.py`.

---

## 4. Observabilidad

### P-11: OTel Collector v0.100+ rompe la configuración de métricas

**Síntoma:** El pod de OTel Collector crasheaba con `invalid configuration: service::telemetry::metrics requires readers format`.

**Causa:** A partir de la versión 0.100 del OTel Collector, el formato de configuración del exporter de métricas cambió. La clave `address:` fue reemplazada por el formato `readers: [{pull: {exporter: {prometheus: {host, port}}}}]`.

**Mitigación:** Actualizar la configuración del OTel Collector al nuevo formato:
```yaml
service:
  telemetry:
    metrics:
      readers:
        - pull:
            exporter:
              prometheus:
                host: 0.0.0.0
                port: 8888
```

**Archivos afectados:** `observability/otel/otel-collector-config.yml`.

---

### P-12: Paquete `opentelemetry-sdk==1.28.4` no existe

**Síntoma:** `pip install` fallaba con `ERROR: Could not find a version that satisfies the requirement opentelemetry-sdk==1.28.4`.

**Causa:** La versión 1.28.4 de `opentelemetry-sdk` nunca fue publicada en PyPI.

**Mitigación:** Usar la versión 1.28.2 (`opentelemetry-sdk==1.28.2`). Para los paquetes de instrumentación, usar `>=0.49b0` en lugar de pinned version para mayor flexibilidad.

**Archivos afectados:** `requirements.txt`.

---

### P-13: Prometheus no scrapea métricas de la app tras instalar kube-prometheus-stack

**Síntoma:** Los dashboards de Grafana mostraban "No data" para las métricas `procurement_*`.

**Causa:** kube-prometheus-stack por defecto solo scrape ServiceMonitors que tienen el label `release: kube-prometheus-stack`. Los ServiceMonitors del proyecto no tenían este label.

**Mitigación:** Dos opciones aplicadas:
1. Agregar el label `release: kube-prometheus-stack` a los ServiceMonitors del proyecto.
2. Configurar `serviceMonitorSelectorNilUsesHelmValues: false` en el values del stack para que scrape todos los ServiceMonitors.

**Archivos afectados:** `k8s/charts/monitoring/values.yaml`, `docs/fase05_manual/13-observability.md` §13.6b.

---

## 5. CI/CD

### P-14: Docker Hub rate limit bloquea el pipeline

**Síntoma:** El Job `build-and-test` fallaba con `toomanyrequests: You have reached your pull rate limit` al hacer pull de `python:3.12-slim` desde Docker Hub.

**Causa:** GitHub Actions usa IPs compartidas que rotan entre múltiples organizaciones. Docker Hub aplica rate limits por IP (100 pulls/6h para anónimos).

**Mitigación:** Importar las imágenes base (`python:3.12-slim`, `node:20-alpine`) al ACR propio con `az acr import` antes del build. El Dockerfile usa `ARG REGISTRY` para apuntar al ACR:
```bash
az acr import --name $ACR_NAME \
  --source docker.io/library/python:3.12-slim \
  --image python:3.12-slim --force || true
```

**Archivos afectados:** `.github/workflows/deploy.yml`, `docker/backend/Dockerfile`.

---

### P-15: Trivy scan falla con `database update failed`

**Síntoma:** El step de Trivy reportaba `FATAL database update failed` en el Job `security-scan`.

**Causa:** Trivy intenta descargar su base de datos de vulnerabilidades desde GitHub Releases. Con rate limits o problemas de red en el runner, la descarga falla.

**Mitigación:** Configurar `exit-code: '0'` en el action de Trivy para que los fallos de actualización de la DB no bloqueen el pipeline. El scan sigue siendo útil incluso con la DB local (puede estar desactualizada por horas, no días).

**Archivos afectados:** `.github/workflows/deploy.yml`.

---

## 6. Networking

### P-16: NGINX Ingress no acepta requests de más de 1 MB

**Síntoma:** La subida de PDFs grandes devolvía `413 Request Entity Too Large`.

**Causa:** NGINX tiene un límite de 1 MB por defecto para el body de las requests.

**Mitigación:** Agregar la anotación `nginx.ingress.kubernetes.io/proxy-body-size: "100m"` al Ingress del api-gateway para permitir archivos de hasta 100 MB.

**Archivos afectados:** `k8s/charts/api-gateway/templates/ingress.yaml`.

---

### P-17: Timeout en workflows largos (análisis completo > 60s)

**Síntoma:** Requests al endpoint `/workflow/full-analysis` devolvían `504 Gateway Timeout` para licitaciones grandes.

**Causa:** NGINX tiene un timeout de lectura de 60 segundos por defecto. Un análisis completo con 3 agentes puede tardar 2-8 minutos dependiendo del tamaño del documento.

**Mitigación:** Aumentar los timeouts de NGINX vía anotaciones del Ingress:
```yaml
nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
```

**Archivos afectados:** `k8s/charts/api-gateway/templates/ingress.yaml`.

---

## 7. Azure / Cloud

### P-18: Cuota de Spot no disponible para NC4as_T4_v3 en brazilsouth

**Síntoma:** `az aks nodepool add --priority Spot` fallaba con `QuotaExceeded: Spot instance quota not available`.

**Causa:** La región `brazilsouth` no tenía cuota de instancias Spot para la familia `Standard NCASTv3` disponible en el momento del despliegue.

**Mitigación:** Usar instancias **Regular** en lugar de Spot. Para controlar el costo, configurar el GPU pool con `min-count: 0` y auto-shutdown nocturno vía CronJob. El costo total con 8h/día en días hábiles es ~$88/mes vs ~$360/mes (24/7 Regular).

**Archivos afectados:** `docs/fase05_manual/05-node-pools-gpu.md`, memoria del proyecto.

---

### P-19: PostgreSQL Flexible Server requiere usuario con nombre específico

**Síntoma:** El init script de la base de datos fallaba con `FATAL: password authentication failed for user "procurement"`.

**Causa:** Azure PostgreSQL Flexible Server crea el usuario administrador con el formato `usuario@servidor`, no simplemente `usuario`. La connection string en el `.env` no incluía el sufijo del servidor.

**Mitigación:** Usar la connection string completa con el usuario `procurement@${PSQL_NAME}` para el usuario admin, y crear un usuario de aplicación `procurement` sin sufijo con permisos limitados solo a la base de datos `procurement_db`.

**Archivos afectados:** `scripts/init_db.sql`, `k8s/azure/api-gateway.yaml` (DATABASE_URL).

---

### P-20: Key Vault CSI Driver no monta secretos si el pod no tiene OIDC annotation

**Síntoma:** Los pods del API Gateway arrancaban pero el volumen de secretos aparecía como `MountVolume.SetUp failed`.

**Causa:** El CSI Driver de Key Vault requiere que el ServiceAccount del pod tenga la anotación `azure.workload.identity/client-id` con el Client ID de la Managed Identity, y el pod debe tener el label `azure.workload.identity/use: "true"`.

**Mitigación:** Agregar las anotaciones correctas al ServiceAccount y los labels al pod en el Helm chart:
```yaml
serviceAccount:
  annotations:
    azure.workload.identity/client-id: <MI_CLIENT_ID>
podLabels:
  azure.workload.identity/use: "true"
```

**Archivos afectados:** `k8s/charts/api-gateway/templates/serviceaccount.yaml`, `k8s/charts/api-gateway/values.yaml`.

---

## Resumen de impacto

| Categoría | Problemas | Impacto en el proyecto |
|-----------|-----------|------------------------|
| GPU / LLM | 3 | Requirieron cambio de motor de inferencia local y modelo |
| Kubernetes / Helm | 5 | Configuraciones de seguridad y deployment ajustadas |
| Base de datos | 2 | Fixes de código en repositorios SQLAlchemy |
| Observabilidad | 3 | Ajustes de configuración en OTel y Prometheus |
| CI/CD | 2 | Pipeline ajustado para rate limits externos |
| Networking | 2 | Timeouts y tamaños de body configurados |
| Azure / Cloud | 3 | Ajustes de arquitectura cloud y configuración |
| **Total** | **20** | — |
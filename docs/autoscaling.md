# Estrategias de Autoscaling — Autonomous Procurement Intelligence Platform

**Fecha:** Junio 2026

---

## Resumen de estrategias

| Componente | Tipo de escalado | Herramienta | Métrica trigger |
|-----------|-----------------|-------------|-----------------|
| API Gateway pods | Horizontal (réplicas) | HPA nativo K8s | CPU utilization > 70% |
| LangGraph pods | Horizontal (réplicas) | HPA nativo K8s | Memory utilization > 80% |
| vLLM pods | — | No implementado | HPA disabled; KEDA no desplegado |
| Nodos GPU pool | Horizontal (nodos) | Cluster Autoscaler | Pods en `Pending` |
| Nodos User pool | Horizontal (nodos) | Cluster Autoscaler | Pods en `Pending` |
| API Gateway CPU/mem | Vertical (recursos) | VPA (modo Auto) | Observación histórica |
| LangGraph CPU/mem | Vertical (recursos) | VPA (modo Auto) | Observación histórica |
| Qdrant CPU/mem | Vertical (sin restart) | VPA (modo Off) | Solo recomendaciones |

---

## 1. HPA — Horizontal Pod Autoscaler

### API Gateway

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-gateway-hpa
  namespace: ai-platform
spec:
  scaleTargetRef:
    apiVersion: argoproj.io/v1alpha1
    kind: Rollout
    name: api-gateway
  minReplicas: 2
  maxReplicas: 8
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

**Comportamiento:**
- Con < 10 usuarios: 2 réplicas (mínimo garantizado)
- Con 50-100 usuarios: 3-4 réplicas
- Con 200 usuarios: 6-8 réplicas
- Cooldown: ~5 min para scale-down (evita flapping)

### LangGraph

```yaml
minReplicas: 1
maxReplicas: 4
targetMemoryUtilizationPercentage: 80
```

**Nota:** LangGraph es un **worker de cola** (ejecuta `worker/main.py`, polling cada 15s sobre la BD). No expone puerto HTTP — usa `exec` probes para liveness/readiness. El HPA escala por memoria porque los workflows cargan contextos grandes en RAM.

### Limitaciones del HPA CPU para GPU workloads

El HPA CPU **no sirve** para vLLM porque:
- La inferencia LLM consume casi exclusivamente GPU, no CPU
- La CPU puede estar al 5% mientras el GPU está al 95%
- Un HPA CPU nunca dispararía el scale-up del vLLM aunque el GPU esté saturado

Por esta razón el HPA de vLLM está deshabilitado (`hpa.enabled: false` en `k8s/charts/vllm/values.yaml`). El escalado de vLLM se gestiona manualmente o mediante el Cluster Autoscaler a nivel de nodo.

---

## 2. Cluster Autoscaler

El Cluster Autoscaler está gestionado por AKS. Escala los **nodos** (VMs) cuando los pods no pueden ser programados.

### Configuración de node pools

```bash
# User Pool: pods de aplicación
az aks nodepool update \
  --resource-group $RG_NAME \
  --cluster-name $AKS_NAME \
  --name userpool \
  --enable-cluster-autoscaler \
  --min-count 1 \
  --max-count 4

# GPU Pool: pods de inferencia
az aks nodepool update \
  --resource-group $RG_NAME \
  --cluster-name $AKS_NAME \
  --name gpupool \
  --enable-cluster-autoscaler \
  --min-count 0 \   # scale-to-zero cuando no hay inferencia
  --max-count 2
```

### Flujo de scale-up

```
1. HPA crea nuevo pod de api-gateway
2. Pod queda en Pending (no hay recursos en nodos actuales)
3. Cluster Autoscaler detecta pod Pending después de ~1-3 min
4. Provisiona nuevo nodo (DS2_v2 / D4s_v3) en Azure (~3-5 min)
5. Pod se schedula en el nuevo nodo
```

### Flujo de scale-down

```
1. Nodo subutilizado por > 10 min (configurable)
2. Cluster Autoscaler verifica que los pods pueden moverse
3. Drena el nodo (cordon + eviction)
4. Termina la VM en Azure
5. Costo reducido inmediatamente
```

### Tabla de comportamiento esperado por carga

| Usuarios | Pods API GW | Pods LangGraph | Nodos User Pool | Nodos GPU Pool |
|---------|-------------|----------------|-----------------|----------------|
| < 10 | 2 | 1 | 1-2 | 0-1 |
| 10-50 | 2-3 | 1-2 | 2-3 | 1 |
| 50-100 | 3-6 | 2-3 | 3-5 | 1-2 |
| 100-200 | 6-8 | 3-4 | 5-7 | 2 |

---

## 3. KEDA — Kubernetes Event-Driven Autoscaling

> **Estado actual: NO desplegado.** No existen manifests de KEDA en `k8s/manifests/` ni en `k8s/charts/`. El ScaledObject documentado a continuación es el diseño planificado para escalar vLLM basándose en la cola de requests. El vLLM actual tiene `hpa.enabled: false` y escala manualmente.

### ScaledObject planificado para vLLM (no desplegado)

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: vllm-scaledobject
  namespace: ai-platform
spec:
  scaleTargetRef:
    name: vllm
  minReplicaCount: 1
  maxReplicaCount: 4
  cooldownPeriod: 300        # 5 min antes de scale-down (GPU warmup es lento)
  pollingInterval: 30        # Consulta Prometheus cada 30s
  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090
      metricName: vllm_requests_waiting
      threshold: "10"        # Si hay > 10 requests en cola → escalar
      query: |
        sum(vllm:num_requests_waiting{namespace="ai-platform"})
```

### Lógica de escalado (cuando se despliegue)

```
Cola vLLM > 10 requests esperando
    └─► KEDA escala +1 pod vLLM
         └─► Pod vLLM en Pending (sin GPU)
              └─► Cluster Autoscaler agrega nodo T4 (~5-7 min)
                   └─► Pod vLLM arranca + carga modelo (~2-3 min con PVC cacheado)
                        └─► Cola empieza a procesarse
```

**Latencia total de scale-up GPU:** ~5-10 min (modelo cacheado en PVC) / ~20-22 min (descarga desde HuggingFace)

### Scale-to-zero del GPU pool

```bash
az aks nodepool update \
  --resource-group $RG_NAME \
  --cluster-name $AKS_NAME \
  --name gpupool \
  --enable-cluster-autoscaler \
  --min-count 0 \   # Si todos los pods vLLM están en 0 → el nodo T4 se termina
  --max-count 2
```

Con `minReplicaCount: 0` en el ScaledObject (cuando se despliegue), KEDA permite scale-to-zero completo del vLLM.

---

## 4. VPA — Vertical Pod Autoscaler

### Configuración

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: api-gateway-vpa
  namespace: ai-platform
spec:
  targetRef:
    apiVersion: argoproj.io/v1alpha1
    kind: Rollout
    name: api-gateway
  updatePolicy:
    updateMode: Auto   # Permite reinicios para aplicar recomendaciones
  resourcePolicy:
    containerPolicies:
    - containerName: api-gateway
      minAllowed: { cpu: 100m, memory: 256Mi }
      maxAllowed: { cpu: 2000m, memory: 4Gi }
```

### Modos de VPA

| Modo | Comportamiento | Recomendado para |
|------|---------------|-----------------|
| `Off` | Solo registra recomendaciones, no actúa | Qdrant (stateful, sin reinicios) |
| `Initial` | Aplica recursos solo al crear el pod | Pods con startup lento |
| `Auto` | Reinicia pods para aplicar recomendaciones | API Gateway, LangGraph |
| `Recreate` | Elimina y recrea pods (downtime) | No recomendado con HPA |

### Consultar recomendaciones actuales

```bash
kubectl describe vpa api-gateway-vpa -n ai-platform
# Buscar la sección "Recommendation:"
# Lower Bound: mínimo recomendado
# Target: valor óptimo
# Upper Bound: máximo estimado
```

### Conflicto VPA + HPA

HPA y VPA no deben controlar la misma métrica (CPU/memory) simultáneamente. La configuración actual:
- HPA controla réplicas basado en CPU utilization (porcentaje)
- VPA controla los valores de requests/limits de CPU y memory

Esto es compatible porque HPA mira el porcentaje de utilización relativo al requests declarado, y VPA ajusta ese requests. El resultado es que VPA acomoda las réplicas de HPA para ser más eficientes.

---

## 5. Estrategia de escalado por escenario de carga

### Diseño por niveles de tráfico (vLLM)

| Nivel | Req/min | Tokens/s req. | Pods vLLM | Nodos T4 | Costo/hr |
|-------|---------|---------------|-----------|----------|---------|
| Idle | < 100 | < 830 | 1 | 1 | $0.50 |
| Medium | 100-500 | 830-4,150 | 1-4 | 1-4 | $0.50-$2.00 |
| High | 500-1,000 | 4,150-8,300 | 4-8 | 4-8 | $2.00-$4.00 |
| Peak | 1,000-5,000 | 8,300-41,500 | 8-20 | 8-20 | $4.00-$10.00 |

> Base: 1 pod vLLM en 1 nodo T4 = ~600 tok/s (AWQ 4-bit).

### Recomendación para lanzamiento (100-500 req/min)

```yaml
# KEDA ScaledObject ajustado para lanzamiento (cuando se despliegue KEDA)
minReplicaCount: 1
maxReplicaCount: 4
threshold: "5"       # escalar antes (< 10) para respuesta más rápida
cooldownPeriod: 600  # 10 min antes de scale-down
```

### Escalado automático con auto-shutdown nocturno

Para dev/staging con horario de oficina, configurar CronJob para apagar el GPU pool fuera de horario:

```yaml
# Scale a 0 nodos GPU a las 20:00 UTC
apiVersion: batch/v1
kind: CronJob
metadata:
  name: gpu-pool-shutdown
  namespace: ai-platform
spec:
  schedule: "0 20 * * 1-5"   # Lunes-Viernes 20:00 UTC
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: az-cli
            image: mcr.microsoft.com/azure-cli
            command:
            - az
            - aks
            - nodepool
            - scale
            - --resource-group
            - $(RG_NAME)
            - --cluster-name
            - $(AKS_NAME)
            - --name
            - gpupool
            - --node-count
            - "0"
```

**Ahorro estimado:** Si el GPU pool (T4 @ $0.50/hr) corre solo 8h/día en días hábiles → ~$88/mes vs ~$360/mes (24/7).
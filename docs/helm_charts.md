# Helm Charts — Autonomous Procurement Intelligence Platform

**Fecha:** Junio 2026

---

## Estructura general

```
k8s/
├── charts/                  ← Helm charts del proyecto
│   ├── api-gateway/         ← FastAPI backend + HPA + Rollout
│   ├── langgraph/           ← LangGraph worker (agentes)
│   ├── embeddings/          ← Sentence-transformers service
│   ├── postgres/            ← PostgreSQL (solo Fase 4 local)
│   ├── vllm/                ← vLLM inference server (AKS)
│   ├── ollama/              ← Ollama inference (Fase 4 local)
│   ├── qdrant/              ← Qdrant vector store
│   ├── minio/               ← MinIO object storage (Fase 4 local)
│   └── monitoring/          ← kube-prometheus-stack + loki-stack + dashboards
│
├── azure/                   ← Overrides de values para AKS (Fase 5)
│   ├── api-gateway.yaml
│   ├── vllm.yaml
│   └── ...
│
└── manifests/               ← Recursos que Helm no gestiona directamente
    ├── api-gateway-rollout.yaml   ← Argo Rollouts Rollout
    ├── analysis-template.yaml    ← AnalysisTemplate para canary
    ├── vpa.yaml                   ← VPA para api-gateway, langgraph, qdrant
    └── frontend.yaml              ← Deployment del frontend
```

---

## Chart: api-gateway

**Versión:** 0.1.0 | **AppVersion:** 3.0.0

### Recursos creados

| Template | Tipo | Descripción |
|----------|------|-------------|
| `deployment.yaml` | Deployment | Pods del API Gateway FastAPI |
| `service.yaml` | Service (ClusterIP) | Exposición interna puerto 8000 |
| `ingress.yaml` | Ingress | Ruta HTTP/S externa via NGINX |
| `hpa.yaml` | HorizontalPodAutoscaler | min 2 / max 8 réplicas, target CPU 70% |
| `configmap.yaml` | ConfigMap | Variables de entorno no sensibles |
| `secret.yaml` | Secret | Referencia a secretos (montados via CSI) |
| `serviceaccount.yaml` | ServiceAccount | Identidad del pod para Key Vault CSI |

### Values principales (`k8s/charts/api-gateway/values.yaml`)

```yaml
replicaCount: 2

image:
  repository: procurement-api
  pullPolicy: IfNotPresent
  tag: latest

service:
  type: ClusterIP
  port: 80
  targetPort: 8000

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: procurement.local
      paths: [{ path: /, pathType: Prefix }]

resources:
  requests:
    cpu: 250m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 1Gi

hpa:
  enabled: true
  minReplicas: 2
  maxReplicas: 8
  targetCPUUtilizationPercentage: 70

env:
  DATABASE_URL: "postgresql+asyncpg://..."
  QDRANT_HOST: qdrant
  VLLM_BASE_URL: "http://vllm:8000/v1"
  EMBEDDINGS_URL: "http://embeddings:8080"
  PROMETHEUS_URL: "http://prometheus:9090"
```

### Overrides AKS (`k8s/azure/api-gateway.yaml`)

```yaml
image:
  repository: <ACR_NAME>.azurecr.io/procurement-api
  tag: latest

ingress:
  hosts:
    - host: procurement.local   # sobreescrito con IP real del LB
      paths: [{ path: /, pathType: Prefix }]

resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 2000m
    memory: 2Gi

hpa:
  minReplicas: 2
  maxReplicas: 8
  targetCPUUtilizationPercentage: 70
```

---

## Chart: monitoring

**Dependencias:** `kube-prometheus-stack` + `loki-stack` (sub-charts)

### Componentes incluidos

| Componente | Descripción | Puerto |
|-----------|-------------|--------|
| Prometheus | Scrape de métricas, almacenamiento 15 días / 20 Gi | 9090 |
| Grafana | Dashboards, datasources Prometheus + Loki | 80/3000 |
| Loki | Almacenamiento de logs, retención 168h | 3100 |
| Promtail | DaemonSet que recoge logs de pods y los envía a Loki | — |
| kube-state-metrics | Métricas de estado de recursos K8s | 8080 |
| AlertManager | Deshabilitado en dev (configurar para producción) | 9093 |
| node-exporter | Deshabilitado en Fase 4 (WSL2 incompatible) | 9100 |

### ServiceMonitors configurados

```yaml
# Fase 4 local (values.yaml)
additionalServiceMonitors:
  - name: ai-platform-api-gateway
    selector:
      matchLabels: { app: api-gateway }
    namespaceSelector:
      matchNames: [ai-platform]
    endpoints:
      - port: metrics
        path: /metrics
        interval: 10s

  - name: ai-platform-vllm
    selector:
      matchLabels: { app: vllm }
    namespaceSelector:
      matchNames: [ai-platform]
    endpoints:
      - port: metrics
        path: /metrics
        interval: 10s
```

### Dashboards (ConfigMaps con label `grafana_dashboard: "1"`)

| Dashboard | Archivo | KPIs |
|-----------|---------|------|
| LLM & RAG | `dashboard-llm.yaml` | Tokens/s, Latencia P50/P90/P99 LLM, Costo/hora |
| Platform API | `dashboard-api.yaml` | Req/s, HTTP latencia, Error rate |
| GPU & Infra | `dashboard-gpu.yaml` | GPU util%, VRAM%, temperatura |
| Agents | `dashboard-agents.yaml` | Workflow runs, éxito/fallo por agente |

### Almacenamiento configurado

```yaml
prometheus:
  prometheusSpec:
    retention: 15d
    storageSpec:
      volumeClaimTemplate:
        spec:
          storageClassName: local-path   # Fase 4
          # storageClassName: managed-premium  # AKS
          resources:
            requests:
              storage: 20Gi

grafana:
  persistence:
    enabled: true
    size: 5Gi

loki:
  persistence:
    enabled: true
    size: 10Gi
```

---

## Chart: vllm

### Values principales

```yaml
image:
  repository: <ACR_NAME>.azurecr.io/vllm-openai
  tag: latest

model: Qwen/Qwen2.5-7B-Instruct-AWQ
quantization: awq

args:
  - --max-model-len=8192
  - --max-num-seqs=256
  - --max-num-batched-tokens=8192
  - --enable-chunked-prefill
  - --gpu-memory-utilization=0.85
  - --quantization=awq

resources:
  requests:
    nvidia.com/gpu: 1
    memory: 20Gi
    cpu: "2"
  limits:
    nvidia.com/gpu: 1
    memory: 24Gi
    cpu: "4"

nodeSelector:
  agentpool: gpupool

persistence:
  enabled: true
  size: 20Gi              # Para cachear el modelo AWQ (~4.2 GB)
  storageClassName: managed-premium
  mountPath: /data/cache
```

### Toleraciones para nodo GPU Spot

```yaml
tolerations:
  - key: "kubernetes.azure.com/scalesetpriority"
    operator: "Equal"
    value: "spot"
    effect: "NoSchedule"
  - key: "nvidia.com/gpu"
    operator: "Exists"
    effect: "NoSchedule"
```

---

## Chart: qdrant

### Values principales

```yaml
persistence:
  enabled: true
  size: 10Gi
  storageClassName: local-path  # managed-premium en AKS

resources:
  requests:
    cpu: 250m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 2Gi

service:
  type: ClusterIP
  port: 6333

# Sin autenticación en dev — habilitar en producción
config:
  service:
    api_key: ""
```

---

## Cómo instalar todos los charts (Fase 5 AKS)

```bash
source ~/.procurement_env

# 1. Monitoring stack
helm upgrade --install monitoring k8s/charts/monitoring \
  -n monitoring --create-namespace \
  --set kube-prometheus-stack.prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.storageClassName=managed-premium \
  --wait --timeout 10m

# 2. Qdrant
helm upgrade --install qdrant k8s/charts/qdrant \
  -n ai-platform --create-namespace --wait

# 3. Embeddings
helm upgrade --install embeddings k8s/charts/embeddings \
  -n ai-platform --wait

# 4. LangGraph
helm upgrade --install langgraph k8s/charts/langgraph \
  -n ai-platform --wait

# 5. API Gateway (con overrides AKS)
helm upgrade --install api-gateway k8s/charts/api-gateway \
  -n ai-platform \
  -f k8s/azure/api-gateway.yaml \
  --wait --timeout 3m

# 6. vLLM (requiere nodo GPU disponible)
helm upgrade --install vllm k8s/charts/vllm \
  -n ai-platform \
  -f k8s/azure/vllm.yaml \
  --wait --timeout 20m  # descarga el modelo ~4.2 GB

# 7. Manifests adicionales (Argo Rollouts, VPA)
kubectl apply -f k8s/manifests/api-gateway-rollout.yaml
kubectl apply -f k8s/manifests/analysis-template.yaml
kubectl apply -f k8s/manifests/vpa.yaml
```
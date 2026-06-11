# YAMLs Clave — Autonomous Procurement Intelligence Platform

**Fecha:** Junio 2026

---

## 1. Argo Rollouts — Canary Deployment (`k8s/manifests/api-gateway-rollout.yaml`)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: api-gateway
  namespace: ai-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api-gateway
  template:
    metadata:
      labels:
        app: api-gateway
    spec:
      containers:
      - name: api-gateway
        image: acrprocurementazdev.azurecr.io/procurement-api:latest
        ports:
        - containerPort: 8000
        resources:
          requests: { cpu: 200m, memory: 512Mi }
          limits: { cpu: 1000m, memory: 2Gi }
  strategy:
    canary:
      stableService: api-gateway-stable
      canaryService: api-gateway-canary
      maxSurge: 1
      maxUnavailable: 1
      steps:
      - setWeight: 10           # 10% del tráfico al canary
      - pause:
          duration: 2m          # espera 2 min con tráfico real
      - analysis:               # análisis automático de success rate
          templates:
          - templateName: success-rate
          args:
          - name: service-name
            value: api-gateway
      - setWeight: 50           # 50% si el análisis pasó
      - pause:
          duration: 2m
      - analysis:               # segundo análisis antes de promote
          templates:
          - templateName: success-rate
          args:
          - name: service-name
            value: api-gateway
      - setWeight: 100          # promote completo
```

**Qué hace:**
- Despliega el **10%** del tráfico a la versión nueva (canary)
- Espera 2 min con tráfico real, luego ejecuta `success-rate` (error rate < 5% via Prometheus)
- Si el análisis falla → rollback automático a versión estable
- Si pasa → sube al 50%, espera 2 min, segundo análisis → promote al 100%

---

## 2. AnalysisTemplate — Validación de canary (`k8s/manifests/analysis-template.yaml`)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
  namespace: ai-platform
spec:
  args:
  - name: service-name
  metrics:
  - name: success-rate
    interval: 60s              # consulta cada 60 segundos
    count: 5                   # 5 mediciones por análisis
    successCondition: result[0] >= 0.95   # 95% de requests exitosos
    failureLimit: 2            # tolera hasta 2 fallos antes de abortar
    provider:
      prometheus:
        address: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090
        query: |
          sum(rate(
            procurement_http_requests_total{
              service="{{args.service-name}}",
              status!~"5.."
            }[5m]
          )) /
          sum(rate(
            procurement_http_requests_total{
              service="{{args.service-name}}"
            }[5m]
          ) or vector(1))
```

**Qué hace:** Consulta Prometheus cada **60 segundos** (**5 veces**). Tolera hasta **2 fallos** antes de abortar el canary y hacer rollback. El `or vector(1)` en el divisor evita división por cero cuando no hay tráfico.

**Nota:** La métrica de latencia fue removida (ver `problemas_mitigaciones.md` P-08).

---

## 3. KEDA ScaledObject — Autoscaling de vLLM

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
  cooldownPeriod: 300
  pollingInterval: 30
  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090
      metricName: vllm_requests_waiting
      threshold: "10"
      query: |
        sum(vllm:num_requests_waiting{namespace="ai-platform"})
```

---

## 4. VPA — Vertical Pod Autoscaler (`k8s/manifests/vpa.yaml`)

```yaml
---
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
    updateMode: Auto
  resourcePolicy:
    containerPolicies:
    - containerName: api-gateway
      minAllowed: { cpu: 100m, memory: 256Mi }
      maxAllowed: { cpu: 2000m, memory: 4Gi }
---
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: langgraph-vpa
  namespace: ai-platform
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: langgraph
  updatePolicy:
    updateMode: Auto
  resourcePolicy:
    containerPolicies:
    - containerName: langgraph
      minAllowed: { cpu: 100m, memory: 256Mi }
      maxAllowed: { cpu: 2000m, memory: 4Gi }
---
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: qdrant-vpa
  namespace: ai-platform
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: qdrant
  updatePolicy:
    updateMode: "Off"    # Solo recomendaciones, sin reinicios
```

---

## 5. Network Policies — Seguridad (`k8s/manifests/network-policies.yaml`)

```yaml
# Denegar todo el tráfico por defecto
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: ai-platform
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
# Ingress → API Gateway (desde NGINX)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-to-api-gateway
  namespace: ai-platform
spec:
  podSelector:
    matchLabels: { app: api-gateway }
  policyTypes: [Ingress]
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8000
---
# API Gateway → LangGraph
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-to-langgraph
  namespace: ai-platform
spec:
  podSelector:
    matchLabels: { app: langgraph }
  policyTypes: [Ingress]
  ingress:
  - from:
    - podSelector:
        matchLabels: { app: api-gateway }
    ports:
    - protocol: TCP
      port: 8001
---
# LangGraph → vLLM
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-langgraph-to-vllm
  namespace: ai-platform
spec:
  podSelector:
    matchLabels: { app: vllm }
  policyTypes: [Ingress]
  ingress:
  - from:
    - podSelector:
        matchExpressions:
        - key: app
          operator: In
          values: [api-gateway, langgraph]
    ports:
    - protocol: TCP
      port: 8000
---
# DNS egress (todos los pods)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-egress
  namespace: ai-platform
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
  - ports:
    - protocol: UDP
      port: 53
    - protocol: TCP
      port: 53
---
# Egress hacia Azure services (PostgreSQL, Blob, Key Vault)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-azure-services-egress
  namespace: ai-platform
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
  - ports:
    - protocol: TCP
      port: 5432    # PostgreSQL
    - protocol: TCP
      port: 443     # HTTPS (Blob, Key Vault)
```

---

## 6. PrometheusRules — Alertas (`k8s/charts/monitoring/`)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: procurement-platform-alerts
  namespace: monitoring
  labels:
    release: kube-prometheus-stack
spec:
  groups:
  - name: gpu.rules
    rules:
    - alert: GPUThrottling
      expr: DCGM_FI_DEV_GPU_UTIL > 95
      for: 5m
      labels: { severity: critical }
      annotations:
        summary: "GPU saturada — posible throttling"
        description: "GPU utilization > 95% durante 5 minutos."
  - name: api-gateway.rules
    rules:
    - alert: APIHighLatency
      expr: |
        histogram_quantile(0.99,
          sum(rate(procurement_http_request_duration_seconds_bucket[5m]))
          by (le)
        ) > 0.8
      for: 2m
      labels: { severity: warning }
      annotations:
        summary: "API Gateway P99 latencia > 800ms"
    - alert: PodCrashLooping
      expr: |
        rate(kube_pod_container_status_restarts_total{namespace="ai-platform"}[15m]) > 0
      for: 5m
      labels: { severity: critical }
      annotations:
        summary: "Pod reiniciando repetidamente en ai-platform"
        description: "Pod {{ $labels.pod }} ha tenido reinicios en 15 min."
```

---

## 7. ServiceMonitors — Scrape de métricas

```yaml
# ServiceMonitor para API Gateway
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: api-gateway
  namespace: ai-platform
  labels:
    release: kube-prometheus-stack
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: api-gateway
  endpoints:
  - port: http
    path: /metrics
    interval: 15s
---
# ServiceMonitor para vLLM
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: vllm-metrics
  namespace: monitoring
  labels:
    release: kube-prometheus-stack
spec:
  namespaceSelector:
    matchNames: [ai-platform]
  selector:
    matchLabels: { app: vllm }
  endpoints:
  - port: http
    path: /metrics
    interval: 15s
```

---

## 8. Pod Security Standards — Labels de namespace

```bash
# ai-platform: enforce=baseline, warn=restricted
kubectl label namespace ai-platform \
  pod-security.kubernetes.io/enforce=baseline \
  pod-security.kubernetes.io/enforce-version=latest \
  pod-security.kubernetes.io/warn=restricted \
  pod-security.kubernetes.io/warn-version=latest

# monitoring: enforce=baseline (necesario para node-exporter)
kubectl label namespace monitoring \
  pod-security.kubernetes.io/enforce=baseline

# gpu-operator: privileged (requiere acceso al hardware)
kubectl label namespace gpu-operator \
  pod-security.kubernetes.io/enforce=privileged
```

---

## 9. Ingress con timeouts para workflows largos

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-gateway
  namespace: ai-platform
  annotations:
    kubernetes.io/ingress.class: nginx
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-connect-timeout: "60"
spec:
  rules:
  - host: procurement.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: api-gateway
            port:
              number: 80
```
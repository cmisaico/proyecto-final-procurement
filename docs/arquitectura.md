# Arquitectura del Sistema — Autonomous Procurement Intelligence Platform

**Versión:** 3.0.0 | **Fecha:** Junio 2026

---

## 1. Visión general

La plataforma es una aplicación LLM de múltiples fases, diseñada para automatizar el análisis de licitaciones públicas mediante RAG (Retrieval-Augmented Generation) y orquestación multi-agente.

### Evolución por fases

| Fase | Descripción | Deployment |
|------|-------------|------------|
| Fase 1 | RAG Platform — FastAPI + LangChain + Ollama + Qdrant | Docker Compose local |
| Fase 2 | Multi-Agent Compliance — LangGraph Supervisor + 3 agentes especializados | Docker Compose local |
| Fase 3 | LLMOps — Prometheus + Grafana + Loki + OTel + K6 | Docker Compose local |
| Fase 4 | Kubernetes — Helm charts + GPU (RTX 5080) + kubeadm en WSL2 | K8s local |
| Fase 5 | AKS Cloud — Azure AKS + T4 Spot + vLLM + CI/CD + Canary | Azure AKS |

---

## 2. Arquitectura de componentes (Fase 5 — AKS)

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NGINX Ingress Controller (Public Load Balancer — AKS)              │
│  IP pública ← az aks get-credentials → procurement.{dominio}        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
           ┌───────────────▼────────────────────┐
           │     Namespace: ai-platform          │
           │                                     │
           │  ┌─────────────────────────────┐   │
           │  │  API Gateway (FastAPI)       │   │
           │  │  Rollout — canary deploy     │   │
           │  │  HPA: min 2 / max 8 pods     │   │
           │  │  Puerto: 8000                │   │
           │  └──────┬──────────────┬────────┘   │
           │         │              │            │
           │  ┌──────▼──────┐ ┌────▼──────────┐ │
           │  │  LangGraph  │ │  Embeddings   │ │
           │  │  (Worker)   │ │  Service      │ │
           │  │  Sin puerto │ │  Puerto:8080  │ │
           │  └──────┬──────┘ └───────────────┘ │
           │         │                           │
           │  ┌──────▼──────────────────────────┐│
           │  │  vLLM — Qwen2.5-7B-AWQ          ││
           │  │  GPU pool: NC4as_T4_v3           ││
           │  │  HPA disabled / escala manual    ││
           │  │  Puerto: 8000                    ││
           │  └─────────────────────────────────┘│
           │                                     │
           │  ┌─────────────┐ ┌────────────────┐ │
           │  │  Qdrant      │ │  OTel Collector│ │
           │  │  (Vector DB) │ │  Puerto: 4317  │ │
           │  │  Puerto:6333 │ └────────────────┘ │
           │  └─────────────┘                    │
           └─────────────────────────────────────┘
                    │               │               │
        ┌───────────▼──┐   ┌───────▼──────┐  ┌────▼──────────┐
        │ Azure          │   │ Azure Blob   │  │ Azure Key     │
        │ PostgreSQL     │   │ Storage      │  │ Vault         │
        │ B_Standard_B2ms│   │ (documentos) │  │ (secretos)    │
        └────────────────┘   └──────────────┘  └───────────────┘
                    │
        ┌───────────▼──────────────────────┐
        │  Namespace: monitoring            │
        │  Prometheus + Grafana + Loki      │
        │  Promtail + kube-state-metrics    │
        │  DCGM Exporter (GPU metrics)      │
        └──────────────────────────────────┘
```

---

## 3. Capas de la arquitectura

### Capa de presentación
- **Frontend:** Next.js 14 (App Router) con TypeScript
- **UI:** TailwindCSS + shadcn/ui, tema oscuro
- **Comunicación:** REST API via proxy Next.js → API Gateway interno

### Capa de API
- **API Gateway:** FastAPI (Python 3.12), patrón Clean Architecture
- **Endpoints principales:** `/api/v1/{health,documents,rag,workflow,agents,reports,cost}`
- **Middleware:** Prometheus metrics, OTEL tracing, request logging
- **Deployment:** Argo Rollouts (canary), HPA CPU-based

### Capa de orquestación (Agentes)
- **LangGraph Worker:** orquestación del workflow multi-agente (Supervisor Pattern)
- **Agentes:** Legal Analysis, Proposal Generation, Compliance Audit
- **Patrones:** Guardrail, Efficient Context Handling, Inference Router

### Capa de datos
- **PostgreSQL:** documentos, licitaciones, workflows, reportes
- **Qdrant:** vector store para embeddings de chunks de documentos
- **Azure Blob / MinIO:** almacenamiento de archivos PDF originales

### Capa de inferencia
- **vLLM** (AKS): servidor OpenAI-compatible, continuous batching, AWQ 4-bit
- **Ollama** (local Fase 4): misma interfaz, modelo `qwen2.5:7b`
- **Embeddings Service:** `sentence-transformers/all-MiniLM-L6-v2` vía API REST

---

## 4. Flujo de datos — Consulta RAG

```
Usuario
  │ POST /api/v1/rag/query
  ▼
API Gateway (FastAPI)
  │ 1. Valida request
  │ 2. Llama RAGPipeline
  ▼
Context Manager
  │ 3. Embedding de la query → Embeddings Service
  │ 4. Búsqueda semántica top-k en Qdrant
  │ 5. Compresión y ranking de chunks
  ▼
vLLM / Ollama
  │ 6. Inferencia con contexto recuperado
  │ 7. Genera respuesta + metadata de tokens
  ▼
API Gateway
  │ 8. Registra métricas (tokens, latencia, ruta)
  │ 9. Retorna { answer, sources, route }
  ▼
Usuario
```

---

## 5. Flujo de datos — Workflow multi-agente

```
Usuario
  │ POST /api/v1/workflow/full-analysis { tender_id }
  ▼
API Gateway → RunFullAnalysisUseCase
  │
  ├─► [Agente Legal]
  │       ├── Recupera contexto RAG (top-k=10)
  │       ├── Guardrail check (input)
  │       ├── Inferencia vLLM → análisis legal
  │       ├── Guardrail check (output)
  │       └── Retorna { riesgos, obligaciones, clausulas_criticas }
  │
  ├─► [Agente de Propuesta] ← recibe output del legal
  │       ├── Recupera contexto adicional
  │       ├── Genera propuesta técnica y económica
  │       └── Retorna { propuesta_tecnica, propuesta_economica }
  │
  ├─► [Agente de Auditoría] ← recibe outputs de legal + propuesta
  │       ├── Cross-check propuesta vs requisitos
  │       ├── Calcula compliance score (0-1)
  │       └── Retorna { score, observaciones, recomendaciones }
  │
  └─► [Reporte Final]
          ├── Consolida todos los outputs
          ├── Guarda en PostgreSQL
          └── Retorna workflow completo
```

---

## 6. Arquitectura de observabilidad

```
Pods (ai-platform)
  │ /metrics (Prometheus format)
  ▼
ServiceMonitor → Prometheus (scrape 15s)
  │
  ├── Métricas HTTP: procurement_http_requests_total, latency histograms
  ├── Métricas LLM:  procurement_llm_tokens_total, tokens_per_second
  ├── Métricas GPU:  DCGM_FI_DEV_GPU_UTIL (vía DCGM Exporter)
  └── Métricas K8s:  kube_pod_*, node_cpu_*, etc. (kube-state-metrics)
                │
                ▼
           Grafana (4 dashboards)
                │
  Logs → Promtail → Loki → Grafana (Explore)

  Trazas → OTel Collector → (futuro: Tempo / Jaeger)

  Alertas → PrometheusRules → Alertmanager → email/PagerDuty
```

---

## 7. Arquitectura de seguridad

| Capa | Mecanismo |
|------|-----------|
| Secretos | Azure Key Vault + CSI Driver (montaje como volumen) |
| Imágenes | Trivy scan en CI/CD (CRITICAL/HIGH) |
| Pods | Pod Security Standards: `enforce=baseline` en ai-platform |
| Red | Network Policies Calico (default-deny + allowlist por servicio) |
| TLS | cert-manager + Let's Encrypt (opcional, requiere dominio) |
| RBAC | ServiceAccounts por namespace, principio mínimo privilegio |
| LLM | Guardrail Pattern (input + output validation) |

---

## 8. Decisiones de diseño clave

| Decisión | Elección | Alternativa descartada | Razón |
|----------|----------|------------------------|-------|
| Inference engine local | Ollama | vLLM | RTX 5080 (sm_120) no soportado por CUDA 12.1/12.4 en vLLM |
| Inference engine AKS | vLLM | Ollama | vLLM tiene continuous batching y OpenAI API compatible |
| Cuantización AKS | AWQ 4-bit | FP16 | T4 tiene 16 GB VRAM; FP16 (14.5 GB) no deja espacio para KV cache |
| Vector DB | Qdrant | Pinecone, Weaviate | Self-hosted, rendimiento alto, sin costo adicional |
| Canary deployment | Argo Rollouts | Kubernetes rolling update | Análisis automático via Prometheus, rollback granular |
| Autoscaling GPU | Cluster Autoscaler (activo) + KEDA (planificado) | HPA CPU | GPU no se escala por CPU; HPA vLLM deshabilitado; KEDA previsto para escalar por cola vLLM |
| ORM | SQLAlchemy async | Tortoise, Django ORM | Soporte asyncio nativo con FastAPI |
| Storage | Azure Blob (prod) / MinIO (dev) | S3, GCS | Mismo SDK (boto3-compatible), sin cambio de código |
| Logs | Loki + Promtail | ELK Stack | Menor footprint de memoria, integración nativa con Grafana |
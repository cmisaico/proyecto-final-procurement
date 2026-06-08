# Autonomous Procurement Intelligence Platform

Plataforma LLM de análisis automatizado de licitaciones públicas. Implementa un pipeline RAG (Retrieval-Augmented Generation) con orquestación multi-agente, desplegada en Azure AKS con vLLM, LangGraph y Qdrant.

**Stack:** FastAPI · Next.js · LangGraph · vLLM (Qwen2.5-7B-AWQ) · Qdrant · Argo Rollouts · Prometheus · Grafana · Helm · Azure AKS

---

## Documentacion

| # | Documento | Descripcion |
|---|-----------|-------------|
| 1 | [Guia de Usuario](docs/guia_usuario/guia_usuario.md) | Instalacion, configuracion y uso de la plataforma |
| 2 | [Guia de Administrador](docs/guia_usuario/guia_administrador.md) | Operaciones de administracion, monitoreo y mantenimiento del cluster |
| 3 | [Arquitectura](docs/guia_usuario/arquitectura.md) | Disenio de componentes, decisiones tecnicas y flujo de datos |
| 4 | [Patrones LLM](docs/guia_usuario/patrones_llm.md) | Inference Router, Guardrail, Efficient Context Handling y Continuous Batching |
| 5 | [Helm Charts](docs/guia_usuario/helm_charts.md) | Estructura de charts, values principales y comandos de despliegue |
| 6 | [Dockerfiles](docs/guia_usuario/dockerfiles.md) | Imagenes de cada servicio, multi-stage builds y optimizaciones |
| 7 | [YAMLs](docs/guia_usuario/yamls.md) | Manifests clave: Rollout canary, AnalysisTemplate, Network Policies, VPA |
| 8 | [Resultados de Pruebas](docs/guia_usuario/resultados_pruebas.md) | Benchmarks de carga (K6), latencia P50/P99 y comparativa RTX 5080 vs T4 |
| 9 | [Estrategias de Autoscaling](docs/guia_usuario/autoscaling.md) | HPA, Cluster Autoscaler, VPA y diseno de KEDA para vLLM |
| 10 | [Calculo de Costos](docs/guia_usuario/calculo_costos.md) | Estimacion de costos en Azure por componente y escenario de carga |
| 11 | [Problemas y Mitigaciones](docs/guia_usuario/problemas_mitigaciones.md) | Registro de problemas encontrados durante el desarrollo y sus soluciones |
| 12 | [Diagramas Formales](docs/guia_usuario/diagramas.md) | Diagramas de arquitectura, flujo RAG, autoscaling y canary deployment |

---

## Estructura del repositorio

```
proyecto_final/
├── app/                    # Backend FastAPI (Clean Architecture)
│   ├── agents/             # LangGraph: LegalAgent, ProposalAgent, AuditAgent
│   ├── api/v1/endpoints/   # Endpoints: documents, rag, workflow, health
│   ├── rag/                # Pipeline RAG: pipeline.py, chunker, retriever
│   └── services/           # InferenceRouter, GuardrailService, EfficientContextHandler
├── frontend/               # Next.js 14 (App Router, TypeScript, TailwindCSS)
├── worker/                 # LangGraph worker process (polling cada 15s)
├── k8s/
│   ├── charts/             # Helm charts: api-gateway, vllm, langgraph, embeddings, monitoring
│   ├── manifests/          # Argo Rollouts, AnalysisTemplate, VPA, Network Policies
│   └── ingress/            # NGINX Ingress routes
└── docs/                   # Documentacion tecnica completa
```

## Acceso rapido (AKS)

| Servicio | URL |
|---------|-----|
| Frontend | `http://procurement.local/` |
| API Docs (Swagger) | `http://procurement.local/docs` |
| Grafana | `kubectl port-forward svc/kube-prometheus-stack-grafana 3000:80 -n monitoring` |
| Prometheus | `kubectl port-forward svc/kube-prometheus-stack-prometheus 9090:9090 -n monitoring` |

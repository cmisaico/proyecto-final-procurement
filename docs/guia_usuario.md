# Guía de Usuario — Autonomous Procurement Intelligence Platform

**Versión:** 3.0.0  
**Plataforma:** Azure AKS (Fase 5) / Kubernetes local (Fase 4)  
**Fecha:** Junio 2026

---

## Tabla de contenido

1. [Introducción](#1-introducción)
2. [Acceso a la plataforma](#2-acceso-a-la-plataforma)
3. [Interfaz web — Navegación](#3-interfaz-web--navegación)
4. [Dashboard de sistema](#4-dashboard-de-sistema)
5. [Gestión de documentos](#5-gestión-de-documentos)
6. [Consulta RAG](#6-consulta-rag)
7. [Workflow multi-agente](#7-workflow-multi-agente)
8. [Reportes](#8-reportes)
9. [Análisis de costos](#9-análisis-de-costos)
10. [API REST — Referencia rápida](#10-api-rest--referencia-rápida)
11. [Monitoreo y observabilidad](#11-monitoreo-y-observabilidad)
12. [Solución de problemas frecuentes](#12-solución-de-problemas-frecuentes)

---

## 1. Introducción

La **Autonomous Procurement Intelligence Platform** es una plataforma de inteligencia artificial diseñada para automatizar el análisis de licitaciones y documentos de compras públicas.

### Capacidades principales

| Capacidad | Descripción |
|-----------|-------------|
| **RAG (Retrieval-Augmented Generation)** | Consulta en lenguaje natural sobre documentos de licitación indexados |
| **Análisis legal automatizado** | Agente especializado que identifica riesgos y obligaciones contractuales |
| **Generación de propuestas** | Agente que redacta propuestas técnicas basadas en requisitos detectados |
| **Auditoría de cumplimiento** | Agente que verifica que la propuesta cumple con las bases del concurso |
| **LLMOps & observabilidad** | Métricas de tokens, latencia, costos y dashboards Grafana en tiempo real |

### Modelo LLM

- **Local (Fase 4):** Qwen2.5:7b vía Ollama — RTX 5080 (15.9 GB VRAM)
- **Cloud (Fase 5):** Qwen2.5-7B-Instruct-AWQ (4-bit) vía vLLM — NVIDIA T4 Spot en AKS

---

## 2. Acceso a la plataforma

### Fase 4 — Kubernetes local (WSL2)

| Servicio | URL | Credenciales |
|----------|-----|-------------|
| **Frontend web** | `http://172.19.137.191` | — |
| **API REST** | `http://172.19.137.191/api/v1` | — |
| **API docs (Swagger)** | `http://172.19.137.191/docs` | — |
| **Grafana** | `http://172.19.137.191:30300` | `admin` / `procurement123` |

> Para usar el hostname `procurement.local`, agregar a `C:\Windows\System32\drivers\etc\hosts` (como administrador):
> ```
> 172.19.137.191  procurement.local
> ```
> Luego acceder vía `http://procurement.local`

### Fase 5 — AKS Cloud

| Servicio | URL |
|----------|-----|
| **Frontend web** | `https://procurement.{dominio}/` |
| **API REST** | `https://procurement.{dominio}/api/v1` |
| **Grafana Managed** | Azure Portal → Managed Grafana → `graf-procurement-dev` |

---

## 3. Interfaz web — Navegación

La interfaz web cuenta con una barra lateral fija con las siguientes secciones:

```
┌─────────────────────────────────┐
│  ⬡  Procurement                 │
│     Intelligence Platform       │
├─────────────────────────────────┤
│  ▦  Dashboard         ←estado  │
│  ☰  Documents         ←upload  │
│  ✉  RAG Query         ←chat    │
│  ⑂  Workflow          ←análisis│
│  ≡  Reports           ←reportes│
│  $  Cost Analysis     ←costos  │
├─────────────────────────────────┤
│  Procurement                    │
│  Qwen2.5:7b                     │
└─────────────────────────────────┘
```

---

## 4. Dashboard de sistema

**Ruta:** `/dashboard`

Muestra el estado en tiempo real de todos los servicios de la plataforma. Se actualiza automáticamente cada **15 segundos**.

### Métricas visibles

| Métrica | Descripción |
|---------|-------------|
| **Overall Status** | `healthy` si todos los servicios están activos, `degraded` si alguno falla |
| **Services Online** | Contador de servicios activos vs total (ej. `4/4`) |
| **Avg Latency** | Latencia promedio en ms de las comprobaciones de salud |
| **Version** | Versión del API actualmente desplegada |

### Servicios monitoreados

| Servicio | Descripción |
|----------|-------------|
| `postgres` | Base de datos PostgreSQL — documentos, workflows, reportes |
| `qdrant` | Vector store — índice de embeddings para RAG |
| `storage` | MinIO / Azure Blob — almacenamiento de archivos PDF |
| `vllm` | Motor de inferencia LLM (Ollama local o vLLM en AKS) |

Cada servicio muestra su estado (`ok` / `error`) y latencia de respuesta en milisegundos.

---

## 5. Gestión de documentos

**Ruta:** `/documents`

Los documentos son la base del sistema. Deben subirse y procesarse antes de poder hacer consultas RAG o análisis de licitaciones.

### Flujo completo

```
1. Subir PDF  →  2. Procesar (chunking + embeddings)  →  3. Disponible para RAG
```

### 5.1 Subir un documento

**Endpoint:** `POST /api/v1/documents/upload`

Parámetros requeridos:
- `tender_id` — identificador de la licitación a la que pertenece el documento
- `file` — archivo PDF (multipart/form-data)

**Ejemplo con curl:**
```bash
curl -X POST http://procurement.local/api/v1/documents/upload \
  -F "tender_id=LICITACION-2026-001" \
  -F "file=@bases_licitacion.pdf"
```

**Respuesta:**
```json
{
  "document_id": "a1b2c3d4-...",
  "tender_id": "LICITACION-2026-001",
  "filename": "bases_licitacion.pdf",
  "minio_path": "documents/a1b2c3d4-.../bases_licitacion.pdf",
  "file_size": 204800
}
```

Guardar el `document_id` para el siguiente paso.

### 5.2 Procesar un documento

**Endpoint:** `POST /api/v1/documents/process?document_id={id}`

Extrae el texto del PDF, lo divide en chunks, genera embeddings y los indexa en Qdrant.

```bash
curl -X POST "http://procurement.local/api/v1/documents/process?document_id=a1b2c3d4-..."
```

**Respuesta:**
```json
{
  "document_id": "a1b2c3d4-...",
  "page_count": 45,
  "chunk_count": 180,
  "status": "processed"
}
```

> El procesamiento puede tardar entre 30 segundos y 3 minutos dependiendo del tamaño del PDF.

### 5.3 Consultar un documento

**Endpoint:** `GET /api/v1/documents/{document_id}`

```bash
curl http://procurement.local/api/v1/documents/a1b2c3d4-...
```

### Estados del documento

| Estado | Descripción |
|--------|-------------|
| `uploaded` | Subido, pendiente de procesar |
| `processing` | Extrayendo texto y generando embeddings |
| `processed` | Listo para consultas RAG |
| `error` | Falló el procesamiento |

---

## 6. Consulta RAG

**Ruta:** `/query`  
**Endpoint:** `POST /api/v1/rag/query`

Permite hacer preguntas en lenguaje natural sobre los documentos indexados. El sistema recupera los chunks más relevantes y genera una respuesta contextualizada.

### Parámetros de la consulta

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `question` | string | Pregunta en lenguaje natural |
| `tender_id` | string (opcional) | Filtrar por licitación específica |
| `document_id` | string (opcional) | Filtrar por documento específico |
| `top_k` | int (default: 5) | Número de chunks a recuperar |

### Ejemplo

```bash
curl -X POST http://procurement.local/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Cuáles son los requisitos técnicos mínimos para participar?",
    "tender_id": "LICITACION-2026-001",
    "top_k": 5
  }'
```

**Respuesta:**
```json
{
  "answer": "Según las bases, los requisitos técnicos mínimos son...",
  "question": "¿Cuáles son los requisitos técnicos mínimos para participar?",
  "sources": [
    {
      "chunk_id": "chunk-001",
      "document_id": "a1b2c3d4-...",
      "page_number": 12,
      "score": 0.94
    }
  ],
  "route": "large",
  "route_reason": "Query requires full context window"
}
```

El campo `route` indica si se usó el modo `small` (contexto reducido) o `large` (contexto completo) según la complejidad de la consulta.

---

## 7. Workflow multi-agente

**Ruta:** `/workflow`

El workflow orquesta tres agentes especializados en secuencia para producir un análisis completo de la licitación.

### Arquitectura del workflow

```
tender_id
    ↓
[Agente Legal]
    ↓ análisis de riesgos y obligaciones
[Agente de Propuesta]
    ↓ propuesta técnica y económica
[Agente de Auditoría]
    ↓ verificación de cumplimiento
[Reporte Final]
```

### 7.1 Análisis completo (recomendado)

**Endpoint:** `POST /api/v1/workflow/full-analysis`

Ejecuta los tres agentes en secuencia de forma automática.

```bash
curl -X POST http://procurement.local/api/v1/workflow/full-analysis \
  -H "Content-Type: application/json" \
  -d '{"tender_id": "LICITACION-2026-001"}'
```

**Respuesta:**
```json
{
  "workflow_id": "wf-uuid-...",
  "tender_id": "LICITACION-2026-001",
  "correlation_id": "corr-uuid-...",
  "status": "completed",
  "steps_completed": ["legal", "proposal", "audit", "report"],
  "errors": [],
  "final_report": {
    "legal_summary": "...",
    "proposal_outline": "...",
    "compliance_score": 0.92,
    ...
  }
}
```

> El análisis completo puede tomar entre **2 y 8 minutos** dependiendo del tamaño del documento y la carga del sistema.

### 7.2 Agentes individuales

Para casos donde se necesite ejecutar solo un paso del workflow:

**Agente Legal:**
```bash
curl -X POST http://procurement.local/api/v1/agents/legal \
  -H "Content-Type: application/json" \
  -d '{"tender_id": "LICITACION-2026-001"}'
```

**Agente de Propuesta** (requiere output del agente legal):
```bash
curl -X POST http://procurement.local/api/v1/agents/proposal \
  -H "Content-Type: application/json" \
  -d '{
    "tender_id": "LICITACION-2026-001",
    "legal_output": { ... }
  }'
```

**Agente de Auditoría** (requiere outputs de legal y propuesta):
```bash
curl -X POST http://procurement.local/api/v1/agents/audit \
  -H "Content-Type: application/json" \
  -d '{
    "tender_id": "LICITACION-2026-001",
    "legal_output": { ... },
    "proposal_output": { ... }
  }'
```

### 7.3 Consultar estado de un workflow

```bash
curl http://procurement.local/api/v1/workflow/{workflow_id}
```

### Estados del workflow

| Estado | Descripción |
|--------|-------------|
| `running` | En ejecución |
| `completed` | Finalizado exitosamente |
| `failed` | Falló durante la ejecución |

---

## 8. Reportes

**Ruta:** `/reports`  
**Endpoint:** `GET /api/v1/reports`

Permite consultar los reportes generados por workflows anteriores. Cada reporte consolidado incluye:

- Análisis legal (riesgos, cláusulas críticas, obligaciones)
- Borrador de propuesta técnica
- Score de cumplimiento normativo
- Recomendaciones del auditor

---

## 9. Análisis de costos

**Ruta:** `/cost`  
**Endpoint:** `GET /api/v1/cost/analysis`

Muestra métricas de consumo de tokens y proyecciones de costo para distintas configuraciones de infraestructura.

```bash
curl http://procurement.local/api/v1/cost/analysis
```

**Métricas incluidas:**

| Campo | Descripción |
|-------|-------------|
| `total_tokens` | Total de tokens procesados (input + output) |
| `avg_tokens_per_request` | Promedio de tokens por workflow ejecutado |
| `tokens_per_second_current` | Throughput actual del LLM |
| `cost_aks_gpu_per_1k_requests_usd` | Costo estimado por cada 1.000 solicitudes en T4 |

**Configuraciones comparadas:**

| Configuración | SKU | Uso |
|--------------|-----|-----|
| T4 Spot (actual dev) | `NC4as_T4_v3` Spot | Desarrollo y demos |
| T4 On-demand | `NC4as_T4_v3` Regular | Pre-producción |
| V100 On-demand | `NC6s_v3` | Producción alta carga |

---

## 10. API REST — Referencia rápida

**Base URL:** `http://{host}/api/v1`  
**Documentación interactiva (Swagger):** `http://{host}/docs`

### Tabla de endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/health` | Health check básico — versión y estado |
| `GET` | `/ready` | Readiness probe — verifica postgres, qdrant, storage, LLM |
| `GET` | `/status` | Estado extendido con latencias por servicio |
| `GET` | `/metrics` | Métricas Prometheus (formato scrape) |
| `POST` | `/documents/upload` | Subir documento PDF |
| `POST` | `/documents/process` | Procesar documento (chunking + embeddings) |
| `GET` | `/documents/{id}` | Consultar metadata de documento |
| `POST` | `/rag/query` | Consulta RAG en lenguaje natural |
| `POST` | `/workflow/full-analysis` | Ejecutar workflow completo (3 agentes) |
| `POST` | `/agents/legal` | Ejecutar solo agente legal |
| `POST` | `/agents/proposal` | Ejecutar solo agente de propuesta |
| `POST` | `/agents/audit` | Ejecutar solo agente de auditoría |
| `GET` | `/workflow/{id}` | Consultar estado de workflow |
| `GET` | `/cost/analysis` | Análisis de costos y tokens |

---

## 11. Monitoreo y observabilidad

### Grafana

Acceder a `http://172.19.137.191:30300` (Fase 4) con `admin` / `procurement123`.

Dashboards disponibles:

| Dashboard | Descripción |
|-----------|-------------|
| **API Performance** | Requests/s, latencia P50/P90/P99, error rate |
| **LLM Performance** | Tokens/s, tokens por solicitud, tiempo de inferencia |
| **Agents** | Ejecuciones por agente, tasa de éxito, Guardrail activaciones |
| **Infrastructure** | CPU, memoria, GPU utilization (DCGM), red |

### Métricas clave a monitorear

| Métrica Prometheus | Alerta si... |
|-------------------|-------------|
| `procurement_llm_tokens_per_second` | < 30 tok/s (posible problema de GPU) |
| `procurement_workflow_runs_total{status="failed"}` | > 5% del total |
| `http_request_duration_seconds{p99}` | > 30s (timeout de cliente) |
| `procurement_guardrail_blocks_total` | Spike repentino (posible abuso) |

---

## 12. Solución de problemas frecuentes

### El dashboard muestra servicios en `error`

1. Verificar que el cluster está activo: `kubectl get pods -n ai-platform`
2. Revisar logs del servicio fallido: `kubectl logs -n ai-platform deployment/{servicio}`
3. Si falla `vllm`/`ollama`, verificar que el nodo GPU tiene el modelo descargado

### El proceso de documento falla o se queda en `processing`

1. Confirmar que el PDF es legible (no escaneado sin OCR)
2. Verificar logs del api-gateway: `kubectl logs -n ai-platform deployment/api-gateway`
3. Revisar espacio en MinIO/Blob Storage

### El workflow tarda más de 10 minutos

- T4 con carga: throughput puede bajar a ~40 tok/s en concurrencia alta
- Verificar que no hay múltiples workflows corriendo en paralelo
- Revisar `/api/v1/cost/analysis` para ver el TPS actual

### Error `404` en `/api/v1/rag/query`

- El `tender_id` o `document_id` no existe o el documento no está en estado `processed`
- Verificar con `GET /api/v1/documents/{document_id}` que el status sea `processed`

### Error de autenticación en ACR (CI/CD)

Verificar que los siguientes secrets están configurados en GitHub:
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `ACR_NAME`
- `AKS_NAME`
- `AKS_RESOURCE_GROUP`

---

## Apéndice — Flujo de uso típico

```
1. Obtener bases de licitación (PDF)
          ↓
2. POST /documents/upload
   → guardar document_id
          ↓
3. POST /documents/process?document_id=...
   → esperar status "processed"
          ↓
4. (Opcional) POST /rag/query
   → preguntas puntuales sobre las bases
          ↓
5. POST /workflow/full-analysis
   → esperar "completed" (~5 min)
          ↓
6. Revisar final_report en la respuesta
   o consultar GET /reports
          ↓
7. Revisar GET /cost/analysis
   → validar consumo de tokens y costos
```
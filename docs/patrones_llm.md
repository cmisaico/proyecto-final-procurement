# Patrones de Diseño LLM — Autonomous Procurement Intelligence Platform

**Versión:** 3.0.0 | **Fecha:** Junio 2026

---

## Resumen

| # | Patrón | Propósito | Estado |
|---|--------|-----------|--------|
| 1 | Inference Router | Evitar la llamada al LLM en queries simples extrayendo la respuesta directamente del contexto recuperado | Implementado (`app/services/inference_router.py`) |
| 2 | Guardrail | Detección de prompt injection/jailbreak pre-LLM y cross-check de alucinaciones post-LLM con descarte del output si falla | Implementado (`app/services/guardrail_service.py`) |
| 3 | Efficient Context Handling | Chunking + Retrieval + Compresión + Ranking + Sliding Window | Implementado (`app/rag/pipeline.py`) |
| 4 | Continuous Batching | Maximizar throughput de vLLM con batching dinámico | Configurado en Helm chart de vLLM |

---

## Patrón 1: Inference Router

### Descripción

El Inference Router evalúa cada query antes de llamar al LLM y decide si la respuesta puede obtenerse directamente del contexto recuperado de Qdrant (path **SMALL**, ~10 ms, sin LLM) o si requiere generación completa por vLLM/Ollama (path **LARGE**, ~3-8 s).

No hay un "modelo pequeño en CPU" — el path rápido simplemente extrae la oración del contexto RAG con mayor solapamiento de keywords, sin ninguna inferencia neuronal.

### Lógica de decisión (`app/services/inference_router.py`)

```python
HIGH_SCORE_THRESHOLD = 0.92   # score mínimo Qdrant para fast path
SIMPLE_MAX_WORDS     = 12     # queries más largas van a LARGE

_COMPLEX_KEYWORDS = {
    "analiza", "compara", "evalúa", "explica", "resume",
    "riesgos", "requisitos", "estrategia", "recomendación", ...
}
_SIMPLE_PREFIXES = {
    "quién", "qué", "cuál", "cuándo", "dónde",   # español
    "who", "what", "which", "when", "where",       # inglés
}

def decide(self, query: str, top_scores: List[float]) -> RouterDecision:
    # 1. Keyword complejo → siempre LARGE
    for kw in self._COMPLEX_KEYWORDS:
        if kw in query.lower():
            return RouterDecision(route=Route.LARGE, ...)

    # 2. Query larga → LARGE
    if len(query.split()) > self.SIMPLE_MAX_WORDS:
        return RouterDecision(route=Route.LARGE, ...)

    # 3. Prefix simple + alta confianza Qdrant → SMALL (sin LLM)
    if starts_simple and max(top_scores) >= self.HIGH_SCORE_THRESHOLD:
        return RouterDecision(route=Route.SMALL, ...)

    # 4. Default → LARGE
    return RouterDecision(route=Route.LARGE, ...)
```

En el path SMALL, `extract_answer()` busca la oración del contexto con mayor solapamiento de palabras clave con la query — sin ninguna llamada de red ni inferencia.

### Impacto medido

| Métrica | Sin router (todo LLM) | Con router |
|---------|----------------------|------------|
| Latencia queries simples | ~3-8 s | ~10 ms |
| Latencia queries complejos | ~3-8 s | ~3-8 s (sin cambio) |
| Llamadas a vLLM evitadas | 0% | ~25-35% (queries factuales) |
| Costo GPU por esas queries | $0.002/req | ~$0.00001/req |

### Ventajas / Desventajas

**Ventajas:** Reducción drástica de latencia y costo en queries factuales simples; no requiere mantener un segundo modelo; lógica determinista y auditable.

**Desventajas:** El clasificador puede enrutar mal queries ambiguas (~5-10%); `extract_answer()` es extractivo, no generativo — no reformula la respuesta; solo funciona cuando Qdrant devuelve chunks con score ≥ 0.92.

---

## Patrón 2: Guardrail

### Descripción
El Guardrail opera en dos etapas secuenciales: **pre-LLM** (`validate_input`) y **post-LLM** (`validate`). Implementado en `app/services/guardrail_service.py` y aplicado en el endpoint RAG y en los tres agentes LangGraph (Legal, Proposal, Audit).

### Etapa 1 — Validación de entrada pre-LLM (`guardrail_service.py:validate_input`)

Antes de que la query llegue al LLM, se evalúa contra una lista de patrones regex compilados que detectan prompt injection y jailbreak:

```python
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above|prior)\s+instructions",
    r"forget\s+(everything|all|your|previous)",
    r"\bsystem\s*prompt\b",
    r"\byou\s+are\s+now\b",
    r"\bjailbreak\b",
    r"bypass\s+(your|all|the)\s+(restrictions|rules|filters)",
    r"ignora\s+(las|todas\s+las|tus)\s+(instrucciones|restricciones)",
    r"actúa\s+como\s+(si|un|una)\b",
    # ... 14 patrones en total (español + inglés)
]
```

Si hay match → `HTTP 400` inmediato, la query nunca llega al modelo. Se registra en el log con el patrón detectado y los primeros 120 caracteres de la query.

### Etapa 2 — Validación de salida post-LLM (`guardrail_service.py:validate`)

Después de que el LLM genera la respuesta, se verifica que sus afirmaciones estén respaldadas por los chunks recuperados de Qdrant:

```python
# 1. Dividir la respuesta en oraciones (máx 20)
claims = _extract_claims(response_text)

# 2. Por cada oración: ¿el 40% de sus palabras clave aparecen en el corpus de chunks?
for claim in claims:
    supported += _is_supported(claim, context_corpus)   # keyword overlap, no embeddings

# 3. Score combinado
score = (supported / total_claims) * 0.7 + (avg_qdrant_score) * 0.3

# 4. Decisión
passed = score >= GUARDRAIL_THRESHOLD   # 0.35
```

Si `passed = False` → el output del LLM se **descarta**. El agente devuelve el `_fallback_output()` (respuesta vacía estructurada) en lugar de la posible alucinación.

La respuesta siempre incluye el campo `guardrail` con el resultado:

```json
{
  "output": { ... },
  "guardrail": {
    "passed": false,
    "score": 0.28,
    "flagged_claims": ["la multa es del 15% del contrato total"],
    "message": "Low consistency (0.28 < 0.35)"
  }
}
```

### Configuración

```python
# app/core/config.py
GUARDRAIL_THRESHOLD: float = 0.35   # score mínimo para aceptar el output del LLM
```

### Ventajas / Desventajas

**Ventajas:** Detección determinista de injection (sin falsos negativos en patrones conocidos); descarte real del output alucinado (no solo flag); sin latencia de embeddings (keyword overlap es O(n) en texto plano).

**Desventajas:** Los patrones regex no detectan ataques semánticamente equivalentes que evitan las palabras clave; el keyword overlap es menos preciso que similitud coseno — un threshold bajo (0.35) es necesario para evitar falsos positivos en respuestas legítimas largas; no detecta PII.

### Impacto

| Métrica | Valor |
|---------|-------|
| Latencia validación de entrada | < 1 ms (regex compilado) |
| Latencia validación de salida | ~5-15 ms (string matching) |
| Threshold actual | 0.35 |
| Usado en | `/api/v1/rag/query`, LegalAgent, ProposalAgent, AuditAgent |

---

## Patrón 3: Efficient Context Handling

### Descripción

Gestión inteligente del contexto para maximizar la calidad de respuesta minimizando tokens enviados al LLM. Implementado en `app/services/context_handler.py` (`EfficientContextHandler`) y usado por los tres agentes LangGraph. El pipeline RAG directo (`app/rag/pipeline.py`) usa una variante simplificada con `qdrant_store.search()`.

### Pipeline implementado (`context_handler.py`)

```
Documento PDF
    │
    ▼ [1. Chunking — en procesamiento de documentos]
    chunks de 1,000 tokens con 200 tokens de overlap
    (CHUNK_SIZE / CHUNK_OVERLAP en config.py)
    │
    ▼ [2. Embedding — EmbeddingService]
    nomic-embed-text → vectores 768-dim
    (EMBEDDINGS_MODEL / EMBEDDING_DIMENSION en config.py)
    │
    ▼ [3. Indexación en Qdrant]
    HNSW index — búsqueda aproximada O(log n)
    │
    ▼ [4. Retrieval — retrieve() / retrieve_multi()]
    Top-k chunks por similitud coseno
    Ordenados por score descendente
    │
    ▼ [5. Token budget enforcement]
    Acumula chunks mientras token_used < MAX_CONTEXT_TOKENS
    Si un chunk no cabe: truncación parcial por caracteres
    Si quedan < 50 tokens: corte duro (break)
    │
    ▼ [6. Deduplicación + re-ranking (solo retrieve_multi)]
    Queries múltiples → seen_contents dedup → sort by score
    │
    ▼ [7. LLM]
    Contexto dentro del budget enviado a vLLM/Ollama
```

### Configuración

```python
# app/core/config.py
CHUNK_SIZE: int = 1000
CHUNK_OVERLAP: int = 200
CONTEXT_TOP_K: int = 10
MAX_CONTEXT_TOKENS: int = 4000
EMBEDDINGS_MODEL: str = "nomic-embed-text"
EMBEDDING_DIMENSION: int = 768
```

### Qué NO está implementado

| Lo que se suele describir | Realidad en este proyecto |
|--------------------------|--------------------------|
| Compresión extractiva de oraciones | No existe — el paso 5 es truncación de texto por caracteres, no extracción de frases relevantes |
| Sliding window | No existe — hay un corte duro cuando se acaba el token budget |

### Impacto en tokens

| Etapa | Tokens aprox. | Reducción |
|-------|--------------|-----------|
| Documento original (50 pág) | ~50,000 | — |
| Retrieval top-10 chunks | ~5,000 | 90% |
| Post token budget (4,000 tok) | ≤ 4,000 | 92% |

### Chunked prefill de vLLM

Con `--enable-chunked-prefill` (activo en el chart), vLLM divide los prefills largos en chunks procesados en pasos sucesivos. Esto reduce la latencia del primer token (TTFT) cuando hay requests concurrentes, evitando que un prefill largo monopolice el GPU. `--enable-prefix-caching` no está configurado actualmente.

---

## Patrón 4: Continuous Batching

### Descripción

vLLM implementa continuous batching nativo (in-flight batching): en lugar de esperar a que un batch completo termine, agrega nuevos requests al batch en progreso. Esto maximiza la utilización del GPU.

### Diferencia clave vs static batching

| Característica | Static Batching | Continuous Batching (vLLM) |
|----------------|-----------------|----------------------------|
| Cuándo acepta nuevo request | Al terminar el batch completo | En cada step de decodificación |
| Latencia primer token | Baja | Similar |
| GPU utilization | 20-40% | 85-95% |
| Throughput | ~200 tok/s | ~1,100 tok/s |
| Cambio en código app | No | No (transparente) |

### Parámetros configurados (`k8s/charts/vllm/values.yaml` → `deployment.yaml`)

```yaml
# Valores reales pasados como args al proceso vLLM
--max-num-seqs 256             # máx secuencias concurrentes en el scheduler
--max-num-batched-tokens 8192  # tokens máximos por step de forward pass
--gpu-memory-utilization 0.85  # 85% de VRAM para modelo + KV cache
--enable-chunked-prefill       # divide prefills largos en chunks → menor TTFT
--quantization awq             # cuantización AWQ 4-bit
--max-model-len 8192           # longitud máxima de secuencia
```

**No configurados** (no están en el values actual): `--enable-prefix-caching`, `--swap-space`.

### Tabla de rendimiento por batch size

| Batch Size | Tokens/s | Latencia P50 | GPU Util % | Recomendado para |
|-----------|----------|-------------|-----------|------------------|
| 1 | ~200 | ~500 ms | ~20% | Testing individual |
| 4 | ~600 | ~800 ms | ~55% | Dev / baja carga |
| 8 | ~900 | ~1,200 ms | ~75% | Carga media |
| 16 | ~1,100 | ~2,000 ms | ~85% | **Sweet spot (licitaciones)** |
| 32 | ~1,200 | ~3,500 ms | ~90% | Alta carga |
| 64 | ~1,200 | ~6,000 ms | ~92% | Throughput máximo |

El sweet spot para el caso de uso de licitaciones (requests ~500 tokens) es **batch size 16-32**, que balancea throughput y latencia aceptable.

### Impacto en autoscaling

- Un solo T4 con continuous batching soporta ~600 tok/s (AWQ)
  - Para >600 tok/s sostenido → escalar manualmente un segundo pod vLLM (o via KEDA cuando se despliegue)
  - El HPA de vLLM está deshabilitado (`hpa.enabled: false`); el escalado actual es manual

---

## Relación entre patrones

```
Request entrante
      │
      ▼
[Inference Router] ──────────────────────────────────► SMALL: extract_answer() sin LLM (~10 ms)
      │ keyword complejo / query larga / score Qdrant < 0.92
      ▼
[Input Guardrail — validate_input()]
  ├── Regex injection/jailbreak (14 patrones)
  └── HTTP 400 si hay match → query descartada
      │ input OK
      ▼
[Efficient Context Handler]
  ├── Retrieval top-k de Qdrant (nomic-embed-text 768-dim)
  ├── Deduplicación + sort by score (retrieve_multi)
  └── Token budget enforcement (≤ 4,000 tokens, truncación)
      │ contexto listo
      ▼
[vLLM — Continuous Batching]
  └── Inferencia en GPU (max 256 seqs, 8192 tok/step)
      │ respuesta generada
      ▼
[Output Guardrail — validate()]
  └── Keyword overlap cross-check (score ≥ 0.35)
      ├── passed → respuesta enviada al usuario
      └── failed → _fallback_output() (LLM output descartado)
      │ output OK
      ▼
Respuesta al usuario
```
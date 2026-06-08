"""
Prometheus metrics registry — Fase 3 LLMOps.
All counters/histograms/gauges used across the platform.
"""
from prometheus_client import Counter, Gauge, Histogram, Info, REGISTRY

# ── API metrics ─────────────────────────────────────────────────────────────

HTTP_REQUESTS_TOTAL = Counter(
    "procurement_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION = Histogram(
    "procurement_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

HTTP_REQUESTS_ACTIVE = Gauge(
    "procurement_http_requests_active",
    "Number of active HTTP requests",
)

HTTP_ERRORS_TOTAL = Counter(
    "procurement_http_errors_total",
    "Total HTTP errors",
    ["method", "endpoint", "status_code"],
)

# ── LLM metrics ─────────────────────────────────────────────────────────────

LLM_TOKENS_TOTAL = Counter(
    "procurement_llm_tokens_total",
    "Total LLM tokens processed",
    ["model", "token_type"],  # token_type: input | output
)

LLM_INFERENCE_DURATION = Histogram(
    "procurement_llm_inference_seconds",
    "LLM inference duration in seconds",
    ["model", "operation"],  # operation: generate | embed
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 80.0, 120.0],
)

LLM_TOKENS_PER_SECOND = Gauge(
    "procurement_llm_tokens_per_second",
    "LLM output tokens per second (last request)",
    ["model"],
)

# ── RAG / Retrieval metrics ─────────────────────────────────────────────────

RETRIEVAL_DURATION = Histogram(
    "procurement_retrieval_seconds",
    "Vector retrieval duration in seconds",
    ["operation"],  # operation: embed_query | qdrant_search | full_retrieval
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

RETRIEVAL_CHUNKS_RETURNED = Histogram(
    "procurement_retrieval_chunks_returned",
    "Number of chunks returned per retrieval",
    buckets=[1, 2, 3, 5, 10, 15, 20],
)

# ── Agent metrics ───────────────────────────────────────────────────────────

AGENT_DURATION = Histogram(
    "procurement_agent_duration_seconds",
    "Agent execution duration in seconds",
    ["agent_name"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

AGENT_ERRORS_TOTAL = Counter(
    "procurement_agent_errors_total",
    "Total agent errors",
    ["agent_name"],
)

AGENT_RUNS_TOTAL = Counter(
    "procurement_agent_runs_total",
    "Total agent runs",
    ["agent_name", "status"],  # status: success | error
)

AGENT_REQUIREMENTS_DETECTED = Histogram(
    "procurement_agent_requirements_detected",
    "Number of requirements detected by legal agent",
    buckets=[0, 1, 2, 5, 10, 20, 50],
)

AGENT_PROPOSAL_LENGTH = Histogram(
    "procurement_agent_proposal_chars",
    "Proposal executive summary length in characters",
    buckets=[100, 500, 1000, 2000, 5000],
)

AGENT_COMPLIANCE_SCORE = Histogram(
    "procurement_agent_compliance_score",
    "Compliance score distribution",
    ["risk_level"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

AGENT_GUARDRAIL_SCORE = Histogram(
    "procurement_agent_guardrail_score",
    "Guardrail validation score",
    ["agent_name"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ── Workflow metrics ─────────────────────────────────────────────────────────

WORKFLOW_DURATION = Histogram(
    "procurement_workflow_duration_seconds",
    "Full workflow execution duration",
    buckets=[10, 30, 60, 120, 300, 600],
)

WORKFLOW_RUNS_TOTAL = Counter(
    "procurement_workflow_runs_total",
    "Total workflow executions",
    ["status"],  # status: completed | failed
)

# ── Cost metrics ────────────────────────────────────────────────────────────

COST_TOKENS_TOTAL = Counter(
    "procurement_cost_tokens_total",
    "Cumulative token usage for cost tracking",
    ["model"],
)

COST_ESTIMATED_USD = Gauge(
    "procurement_cost_estimated_usd",
    "Estimated cumulative cost in USD equivalent",
)

# ── App info ────────────────────────────────────────────────────────────────

APP_INFO = Info(
    "procurement_app",
    "Application information",
)
APP_INFO.info({
    "version": "3.0.0",
    "phase": "fase03",
    "llm_model": "qwen2.5:7b",
    "embed_model": "nomic-embed-text",
})

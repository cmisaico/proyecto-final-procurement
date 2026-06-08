"""
Cost Analysis API — Fase 3 LLMOps.
Provides token usage, cost estimates local vs AKS vs vLLM.
"""
from typing import Any, Dict, List

from fastapi import APIRouter
from prometheus_client import REGISTRY
from pydantic import BaseModel

router = APIRouter(prefix="/cost", tags=["cost analysis"])

# AKS pricing (East US, 2024 approx)
AKS_COST_PER_HOUR = {
    "D4s_v3":  0.192,   # 4 vCPU, 16GB RAM  (CPU backend)
    "NC6s_v3": 3.060,   # 1x V100, 6 vCPU  (GPU vLLM)
}
VLLM_TOKENS_PER_SEC = 150  # qwen2.5:7b on V100
OLLAMA_TOKENS_PER_SEC = 12  # qwen2.5:7b on CPU (measured)


class CostReport(BaseModel):
    total_tokens: int
    input_tokens: int
    output_tokens: int
    avg_tokens_per_request: float
    tokens_per_second_current: float
    cost_local_usd: float
    cost_aks_cpu_per_1k_requests_usd: float
    cost_aks_gpu_per_1k_requests_usd: float
    cost_vllm_per_1k_requests_usd: float
    recommendations: List[str]
    breakdown: Dict[str, Any]


@router.get("/analysis", response_model=CostReport)
async def cost_analysis():
    """Return token usage and cost projections for local, AKS CPU, and vLLM."""

    # Read from Prometheus registry
    total_in = _get_counter("procurement_llm_tokens_total", {"token_type": "input"})
    total_out = _get_counter("procurement_llm_tokens_total", {"token_type": "output"})
    total = total_in + total_out

    wf_runs = _get_counter("procurement_workflow_runs_total", {"status": "completed"})
    avg_per_req = (total / max(wf_runs, 1))

    # Current: Ollama CPU speed
    tps = _get_gauge("procurement_llm_tokens_per_second")

    # ── Cost projections ─────────────────────────────────────────────────
    # Local: no monetary cost, but track CPU time
    # Each request: ~avg_per_req / 12 tps = ~X seconds of CPU
    seconds_per_req = avg_per_req / max(tps, OLLAMA_TOKENS_PER_SEC)
    local_cpu_seconds_per_1k = seconds_per_req * 1000

    # AKS CPU (D4s_v3): $0.192/hour = $0.0000533/s
    aks_cpu_per_1k = local_cpu_seconds_per_1k * (AKS_COST_PER_HOUR["D4s_v3"] / 3600)

    # AKS GPU (NC6s_v3 + vLLM): vLLM is ~12.5x faster
    vllm_seconds_per_req = avg_per_req / VLLM_TOKENS_PER_SEC
    aks_gpu_per_1k = vllm_seconds_per_req * 1000 * (AKS_COST_PER_HOUR["NC6s_v3"] / 3600)

    recommendations = []
    if tps < 5:
        recommendations.append("Consider migrating to vLLM on GPU: ~12x throughput improvement.")
    if avg_per_req > 2000:
        recommendations.append("Reduce MAX_CONTEXT_TOKENS to lower token usage per request.")
    if wf_runs > 100:
        recommendations.append("High workflow volume detected. AKS HPA recommended for autoscaling.")
    if not recommendations:
        recommendations.append("System operating within normal parameters.")

    return CostReport(
        total_tokens=int(total),
        input_tokens=int(total_in),
        output_tokens=int(total_out),
        avg_tokens_per_request=round(avg_per_req, 1),
        tokens_per_second_current=round(tps, 1),
        cost_local_usd=0.0,
        cost_aks_cpu_per_1k_requests_usd=round(aks_cpu_per_1k, 4),
        cost_aks_gpu_per_1k_requests_usd=round(aks_gpu_per_1k, 4),
        cost_vllm_per_1k_requests_usd=round(aks_gpu_per_1k, 4),
        recommendations=recommendations,
        breakdown={
            "ollama_cpu": {
                "model": "qwen2.5:7b",
                "tokens_per_second": OLLAMA_TOKENS_PER_SEC,
                "seconds_per_request": round(seconds_per_req, 2),
                "cost_per_request_usd": 0.0,
            },
            "aks_d4s_v3": {
                "hourly_rate_usd": AKS_COST_PER_HOUR["D4s_v3"],
                "cost_per_1k_requests_usd": round(aks_cpu_per_1k, 4),
            },
            "aks_nc6s_v3_vllm": {
                "hourly_rate_usd": AKS_COST_PER_HOUR["NC6s_v3"],
                "vllm_tokens_per_second": VLLM_TOKENS_PER_SEC,
                "cost_per_1k_requests_usd": round(aks_gpu_per_1k, 4),
                "speedup_vs_cpu": f"{VLLM_TOKENS_PER_SEC/OLLAMA_TOKENS_PER_SEC:.1f}x",
            },
        },
    )


def _get_counter(metric_name: str, labels: Dict[str, str]) -> float:
    try:
        for metric in REGISTRY.collect():
            if metric.name == metric_name:
                for sample in metric.samples:
                    if all(sample.labels.get(k) == v for k, v in labels.items()):
                        return sample.value
    except Exception:
        pass
    return 0.0


def _get_gauge(metric_name: str) -> float:
    try:
        for metric in REGISTRY.collect():
            if metric.name == metric_name:
                for sample in metric.samples:
                    return sample.value
    except Exception:
        pass
    return OLLAMA_TOKENS_PER_SEC

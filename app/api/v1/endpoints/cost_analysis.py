"""
Cost Analysis API — Fase 3 LLMOps.
Queries Prometheus HTTP API to aggregate metrics across all pods.
"""
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/cost", tags=["cost analysis"])

AKS_COST_PER_HOUR = {
    "D4s_v3":           0.192,
    "NC4as_T4_v3":      0.526,
    "NC4as_T4_v3_spot": 0.158,
    "NC6s_v3":          3.060,
}

VLLM_TOKENS_PER_SEC_T4   = 90
VLLM_TOKENS_PER_SEC_V100 = 150


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
    prometheus_available: bool = True


@router.get("/analysis", response_model=CostReport)
async def cost_analysis():
    total_in,  ok1 = await _prom_query('sum(procurement_llm_tokens_total{token_type="input"})')
    total_out, ok2 = await _prom_query('sum(procurement_llm_tokens_total{token_type="output"})')
    prometheus_available = ok1 or ok2
    total     = total_in + total_out

    wf_runs, _  = await _prom_query('sum(procurement_workflow_runs_total{status="completed"})')
    avg_per_req = total / max(wf_runs, 1)

    tps, _ = await _prom_query("max(procurement_llm_tokens_per_second)")
    tps = tps or VLLM_TOKENS_PER_SEC_T4

    seconds_per_req_t4   = avg_per_req / max(tps, VLLM_TOKENS_PER_SEC_T4)
    seconds_per_req_v100 = avg_per_req / VLLM_TOKENS_PER_SEC_V100

    t4_spot_per_1k     = seconds_per_req_t4   * 1000 * (AKS_COST_PER_HOUR["NC4as_T4_v3_spot"] / 3600)
    t4_ondemand_per_1k = seconds_per_req_t4   * 1000 * (AKS_COST_PER_HOUR["NC4as_T4_v3"]      / 3600)
    v100_per_1k        = seconds_per_req_v100 * 1000 * (AKS_COST_PER_HOUR["NC6s_v3"]           / 3600)

    recommendations = []
    if tps < 30:
        recommendations.append("Throughput below 30 tok/s — verify vLLM AWQ quantization is active on T4.")
    if avg_per_req > 2000:
        recommendations.append("Avg tokens/request > 2 000 — consider reducing MAX_CONTEXT_TOKENS.")
    if wf_runs > 100:
        recommendations.append("High workflow volume — review AKS HPA settings for the api-gateway node pool.")
    if t4_spot_per_1k > 0.05:
        recommendations.append("Cost per 1k requests exceeding $0.05 — evaluate NC6s_v3 for higher throughput.")
    if not recommendations:
        recommendations.append("System operating within normal parameters on AKS T4 Spot.")

    return CostReport(
        prometheus_available=prometheus_available,
        total_tokens=int(total),
        input_tokens=int(total_in),
        output_tokens=int(total_out),
        avg_tokens_per_request=round(avg_per_req, 1),
        tokens_per_second_current=round(tps, 1),
        cost_local_usd=0.0,
        cost_aks_cpu_per_1k_requests_usd=round(t4_ondemand_per_1k, 4),
        cost_aks_gpu_per_1k_requests_usd=round(v100_per_1k, 4),
        cost_vllm_per_1k_requests_usd=round(t4_spot_per_1k, 4),
        recommendations=recommendations,
        breakdown={
            "t4_spot_current": {
                "node": "Standard_NC4as_T4_v3 (Spot)",
                "hourly_rate_usd": AKS_COST_PER_HOUR["NC4as_T4_v3_spot"],
                "model": "Qwen2.5-7B-Instruct-AWQ",
                "tokens_per_second": VLLM_TOKENS_PER_SEC_T4,
                "cost_per_1k_requests_usd": round(t4_spot_per_1k, 4),
            },
            "t4_ondemand": {
                "node": "Standard_NC4as_T4_v3 (On-demand)",
                "hourly_rate_usd": AKS_COST_PER_HOUR["NC4as_T4_v3"],
                "model": "Qwen2.5-7B-Instruct-AWQ",
                "tokens_per_second": VLLM_TOKENS_PER_SEC_T4,
                "cost_per_1k_requests_usd": round(t4_ondemand_per_1k, 4),
            },
            "nc6s_v3_production": {
                "node": "Standard_NC6s_v3 (On-demand)",
                "hourly_rate_usd": AKS_COST_PER_HOUR["NC6s_v3"],
                "model": "Qwen2.5-7B-Instruct (FP16)",
                "tokens_per_second": VLLM_TOKENS_PER_SEC_V100,
                "cost_per_1k_requests_usd": round(v100_per_1k, 4),
            },
        },
    )


async def _prom_query(promql: str) -> tuple[float, bool]:
    """Query Prometheus HTTP API. Returns (value, data_available)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.PROMETHEUS_URL}/api/v1/query",
                params={"query": promql},
            )
            data = resp.json()
            results = data.get("data", {}).get("result", [])
            if results:
                return float(results[0]["value"][1]), True
    except Exception:
        pass
    return 0.0, False

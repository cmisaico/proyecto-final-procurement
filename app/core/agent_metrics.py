"""
Thin metrics wrappers for agent calls.
Used by supervisor_agent to record per-agent timing and outcomes.
"""
import time
from typing import Any, Callable, Dict, Optional
import tiktoken

from app.core.metrics import (
    AGENT_COMPLIANCE_SCORE,
    AGENT_DURATION,
    AGENT_ERRORS_TOTAL,
    AGENT_GUARDRAIL_SCORE,
    AGENT_PROPOSAL_LENGTH,
    AGENT_REQUIREMENTS_DETECTED,
    AGENT_RUNS_TOTAL,
    LLM_INFERENCE_DURATION,
    LLM_TOKENS_PER_SECOND,
    LLM_TOKENS_TOTAL,
    RETRIEVAL_CHUNKS_RETURNED,
    RETRIEVAL_DURATION,
    WORKFLOW_DURATION,
    WORKFLOW_RUNS_TOTAL,
    COST_TOKENS_TOTAL,
    COST_ESTIMATED_USD,
)
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    _enc = tiktoken.get_encoding("cl100k_base")
except Exception:
    _enc = None


def count_tokens(text: str) -> int:
    if _enc and text:
        return len(_enc.encode(text))
    return len(text) // 4


def record_llm_call(
    prompt: str,
    response: str,
    duration_seconds: float,
    model: str = None,
    operation: str = "generate",
) -> Dict[str, Any]:
    model = model or settings.OLLAMA_LLM_MODEL
    input_tokens = count_tokens(prompt)
    output_tokens = count_tokens(response)

    LLM_TOKENS_TOTAL.labels(model=model, token_type="input").inc(input_tokens)
    LLM_TOKENS_TOTAL.labels(model=model, token_type="output").inc(output_tokens)
    LLM_INFERENCE_DURATION.labels(model=model, operation=operation).observe(duration_seconds)
    COST_TOKENS_TOTAL.labels(model=model).inc(input_tokens + output_tokens)

    if duration_seconds > 0:
        tps = output_tokens / duration_seconds
        LLM_TOKENS_PER_SECOND.labels(model=model).set(tps)

    # Rough cost estimate: 0 locally, but track for AKS projection
    # AKS GPU cost: ~$0.0002 per 1K tokens
    estimated_cost = (input_tokens + output_tokens) / 1000 * 0.0002
    COST_ESTIMATED_USD.inc(estimated_cost)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "tokens_per_second": round(output_tokens / max(duration_seconds, 0.001), 1),
        "duration_seconds": round(duration_seconds, 3),
    }


def record_retrieval(chunks: int, duration_seconds: float, operation: str = "full_retrieval") -> None:
    RETRIEVAL_DURATION.labels(operation=operation).observe(duration_seconds)
    RETRIEVAL_CHUNKS_RETURNED.observe(chunks)


def record_agent_run(
    agent_name: str,
    duration_seconds: float,
    success: bool,
    guardrail_score: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    AGENT_DURATION.labels(agent_name=agent_name).observe(duration_seconds)
    AGENT_RUNS_TOTAL.labels(agent_name=agent_name, status="success" if success else "error").inc()

    if not success:
        AGENT_ERRORS_TOTAL.labels(agent_name=agent_name).inc()

    if guardrail_score is not None:
        AGENT_GUARDRAIL_SCORE.labels(agent_name=agent_name).observe(guardrail_score)

    if extra:
        if "requirements_count" in extra:
            AGENT_REQUIREMENTS_DETECTED.observe(extra["requirements_count"])
        if "proposal_length" in extra:
            AGENT_PROPOSAL_LENGTH.observe(extra["proposal_length"])
        if "compliance_score" in extra and "risk_level" in extra:
            AGENT_COMPLIANCE_SCORE.labels(risk_level=extra["risk_level"]).observe(
                extra["compliance_score"]
            )


def record_workflow(duration_seconds: float, success: bool) -> None:
    WORKFLOW_DURATION.observe(duration_seconds)
    WORKFLOW_RUNS_TOTAL.labels(status="completed" if success else "failed").inc()

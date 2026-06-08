"""
Thin metrics wrappers for agent calls.
Used by supervisor_agent to record per-agent timing and outcomes.
"""
import time
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

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


class PrometheusLLMCallback(BaseCallbackHandler):
    """LangChain callback that records token usage and throughput to Prometheus on every LLM call."""

    def __init__(self) -> None:
        super().__init__()
        self._start_times: Dict[str, float] = {}

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._start_times[str(run_id)] = time.perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        duration = time.perf_counter() - self._start_times.pop(str(run_id), time.perf_counter())
        model = (response.llm_output or {}).get("model_name", settings.VLLM_MODEL)
        usage = (response.llm_output or {}).get("token_usage", {})

        input_tokens  = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        if not input_tokens and not output_tokens:
            # vLLM occasionally omits usage; fall back to character estimate
            all_text = " ".join(
                gen.text for gens in response.generations for gen in gens if hasattr(gen, "text")
            )
            output_tokens = max(len(all_text) // 4, 1)

        LLM_TOKENS_TOTAL.labels(model=model, token_type="input").inc(input_tokens)
        LLM_TOKENS_TOTAL.labels(model=model, token_type="output").inc(output_tokens)
        LLM_INFERENCE_DURATION.labels(model=model, operation="generate").observe(duration)
        COST_TOKENS_TOTAL.labels(model=model).inc(input_tokens + output_tokens)

        if duration > 0 and output_tokens > 0:
            LLM_TOKENS_PER_SECOND.labels(model=model).set(output_tokens / duration)

        estimated_cost = (input_tokens + output_tokens) / 1000 * 0.0002
        COST_ESTIMATED_USD.inc(estimated_cost)

    def on_llm_error(
        self, error: Union[Exception, KeyboardInterrupt], *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._start_times.pop(str(run_id), None)


# Singleton — one instance shared across all LLM calls
prometheus_llm_callback = PrometheusLLMCallback()


def record_llm_call(
    prompt: str,
    response: str,
    duration_seconds: float,
    model: str = None,
    operation: str = "generate",
) -> Dict[str, Any]:
    model = model or settings.VLLM_MODEL
    input_tokens  = max(len(prompt) // 4, 1)
    output_tokens = max(len(response) // 4, 1)

    LLM_TOKENS_TOTAL.labels(model=model, token_type="input").inc(input_tokens)
    LLM_TOKENS_TOTAL.labels(model=model, token_type="output").inc(output_tokens)
    LLM_INFERENCE_DURATION.labels(model=model, operation=operation).observe(duration_seconds)
    COST_TOKENS_TOTAL.labels(model=model).inc(input_tokens + output_tokens)

    if duration_seconds > 0:
        LLM_TOKENS_PER_SECOND.labels(model=model).set(output_tokens / duration_seconds)

    COST_ESTIMATED_USD.inc((input_tokens + output_tokens) / 1000 * 0.0002)

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

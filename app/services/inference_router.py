import re
from dataclasses import dataclass
from enum import Enum
from typing import List

from app.core.logging import get_logger

logger = get_logger(__name__)


class Route(str, Enum):
    SMALL = "small"   # fast path: extract answer from context, no LLM call
    LARGE = "large"   # full path: LLM inference with full context


@dataclass
class RouterDecision:
    route: Route
    reason: str
    confidence: float


class InferenceRouter:
    """
    Inference Router Pattern:
    - SMALL path: simple factual queries with high-confidence retrieval → extract
      answer directly from top context chunk (no LLM, ~10ms latency)
    - LARGE path: analytical / multi-step queries → full vLLM inference
      (Qwen2.5-7B-AWQ, ~3-8s latency)

    Routing criteria (evaluated in order, first match wins):
    1. High retrieval score (>= 0.92) + short factual query → SMALL
    2. Complex-intent keywords detected → LARGE
    3. Long query (> 15 words) → LARGE
    4. Default → LARGE
    """

    # Queries starting with these words are usually simple single-fact lookups
    _SIMPLE_PREFIXES = {
        # Spanish
        "quién", "quien", "qué", "que", "cuál", "cual",
        "cuándo", "cuando", "dónde", "donde", "cuánto", "cuanto",
        # English
        "who", "what", "which", "when", "where", "how many", "how much",
    }

    # If any of these words appear, the query needs reasoning → LARGE
    _COMPLEX_KEYWORDS = {
        # Spanish
        "analiza", "analizar", "compara", "comparar", "evalúa", "evaluar",
        "explica", "explicar", "resume", "resumir", "describe", "describir",
        "lista", "listar", "identifica", "identificar", "propón", "proponer",
        "riesgos", "requisitos", "obligaciones", "diferencia", "ventajas",
        "estrategia", "recomendación", "resumen ejecutivo",
        # English
        "analyze", "compare", "evaluate", "explain", "summarize", "describe",
        "identify", "list all", "risks", "requirements", "obligations",
        "differences", "advantages", "strategy", "recommendation",
    }

    HIGH_SCORE_THRESHOLD: float = 0.92
    SIMPLE_MAX_WORDS: int = 12

    def decide(self, query: str, top_scores: List[float]) -> RouterDecision:
        query_lower = query.strip().lower()
        word_count = len(query_lower.split())
        top_score = max(top_scores) if top_scores else 0.0

        # 1. Complex keywords → always LARGE
        for kw in self._COMPLEX_KEYWORDS:
            if kw in query_lower:
                decision = RouterDecision(
                    route=Route.LARGE,
                    reason=f"complex keyword detected: '{kw}'",
                    confidence=0.95,
                )
                logger.info("InferenceRouter", extra={"route": decision.route, "reason": decision.reason})
                return decision

        # 2. Long query → LARGE
        if word_count > self.SIMPLE_MAX_WORDS:
            decision = RouterDecision(
                route=Route.LARGE,
                reason=f"long query ({word_count} words > {self.SIMPLE_MAX_WORDS})",
                confidence=0.85,
            )
            logger.info("InferenceRouter", extra={"route": decision.route, "reason": decision.reason})
            return decision

        # 3. High retrieval confidence + simple factual prefix → SMALL
        starts_simple = any(query_lower.startswith(p) for p in self._SIMPLE_PREFIXES)
        if starts_simple and top_score >= self.HIGH_SCORE_THRESHOLD:
            decision = RouterDecision(
                route=Route.SMALL,
                reason=f"simple factual query (score={top_score:.3f} >= {self.HIGH_SCORE_THRESHOLD})",
                confidence=top_score,
            )
            logger.info("InferenceRouter", extra={"route": decision.route, "reason": decision.reason})
            return decision

        # 4. Default → LARGE
        decision = RouterDecision(
            route=Route.LARGE,
            reason="default: no fast-path criteria met",
            confidence=0.70,
        )
        logger.info("InferenceRouter", extra={"route": decision.route, "reason": decision.reason})
        return decision

    @staticmethod
    def extract_answer(query: str, context: str) -> str:
        """
        Fast extraction for SMALL path: find the sentence in context that best
        overlaps with the query keywords (no LLM required).
        """
        stopwords = {
            "de", "la", "el", "en", "y", "a", "los", "las", "del", "que",
            "se", "por", "con", "es", "un", "una", "para", "al", "lo",
            "the", "is", "are", "of", "and", "or", "in", "to", "a", "an",
            "quién", "quien", "qué", "que", "cuál", "cual", "cuándo",
            "cuando", "dónde", "donde",
        }
        query_words = {
            w for w in re.findall(r"\b\w{3,}\b", query.lower())
            if w not in stopwords
        }

        sentences = re.split(r"[.!\n]+", context)
        best_sentence = ""
        best_score = -1

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue
            sentence_words = set(re.findall(r"\b\w{3,}\b", sentence.lower()))
            overlap = len(query_words & sentence_words) / max(len(query_words), 1)
            if overlap > best_score:
                best_score = overlap
                best_sentence = sentence

        return best_sentence or context[:300]


_router = InferenceRouter()


def get_inference_router() -> InferenceRouter:
    return _router

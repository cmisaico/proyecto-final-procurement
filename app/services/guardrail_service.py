import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.services.context_handler import ContextResult

logger = get_logger(__name__)

# Patrones para detectar prompt injection y jailbreak en el input del usuario.
# Solo se aplican en validate_input() — no en la validación de salida del LLM.
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above|prior)\s+instructions",
    r"forget\s+(everything|all|your|previous)",
    r"disregard\s+(all|previous|prior|above)",
    r"\bsystem\s*prompt\b",
    r"\byou\s+are\s+now\b",
    r"\bact\s+as\s+(a|an|if)\b",
    r"\bjailbreak\b",
    r"\bDAN\s+mode\b",
    r"do\s+anything\s+now",
    r"pretend\s+(you\s+are|to\s+be)",
    r"bypass\s+(your|all|the)\s+(restrictions|rules|filters|guidelines)",
    r"ignora\s+(las|todas\s+las|tus)\s+(instrucciones|restricciones|reglas)",
    r"olvida\s+(todo|las\s+instrucciones\s+anteriores)",
    r"ahora\s+eres\b",
    r"actúa\s+como\s+(si|un|una)\b",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


class GuardrailResult:
    def __init__(
        self,
        passed: bool,
        score: float,
        flagged_claims: List[str],
        message: str,
    ):
        self.passed = passed
        self.score = score
        self.flagged_claims = flagged_claims
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "flagged_claims": self.flagged_claims,
            "message": self.message,
        }


class GuardrailService:
    """
    Guardrail Pattern:
    - Validates LLM responses against retrieved context
    - Detects potential hallucinations
    - Rejects responses below consistency threshold
    """

    def __init__(self, threshold: float = None):
        self._threshold = threshold or settings.GUARDRAIL_THRESHOLD

    def validate_input(self, text: str) -> GuardrailResult:
        """Pre-LLM check: detect prompt injection and jailbreak attempts."""
        for pattern in _COMPILED_PATTERNS:
            match = pattern.search(text)
            if match:
                logger.warning(
                    "Guardrail: prompt injection detected",
                    extra={"pattern": pattern.pattern, "snippet": text[:120]},
                )
                return GuardrailResult(
                    passed=False,
                    score=0.0,
                    flagged_claims=[match.group(0)],
                    message=f"Prompt injection detected: '{match.group(0)}'",
                )
        return GuardrailResult(passed=True, score=1.0, flagged_claims=[], message="OK")

    def validate(
        self,
        response_text: str,
        context_results: List[ContextResult],
        agent_name: str = "unknown",
    ) -> GuardrailResult:
        if not context_results:
            logger.warning("Guardrail: no context to validate against", extra={"agent": agent_name})
            return GuardrailResult(
                passed=True,
                score=0.5,
                flagged_claims=[],
                message="No context available for validation",
            )

        context_corpus = " ".join(r.content.lower() for r in context_results)
        claims = self._extract_claims(response_text)

        flagged: List[str] = []
        supported = 0

        for claim in claims:
            if self._is_supported(claim, context_corpus):
                supported += 1
            else:
                flagged.append(claim)

        total = len(claims) if claims else 1
        score = supported / total

        # Weight by average context score
        avg_ctx_score = sum(r.score for r in context_results) / len(context_results)
        adjusted_score = (score * 0.7) + (avg_ctx_score * 0.3)

        passed = adjusted_score >= self._threshold

        logger.info(
            "Guardrail check",
            extra={
                "agent": agent_name,
                "claims": total,
                "supported": supported,
                "score": round(adjusted_score, 3),
                "passed": passed,
            },
        )

        return GuardrailResult(
            passed=passed,
            score=round(adjusted_score, 3),
            flagged_claims=flagged[:5],  # max 5 flags
            message="OK" if passed else f"Low consistency ({adjusted_score:.2f} < {self._threshold})",
        )

    def _extract_claims(self, text: str) -> List[str]:
        """Extract factual phrases (sentences + key noun phrases) from LLM output."""
        # Split by sentence
        sentences = re.split(r"[.!?\n]+", text)
        claims = []
        for s in sentences:
            s = s.strip().lower()
            if len(s) > 20:  # ignore very short fragments
                claims.append(s)
        return claims[:20]  # cap at 20 claims

    def _is_supported(self, claim: str, corpus: str) -> bool:
        """Check if key terms of the claim appear in the context corpus."""
        # Extract meaningful words (skip stopwords)
        stopwords = {
            "de", "la", "el", "en", "y", "a", "los", "las", "del", "que",
            "se", "por", "con", "es", "un", "una", "para", "al", "lo",
            "the", "is", "are", "of", "and", "or", "in", "to", "a", "an",
        }
        words = [w for w in re.findall(r"\b\w{4,}\b", claim) if w not in stopwords]

        if not words:
            return True  # nothing to check

        # A claim is "supported" if at least 40% of its key words appear in context
        matches = sum(1 for w in words if w in corpus)
        ratio = matches / len(words)
        return ratio >= 0.4

import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm_factory import get_llm
from app.core.logging import get_logger
from app.domain.entities.workflow import RiskLevel
from app.services.context_handler import EfficientContextHandler
from app.services.guardrail_service import GuardrailService

logger = get_logger(__name__)

AUDIT_SYSTEM_PROMPT = """Eres un auditor experto en cumplimiento normativo de licitaciones públicas.
Analiza la propuesta generada frente a los requisitos legales identificados y el contexto original.

Responde con un objeto JSON válido exactamente con esta estructura:
{
  "compliance_score": 0.0,
  "risk_level": "low|medium|high|critical",
  "issues": [
    {
      "type": "missing_requirement|inconsistency|risk|contradiction",
      "severity": "low|medium|high|critical",
      "description": "descripción del problema",
      "recommendation": "cómo resolverlo"
    }
  ],
  "recommendations": ["recomendación 1", "recomendación 2"],
  "strengths": ["fortaleza 1", "fortaleza 2"],
  "missing_requirements": ["requisito faltante 1"],
  "risks": [
    {"description": "riesgo", "probability": "alta|media|baja", "impact": "alto|medio|bajo"}
  ]
}

compliance_score debe ser un número entre 0.0 y 1.0 que refleje el nivel de cumplimiento."""

AUDIT_QUERIES = [
    "requisitos obligatorios incumplidos o faltantes",
    "riesgos y penalidades por incumplimiento",
    "contradicciones en los documentos de licitación",
]


class ComplianceAuditAgent:
    NAME = "compliance_audit"

    def __init__(self):
        self._llm = get_llm(temperature=0.0)
        self._ctx_handler = EfficientContextHandler()
        self._guardrail = GuardrailService()

    async def run(
        self,
        tender_id: str,
        legal_output: Dict[str, Any],
        proposal_output: Dict[str, Any],
        correlation_id: str,
    ) -> Dict[str, Any]:
        logger.info("AuditAgent started", extra={"tender_id": tender_id, "correlation": correlation_id})

        ctx_results = await self._ctx_handler.retrieve_multi(
            queries=AUDIT_QUERIES,
            tender_id=tender_id,
            top_k_per_query=3,
        )
        context = self._ctx_handler.format_context(ctx_results)

        legal_summary   = json.dumps(legal_output, ensure_ascii=False, indent=2)
        proposal_summary = json.dumps(proposal_output, ensure_ascii=False, indent=2)

        messages = [
            SystemMessage(content=AUDIT_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"REQUISITOS LEGALES IDENTIFICADOS:\n{legal_summary}\n\n"
                f"PROPUESTA GENERADA:\n{proposal_summary}\n\n"
                f"CONTEXTO ORIGINAL:\n{context}\n\n"
                "Realiza la auditoría de cumplimiento."
            )),
        ]

        response = await self._llm.ainvoke(messages)
        raw_output = response.content

        try:
            output = json.loads(raw_output)
        except json.JSONDecodeError:
            output = self._fallback_output()

        # Normalize score
        score = float(output.get("compliance_score", 0.0))
        output["compliance_score"] = max(0.0, min(1.0, score))

        # Normalize risk level
        risk_raw = output.get("risk_level", "medium").lower()
        try:
            RiskLevel(risk_raw)
        except ValueError:
            output["risk_level"] = "medium"

        guardrail_result = self._guardrail.validate(
            response_text=raw_output,
            context_results=ctx_results,
            agent_name=self.NAME,
        )

        if not guardrail_result.passed:
            logger.warning(
                "AuditAgent guardrail FAILED — output discarded, using fallback",
                extra={
                    "tender_id": tender_id,
                    "score": guardrail_result.score,
                    "flagged": guardrail_result.flagged_claims,
                },
            )
            output = self._fallback_output()

        logger.info(
            "AuditAgent completed",
            extra={
                "tender_id": tender_id,
                "compliance_score": output["compliance_score"],
                "risk_level": output.get("risk_level"),
                "issues": len(output.get("issues", [])),
                "guardrail_score": guardrail_result.score,
                "guardrail_passed": guardrail_result.passed,
            },
        )

        return {
            "output": output,
            "guardrail": guardrail_result.to_dict(),
            "context_chunks": len(ctx_results),
        }

    def _fallback_output(self) -> Dict[str, Any]:
        return {
            "compliance_score": 0.5,
            "risk_level": "medium",
            "issues": [],
            "recommendations": ["Revisión manual recomendada"],
            "strengths": [],
            "missing_requirements": [],
            "risks": [],
        }

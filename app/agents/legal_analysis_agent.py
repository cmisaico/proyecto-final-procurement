import json
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm_factory import get_llm
from app.core.logging import get_logger
from app.services.context_handler import EfficientContextHandler
from app.services.guardrail_service import GuardrailService

logger = get_logger(__name__)

LEGAL_SYSTEM_PROMPT = """Eres un abogado experto en contratación pública y licitaciones.
Analiza el contexto proporcionado y extrae ÚNICAMENTE información presente en el texto.

Responde con un objeto JSON válido exactamente con esta estructura:
{
  "requirements": [
    {"type": "technical|legal|financial|administrative", "description": "...", "mandatory": true|false}
  ],
  "required_documents": ["documento 1", "documento 2"],
  "restrictions": ["restricción 1", "restricción 2"],
  "deadlines": [
    {"event": "descripción del hito", "date": "fecha o plazo"}
  ],
  "penalties": ["penalidad 1", "penalidad 2"],
  "budget": "monto o rango presupuestario si aparece"
}

Solo incluye información que esté explícita en el contexto. No inventes datos."""

LEGAL_QUERIES = [
    "requisitos técnicos y legales obligatorios",
    "documentos obligatorios para presentar",
    "restricciones y condiciones de participación",
    "fechas límite y plazos importantes",
    "penalidades multas y sanciones",
    "presupuesto monto disponible",
]


class LegalAnalysisAgent:
    NAME = "legal_analysis"

    def __init__(self):
        self._llm = get_llm(temperature=0.0)
        self._ctx_handler = EfficientContextHandler()
        self._guardrail = GuardrailService()

    async def run(self, tender_id: str, correlation_id: str) -> Dict[str, Any]:
        logger.info("LegalAgent started", extra={"tender_id": tender_id, "correlation": correlation_id})

        ctx_results = await self._ctx_handler.retrieve_multi(
            queries=LEGAL_QUERIES,
            tender_id=tender_id,
            top_k_per_query=3,
        )
        context = self._ctx_handler.format_context(ctx_results)

        messages = [
            SystemMessage(content=LEGAL_SYSTEM_PROMPT),
            HumanMessage(content=f"Analiza el siguiente contexto de licitación:\n\n{context}"),
        ]

        response = await self._llm.ainvoke(messages)
        raw_output = response.content

        try:
            output = json.loads(raw_output)
        except json.JSONDecodeError:
            output = self._fallback_output()

        guardrail_result = self._guardrail.validate(
            response_text=raw_output,
            context_results=ctx_results,
            agent_name=self.NAME,
        )

        if not guardrail_result.passed:
            logger.warning(
                "LegalAgent guardrail FAILED — output discarded, using fallback",
                extra={
                    "tender_id": tender_id,
                    "score": guardrail_result.score,
                    "flagged": guardrail_result.flagged_claims,
                },
            )
            output = self._fallback_output()

        logger.info(
            "LegalAgent completed",
            extra={
                "tender_id": tender_id,
                "requirements": len(output.get("requirements", [])),
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
            "requirements": [],
            "required_documents": [],
            "restrictions": [],
            "deadlines": [],
            "penalties": [],
            "budget": "No determinado",
        }

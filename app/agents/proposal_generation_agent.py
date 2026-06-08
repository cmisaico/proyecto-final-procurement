import json
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm_factory import get_llm
from app.core.logging import get_logger
from app.services.context_handler import EfficientContextHandler
from app.services.guardrail_service import GuardrailService

logger = get_logger(__name__)

PROPOSAL_SYSTEM_PROMPT = """Eres un experto en elaboración de propuestas para licitaciones públicas.
Basándote en el análisis legal y el contexto de la licitación, genera una propuesta preliminar estructurada.

Responde con un objeto JSON válido exactamente con esta estructura:
{
  "executive_summary": "resumen ejecutivo de 2-3 párrafos",
  "proposal": "descripción general de la propuesta técnica",
  "compliance_matrix": [
    {
      "requirement": "requisito de la licitación",
      "compliance_status": "cumple|no_cumple|parcial",
      "evidence": "cómo se cumple o por qué no",
      "documents_needed": ["documento 1"]
    }
  ],
  "checklist": [
    {
      "item": "tarea o documento",
      "category": "documento|técnico|legal|financiero",
      "priority": "alta|media|baja",
      "status": "pendiente"
    }
  ],
  "estimated_effort": "estimación de esfuerzo para preparar la propuesta"
}"""

PROPOSAL_QUERIES = [
    "objeto y alcance de la licitación",
    "especificaciones técnicas requeridas",
    "criterios de evaluación y calificación",
    "formato presentación propuesta técnica",
]


class ProposalGenerationAgent:
    NAME = "proposal_generation"

    def __init__(self):
        self._llm = get_llm(temperature=0.1)
        self._ctx_handler = EfficientContextHandler()
        self._guardrail = GuardrailService()

    async def run(
        self,
        tender_id: str,
        legal_output: Dict[str, Any],
        correlation_id: str,
    ) -> Dict[str, Any]:
        logger.info("ProposalAgent started", extra={"tender_id": tender_id, "correlation": correlation_id})

        ctx_results = await self._ctx_handler.retrieve_multi(
            queries=PROPOSAL_QUERIES,
            tender_id=tender_id,
            top_k_per_query=3,
        )
        context = self._ctx_handler.format_context(ctx_results)

        legal_summary = json.dumps(legal_output, ensure_ascii=False, indent=2)

        messages = [
            SystemMessage(content=PROPOSAL_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"ANÁLISIS LEGAL PREVIO:\n{legal_summary}\n\n"
                f"CONTEXTO DE LA LICITACIÓN:\n{context}\n\n"
                "Genera la propuesta preliminar."
            )),
        ]

        response = await self._llm.ainvoke(messages)
        raw_output = response.content

        try:
            output = json.loads(raw_output)
        except json.JSONDecodeError:
            output = self._fallback_output(legal_output)

        guardrail_result = self._guardrail.validate(
            response_text=raw_output,
            context_results=ctx_results,
            agent_name=self.NAME,
        )

        logger.info(
            "ProposalAgent completed",
            extra={
                "tender_id": tender_id,
                "checklist_items": len(output.get("checklist", [])),
                "compliance_items": len(output.get("compliance_matrix", [])),
                "guardrail_score": guardrail_result.score,
            },
        )

        return {
            "output": output,
            "guardrail": guardrail_result.to_dict(),
            "context_chunks": len(ctx_results),
        }

    def _fallback_output(self, legal_output: Dict[str, Any]) -> Dict[str, Any]:
        reqs = legal_output.get("requirements", [])
        checklist = [
            {"item": r.get("description", ""), "category": r.get("type", "otro"),
             "priority": "alta" if r.get("mandatory") else "media", "status": "pendiente"}
            for r in reqs
        ]
        return {
            "executive_summary": "No se pudo generar resumen ejecutivo.",
            "proposal": "Propuesta pendiente de elaboración.",
            "compliance_matrix": [],
            "checklist": checklist,
            "estimated_effort": "No determinado",
        }

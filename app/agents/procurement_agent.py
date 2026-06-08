import json
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from app.core.llm_factory import get_llm
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.pipeline import RAGPipeline

logger = get_logger(__name__)

SYSTEM_PROMPT = """Eres un experto en análisis de licitaciones públicas.
Analiza el texto de la licitación y extrae la siguiente información en formato JSON estricto.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura:
{
  "requirements": [
    {
      "type": "document|technical|financial|legal|deadline|restriction|other",
      "priority": "mandatory|optional",
      "description": "descripción clara del requisito",
      "raw_text": "texto original del documento"
    }
  ],
  "mandatory_documents": ["lista de documentos requeridos"],
  "key_dates": [
    {"description": "descripción del hito", "date": "fecha en formato ISO o texto"}
  ],
  "restrictions": ["lista de restricciones identificadas"],
  "summary": "resumen ejecutivo de la licitación en 2-3 oraciones"
}"""


class AgentState(TypedDict):
    tender_id: str
    document_id: str
    context: str
    messages: Annotated[list, add_messages]
    analysis: Optional[Dict[str, Any]]
    error: Optional[str]


class ProcurementAnalysisAgent:
    def __init__(self):
        self._llm = get_llm(temperature=0.0)
        self._rag = RAGPipeline()
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        workflow = StateGraph(AgentState)

        workflow.add_node("retrieve_context", self._retrieve_context)
        workflow.add_node("analyze", self._analyze)
        workflow.add_node("validate", self._validate)

        workflow.set_entry_point("retrieve_context")
        workflow.add_edge("retrieve_context", "analyze")
        workflow.add_edge("analyze", "validate")
        workflow.add_edge("validate", END)

        return workflow.compile()

    async def _retrieve_context(self, state: AgentState) -> AgentState:
        queries = [
            "requisitos obligatorios documentos",
            "fechas límite plazo presentación",
            "restricciones condiciones participación",
            "requisitos técnicos financieros",
        ]
        context_parts = []
        for q in queries:
            result = await self._rag.query(
                question=q,
                tender_id=state["tender_id"],
                top_k=3,
            )
            context_parts.append(result["answer"])

        state["context"] = "\n\n".join(context_parts)
        return state

    async def _analyze(self, state: AgentState) -> AgentState:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Analiza esta licitación:\n\n{state['context']}"),
        ]
        response = await self._llm.ainvoke(messages)
        try:
            state["analysis"] = json.loads(response.content)
        except json.JSONDecodeError:
            state["error"] = "Failed to parse JSON response from LLM"
            state["analysis"] = {}
        return state

    async def _validate(self, state: AgentState) -> AgentState:
        analysis = state.get("analysis", {})
        if not analysis.get("requirements"):
            analysis["requirements"] = []
        if not analysis.get("mandatory_documents"):
            analysis["mandatory_documents"] = []
        if not analysis.get("key_dates"):
            analysis["key_dates"] = []
        if not analysis.get("restrictions"):
            analysis["restrictions"] = []
        if not analysis.get("summary"):
            analysis["summary"] = "No se pudo generar un resumen."
        state["analysis"] = analysis
        logger.info("Agent analysis complete", extra={"tender_id": state["tender_id"]})
        return state

    async def analyze(self, tender_id: str, document_id: str) -> Dict[str, Any]:
        initial_state = AgentState(
            tender_id=tender_id,
            document_id=document_id,
            context="",
            messages=[],
            analysis=None,
            error=None,
        )
        final_state = await self._graph.ainvoke(initial_state)
        return {
            "tender_id": tender_id,
            "document_id": document_id,
            "analysis": final_state["analysis"],
            "error": final_state.get("error"),
        }

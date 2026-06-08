"""
Supervisor Agent — Multi-Agent Orchestrator (LangGraph) — Fase 2+3

Workflow:
  START → legal_node → proposal_node → audit_node → report_node → END

Fase 3: each node records Prometheus metrics and OTel spans.
"""
import time
import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from app.agents.compliance_audit_agent import ComplianceAuditAgent
from app.agents.legal_analysis_agent import LegalAnalysisAgent
from app.agents.proposal_generation_agent import ProposalGenerationAgent
from app.core.agent_metrics import record_agent_run, record_workflow
from app.core.logging import get_logger
from app.core.tracing import get_tracer, span

logger = get_logger(__name__)


class WorkflowState(TypedDict):
    workflow_id: str
    tender_id: str
    correlation_id: str
    legal_result: Optional[Dict[str, Any]]
    proposal_result: Optional[Dict[str, Any]]
    audit_result: Optional[Dict[str, Any]]
    guardrail_scores: Dict[str, float]
    final_report: Optional[Dict[str, Any]]
    messages: Annotated[list, add_messages]
    steps_completed: List[str]
    errors: List[str]
    started_at: str


class SupervisorAgent:
    def __init__(self):
        self._legal_agent    = LegalAnalysisAgent()
        self._proposal_agent = ProposalGenerationAgent()
        self._audit_agent    = ComplianceAuditAgent()
        self._graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(WorkflowState)
        workflow.add_node("legal_node",    self._legal_node)
        workflow.add_node("proposal_node", self._proposal_node)
        workflow.add_node("audit_node",    self._audit_node)
        workflow.add_node("report_node",   self._report_node)
        workflow.set_entry_point("legal_node")
        workflow.add_edge("legal_node",    "proposal_node")
        workflow.add_edge("proposal_node", "audit_node")
        workflow.add_edge("audit_node",    "report_node")
        workflow.add_edge("report_node",   END)
        return workflow.compile()

    async def _legal_node(self, state: WorkflowState) -> WorkflowState:
        logger.info("Supervisor: legal_node", extra={
            "workflow_id": state["workflow_id"], "correlation_id": state["correlation_id"]
        })
        t0 = time.perf_counter()
        success = True
        with span("legal_analysis", {"tender_id": state["tender_id"], "workflow_id": state["workflow_id"]}):
            try:
                result = await self._legal_agent.run(
                    tender_id=state["tender_id"],
                    correlation_id=state["correlation_id"],
                )
                state["legal_result"] = result["output"]
                state["guardrail_scores"]["legal"] = result["guardrail"]["score"]
                state["steps_completed"].append("legal")
            except Exception as e:
                state["errors"].append(f"legal_node: {e}")
                state["legal_result"] = {}
                success = False
                logger.error("legal_node failed", extra={"error": str(e)})

        duration = time.perf_counter() - t0
        req_count = len((state.get("legal_result") or {}).get("requirements", []))
        record_agent_run(
            agent_name="legal_analysis",
            duration_seconds=duration,
            success=success,
            guardrail_score=state["guardrail_scores"].get("legal"),
            extra={"requirements_count": req_count},
        )
        return state

    async def _proposal_node(self, state: WorkflowState) -> WorkflowState:
        logger.info("Supervisor: proposal_node", extra={"workflow_id": state["workflow_id"]})
        t0 = time.perf_counter()
        success = True
        with span("proposal_generation", {"tender_id": state["tender_id"]}):
            try:
                result = await self._proposal_agent.run(
                    tender_id=state["tender_id"],
                    legal_output=state.get("legal_result") or {},
                    correlation_id=state["correlation_id"],
                )
                state["proposal_result"] = result["output"]
                state["guardrail_scores"]["proposal"] = result["guardrail"]["score"]
                state["steps_completed"].append("proposal")
            except Exception as e:
                state["errors"].append(f"proposal_node: {e}")
                state["proposal_result"] = {}
                success = False
                logger.error("proposal_node failed", extra={"error": str(e)})

        duration = time.perf_counter() - t0
        summary = (state.get("proposal_result") or {}).get("executive_summary", "")
        record_agent_run(
            agent_name="proposal_generation",
            duration_seconds=duration,
            success=success,
            guardrail_score=state["guardrail_scores"].get("proposal"),
            extra={"proposal_length": len(summary)},
        )
        return state

    async def _audit_node(self, state: WorkflowState) -> WorkflowState:
        logger.info("Supervisor: audit_node", extra={"workflow_id": state["workflow_id"]})
        t0 = time.perf_counter()
        success = True
        with span("compliance_audit", {"tender_id": state["tender_id"]}):
            try:
                result = await self._audit_agent.run(
                    tender_id=state["tender_id"],
                    legal_output=state.get("legal_result") or {},
                    proposal_output=state.get("proposal_result") or {},
                    correlation_id=state["correlation_id"],
                )
                state["audit_result"] = result["output"]
                state["guardrail_scores"]["audit"] = result["guardrail"]["score"]
                state["steps_completed"].append("audit")
            except Exception as e:
                state["errors"].append(f"audit_node: {e}")
                state["audit_result"] = {}
                success = False
                logger.error("audit_node failed", extra={"error": str(e)})

        duration = time.perf_counter() - t0
        audit_out = state.get("audit_result") or {}
        record_agent_run(
            agent_name="compliance_audit",
            duration_seconds=duration,
            success=success,
            guardrail_score=state["guardrail_scores"].get("audit"),
            extra={
                "compliance_score": audit_out.get("compliance_score", 0.0),
                "risk_level": audit_out.get("risk_level", "medium"),
            },
        )
        return state

    async def _report_node(self, state: WorkflowState) -> WorkflowState:
        audit    = state.get("audit_result") or {}
        legal    = state.get("legal_result") or {}
        proposal = state.get("proposal_result") or {}
        avg_guardrail = (
            sum(state["guardrail_scores"].values()) / len(state["guardrail_scores"])
            if state["guardrail_scores"] else 0.5
        )
        state["final_report"] = {
            "workflow_id": state["workflow_id"],
            "tender_id": state["tender_id"],
            "correlation_id": state["correlation_id"],
            "compliance_score": audit.get("compliance_score", 0.0),
            "risk_level": audit.get("risk_level", "medium"),
            "executive_summary": proposal.get("executive_summary", ""),
            "requirements_count": len(legal.get("requirements", [])),
            "required_documents": legal.get("required_documents", []),
            "deadlines": legal.get("deadlines", []),
            "penalties": legal.get("penalties", []),
            "checklist": proposal.get("checklist", []),
            "compliance_matrix": proposal.get("compliance_matrix", []),
            "issues": audit.get("issues", []),
            "recommendations": audit.get("recommendations", []),
            "risks": audit.get("risks", []),
            "guardrail_scores": state["guardrail_scores"],
            "avg_guardrail_score": round(avg_guardrail, 3),
            "steps_completed": state["steps_completed"],
            "errors": state["errors"],
            "completed_at": datetime.utcnow().isoformat(),
        }
        state["steps_completed"].append("report")
        return state

    async def execute(self, tender_id: str, workflow_id: Optional[str] = None) -> Dict[str, Any]:
        wf_id = workflow_id or str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        t0 = time.perf_counter()

        initial_state = WorkflowState(
            workflow_id=wf_id,
            tender_id=tender_id,
            correlation_id=correlation_id,
            legal_result=None,
            proposal_result=None,
            audit_result=None,
            guardrail_scores={},
            final_report=None,
            messages=[],
            steps_completed=[],
            errors=[],
            started_at=datetime.utcnow().isoformat(),
        )

        logger.info("Supervisor workflow started", extra={
            "workflow_id": wf_id, "tender_id": tender_id, "correlation_id": correlation_id
        })

        success = True
        with span("supervisor_workflow", {"workflow_id": wf_id, "tender_id": tender_id}):
            try:
                final_state = await self._graph.ainvoke(initial_state)
            except Exception as e:
                success = False
                logger.error("Supervisor workflow failed", extra={"error": str(e)})
                raise

        duration = time.perf_counter() - t0
        record_workflow(duration_seconds=duration, success=success)
        logger.info("Supervisor workflow completed", extra={
            "workflow_id": wf_id,
            "duration_seconds": round(duration, 2),
            "steps": final_state.get("steps_completed", []),
        })

        return {
            "workflow_id": wf_id,
            "tender_id": tender_id,
            "correlation_id": correlation_id,
            "legal": final_state.get("legal_result"),
            "proposal": final_state.get("proposal_result"),
            "audit": final_state.get("audit_result"),
            "final_report": final_state.get("final_report"),
            "steps_completed": final_state.get("steps_completed", []),
            "errors": final_state.get("errors", []),
        }

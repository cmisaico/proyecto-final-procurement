"""
LangGraph Worker — procesa workflows pendientes de la DB.
Se ejecuta como servicio independiente en Docker Compose.
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, "/app")

from app.core.logging import setup_logging, get_logger
from app.infrastructure.database.connection import AsyncSessionLocal
from app.application.use_cases.run_full_analysis import RunFullAnalysisUseCase, FullAnalysisInput
from app.domain.entities.workflow import WorkflowStatus
from app.infrastructure.repositories.pg_workflow_repository import PgWorkflowRepository

setup_logging()
logger = get_logger("langgraph-worker")

POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "10"))


async def process_pending_workflows():
    """Pick up pending workflows and execute them."""
    async with AsyncSessionLocal() as session:
        repo = PgWorkflowRepository(session)

        from sqlalchemy import select
        from app.infrastructure.database.models_fase02 import WorkflowExecutionModel

        result = await session.execute(
            select(WorkflowExecutionModel)
            .where(WorkflowExecutionModel.status == WorkflowStatus.PENDING.value)
            .limit(5)
        )
        pending = result.scalars().all()

        for wf_model in pending:
            logger.info("Worker picking up workflow", extra={"workflow_id": wf_model.id})
            try:
                use_case = RunFullAnalysisUseCase(session)
                await use_case.execute(FullAnalysisInput(tender_id=wf_model.tender_id))
                await session.commit()
            except Exception as e:
                logger.error("Worker failed processing workflow",
                             extra={"workflow_id": wf_model.id, "error": str(e)})
                await session.rollback()


async def main():
    logger.info("LangGraph Worker started", extra={"poll_interval": POLL_INTERVAL})
    while True:
        try:
            await process_pending_workflows()
        except Exception as e:
            logger.error("Worker poll error", extra={"error": str(e)})
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())

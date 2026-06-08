from fastapi import APIRouter

from app.api.v1.endpoints import agents, cost_analysis, documents, health, rag, reports, workflow

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(rag.router)
api_router.include_router(agents.router)
api_router.include_router(workflow.router)
api_router.include_router(reports.router)
api_router.include_router(cost_analysis.router)

import time
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(tags=["observability"])


class HealthResponse(BaseModel):
    status: str
    version: str
    app: str


class ReadinessResponse(BaseModel):
    status: str
    checks: Dict[str, str]


class StatusResponse(BaseModel):
    status: str
    version: str
    services: Dict[str, Any]
    llm_model: str
    embed_model: str
    context_top_k: int
    max_context_tokens: int
    guardrail_threshold: float


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        app=settings.APP_NAME,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness():
    checks: Dict[str, str] = {}

    try:
        from app.infrastructure.database.connection import engine
        import sqlalchemy
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {str(e)[:80]}"

    try:
        from app.infrastructure.vector_store.qdrant_client import qdrant_store
        qdrant_store._client.get_collections()
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = f"error: {str(e)[:80]}"

    try:
        from app.infrastructure.storage.factory import storage_client
        storage_client.ensure_bucket()
        checks["storage"] = "ok"
    except Exception as e:
        checks["storage"] = f"error: {str(e)[:80]}"

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            checks["ollama"] = "ok" if r.status_code == 200 else f"http_{r.status_code}"
    except Exception as e:
        checks["ollama"] = f"error: {str(e)[:80]}"

    all_ok = all(v == "ok" for v in checks.values())
    return ReadinessResponse(
        status="ready" if all_ok else "degraded",
        checks=checks,
    )


@router.get("/status", response_model=StatusResponse)
async def status():
    """Extended status with configuration and service details."""
    checks: Dict[str, Any] = {}

    for svc, checker in [
        ("postgres", _check_postgres),
        ("qdrant",   _check_qdrant),
        ("storage",  _check_storage),
        ("ollama",   _check_ollama),
    ]:
        t0 = time.perf_counter()
        try:
            ok = await checker()
            checks[svc] = {"status": "ok" if ok else "error", "latency_ms": round((time.perf_counter()-t0)*1000, 1)}
        except Exception as e:
            checks[svc] = {"status": "error", "detail": str(e)[:80], "latency_ms": round((time.perf_counter()-t0)*1000, 1)}

    all_ok = all(v.get("status") == "ok" for v in checks.values())
    return StatusResponse(
        status="healthy" if all_ok else "degraded",
        version=settings.APP_VERSION,
        services=checks,
        llm_model=settings.OLLAMA_LLM_MODEL,
        embed_model=settings.OLLAMA_EMBED_MODEL,
        context_top_k=settings.CONTEXT_TOP_K,
        max_context_tokens=settings.MAX_CONTEXT_TOKENS,
        guardrail_threshold=settings.GUARDRAIL_THRESHOLD,
    )


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus metrics endpoint."""
    data = generate_latest()
    return PlainTextResponse(content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _check_postgres() -> bool:
    from app.infrastructure.database.connection import engine
    import sqlalchemy
    async with engine.connect() as conn:
        await conn.execute(sqlalchemy.text("SELECT 1"))
    return True


async def _check_qdrant() -> bool:
    from app.infrastructure.vector_store.qdrant_client import qdrant_store
    qdrant_store._client.get_collections()
    return True


async def _check_storage() -> bool:
    from app.infrastructure.storage.factory import storage_client
    storage_client.ensure_bucket()
    return True


async def _check_ollama() -> bool:
    import httpx
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
        return r.status_code == 200

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import setup_logging
from app.core.tracing import setup_tracing, instrument_fastapi
from app.middleware.metrics_middleware import MetricsMiddleware

setup_logging()
setup_tracing(service_name="procurement-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    _log = logging.getLogger(__name__)

    from app.infrastructure.storage.factory import storage_client
    from app.infrastructure.vector_store.qdrant_client import qdrant_store
    import app.infrastructure.database.models          # noqa: F401
    import app.infrastructure.database.models_fase02   # noqa: F401

    # Dependency initialization: errors are logged as warnings so that the app
    # starts and /health always returns 200. Connections are retried lazily on
    # first use. This allows the Rollout readiness probe to pass while
    # infrastructure (Qdrant, Azure Blob) comes up asynchronously.
    try:
        storage_client.ensure_bucket()
    except Exception as exc:
        _log.warning("Storage init failed at startup — will retry on first use: %s", exc)

    try:
        qdrant_store.ensure_collection()
    except Exception as exc:
        _log.warning("Qdrant init failed at startup — will retry on first use: %s", exc)

    yield

    from app.infrastructure.database.connection import engine
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Autonomous Procurement Intelligence Platform — Fase 3: LLMOps & Observability",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

instrument_fastapi(app)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


app.include_router(api_router)


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

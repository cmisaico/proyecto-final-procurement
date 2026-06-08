import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import (
    HTTP_ERRORS_TOTAL,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_ACTIVE,
    HTTP_REQUESTS_TOTAL,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records Prometheus HTTP metrics for every request."""

    SKIP_PATHS = {"/metrics", "/health", "/ready", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        # Normalize dynamic path params for better cardinality
        endpoint = self._normalize_path(path)

        if path in self.SKIP_PATHS:
            return await call_next(request)

        HTTP_REQUESTS_ACTIVE.inc()
        start = time.perf_counter()

        try:
            response = await call_next(request)
            status = str(response.status_code)
            HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code=status).inc()
            if response.status_code >= 400:
                HTTP_ERRORS_TOTAL.labels(method=method, endpoint=endpoint, status_code=status).inc()
            return response
        except Exception as exc:
            HTTP_ERRORS_TOTAL.labels(method=method, endpoint=endpoint, status_code="500").inc()
            HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code="500").inc()
            raise
        finally:
            duration = time.perf_counter() - start
            HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
            HTTP_REQUESTS_ACTIVE.dec()

    def _normalize_path(self, path: str) -> str:
        import re
        # Replace UUIDs with {id}
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{id}",
            path,
        )
        return path

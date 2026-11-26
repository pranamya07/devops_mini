"""Prometheus metrics and request logging for every HTTP request.

Metrics exposed on /metrics (scraped by Prometheus, graphed in Grafana):
    http_requests_total            requests by method, route and status code
    http_request_duration_seconds  latency histogram (for p50/p95/p99)
    http_requests_in_progress      requests being handled right now
    http_exceptions_total          unhandled errors by exception type
    task_operations_total          tasks created, replaced, updated, deleted
    app_info                       running version and environment
    process_*                      CPU time and memory of the API process
"""

import logging
import re
import time
import uuid

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.requests")

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests handled, by method, route and status code.",
    ["method", "path", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Time spent handling HTTP requests.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
IN_PROGRESS = Gauge("http_requests_in_progress", "HTTP requests currently being handled.")
EXCEPTIONS = Counter(
    "http_exceptions_total",
    "Unhandled exceptions raised while handling requests.",
    ["path", "exception"],
)
TASK_OPERATIONS = Counter(
    "task_operations_total",
    "Task changes made through the API.",
    ["operation"],
)
APP_INFO = Gauge(
    "app_info",
    "Running app version and environment (value is always 1).",
    ["app_name", "version", "environment"],
)

# Prometheus scrapes /metrics every few seconds; counting it would drown real traffic.
EXCLUDED_PATHS = {"/metrics"}

# Accept a caller's X-Request-ID only if it is short and safe to write to logs.
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def record_app_info(app_name: str, version: str, environment: str) -> None:
    APP_INFO.clear()
    APP_INFO.labels(app_name, version, environment).set(1)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def route_template(request: Request) -> str:
    """The route pattern, e.g. /api/v1/tasks/{task_id}, not /api/v1/tasks/42.

    FastAPI stores the matched route on the request once routing has run.
    Using the pattern keeps one metric series per route instead of one per ID.
    """
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


def request_id_for(request: Request) -> str:
    incoming = request.headers.get("x-request-id", "")
    return incoming if SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        request_id = request_id_for(request)
        method = request.method
        status = 500
        start = time.perf_counter()
        IN_PROGRESS.inc()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            EXCEPTIONS.labels(route_template(request), type(exc).__name__).inc()
            logger.exception(
                "Unhandled error on %s %s request_id=%s", method, request.url.path, request_id
            )
            raise
        finally:
            duration = time.perf_counter() - start
            path = route_template(request)
            IN_PROGRESS.dec()
            REQUESTS.labels(method, path, str(status)).inc()
            LATENCY.labels(method, path).observe(duration)
            level = (
                logging.ERROR
                if status >= 500
                else logging.WARNING
                if status >= 400
                else logging.INFO
            )
            logger.log(
                level,
                "%s %s %s %.1fms request_id=%s",
                method,
                request.url.path,
                status,
                duration * 1000,
                request_id,
            )

        response.headers["X-Request-ID"] = request_id
        return response

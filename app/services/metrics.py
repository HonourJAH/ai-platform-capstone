import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "inference_requests_total",
    "Total requests to the inference endpoint",
    ["task_type", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "inference_request_latency_seconds",
    "Latency of inference requests",
    ["task_type"],
)

RATE_LIMIT_REJECTIONS = Counter(
    "rate_limit_rejections_total",
    "Total requests rejected by the rate limiter",
    ["tier"],
)

HTTP_REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["path", "status_code"],
)

HTTP_REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "Latency of HTTP requests",
    ["path"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start

        path = request.url.path
        HTTP_REQUEST_COUNT.labels(path=path, status_code=response.status_code).inc()
        HTTP_REQUEST_LATENCY.labels(path=path).observe(duration)

        return response

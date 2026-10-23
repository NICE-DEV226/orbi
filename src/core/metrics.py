"""
Orbi — Métriques Prometheus (requêtes HTTP).
Les labels utilisent le gabarit de route (jamais l'URL brute) pour borner la cardinalité.
"""

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request

HTTP_REQUESTS = Counter("orbi_http_requests_total", "Requêtes HTTP traitées", ["method", "route", "status"])
HTTP_LATENCY = Histogram("orbi_http_request_duration_seconds", "Durée des requêtes HTTP", ["method", "route"])

_UNMATCHED = "unmatched"
_SKIPPED_ROUTES = {"/metrics", "/livez"}


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", _UNMATCHED)


async def metrics_middleware(request: Request, call_next):
    """Mesure chaque requête (compteur + histogramme de latence)."""
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = _route_label(request)
        if route not in _SKIPPED_ROUTES:
            HTTP_REQUESTS.labels(request.method, route, str(status)).inc()
            HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - start)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST

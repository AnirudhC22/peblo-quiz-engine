"""
Middleware
- RequestLoggingMiddleware: logs method, path, status, duration for every request
- RateLimitMiddleware: simple in-memory token bucket per IP address
"""

import logging
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request Logging Middleware
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every request with method, path, status code, and duration.
    Format: POST /api/v1/ingest → 200 in 412ms
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000)

        # Skip noisy health pings
        if request.url.path not in ("/health", "/"):
            logger.info(
                f"{request.method} {request.url.path} → {response.status_code} in {duration_ms}ms"
            )

        return response


# ---------------------------------------------------------------------------
# Rate Limiting Middleware (token bucket per IP)
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory token bucket rate limiter.

    Default: 60 requests per minute per IP.
    LLM-heavy endpoints (/generate-quiz, /quiz/.../hint) share a tighter
    sub-limit of 10 req/min to protect against accidental Gemini quota burn.

    In production, replace with Redis-backed sliding window.
    """

    # { ip: [timestamp, ...] }
    _general: dict = defaultdict(list)
    _llm_heavy: dict = defaultdict(list)

    GENERAL_LIMIT = 60    # requests per minute
    LLM_LIMIT = 10        # requests per minute for LLM endpoints
    WINDOW = 60           # seconds

    LLM_PATHS = {"/api/v1/generate-quiz", "/api/v1/quiz"}

    def _is_llm_path(self, path: str) -> bool:
        if path in self.LLM_PATHS:
            return True
        if "/hint" in path:
            return True
        return False

    def _check_limit(self, store: dict, ip: str, limit: int) -> bool:
        """Returns True if request is allowed, False if rate limited."""
        now = time.time()
        window_start = now - self.WINDOW

        # Prune old timestamps
        store[ip] = [t for t in store[ip] if t > window_start]

        if len(store[ip]) >= limit:
            return False

        store[ip].append(now)
        return True

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks and docs
        if request.url.path in ("/health", "/", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"

        # Check LLM-heavy endpoint limit first
        if self._is_llm_path(request.url.path):
            if not self._check_limit(self._llm_heavy, ip, self.LLM_LIMIT):
                logger.warning(f"LLM rate limit hit for IP {ip} on {request.url.path}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Too many LLM requests. Limit: {self.LLM_LIMIT}/min per IP.",
                        "retry_after": "60 seconds",
                    },
                )

        # General rate limit
        if not self._check_limit(self._general, ip, self.GENERAL_LIMIT):
            logger.warning(f"General rate limit hit for IP {ip}")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Too many requests. Limit: {self.GENERAL_LIMIT}/min per IP.",
                    "retry_after": "60 seconds",
                },
            )

        return await call_next(request)

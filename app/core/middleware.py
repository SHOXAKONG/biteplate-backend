from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = structlog.get_logger()

TerminalCall = Callable[[Request], Awaitable[Response]]


class MiddlewareHandler(ABC):

    name: str = "handler"
    _next: MiddlewareHandler | None = None

    def set_next(self, handler: MiddlewareHandler) -> MiddlewareHandler:
        self._next = handler
        return handler

    async def _continue(self, request: Request, terminal: TerminalCall) -> Response:
        if self._next is not None:
            return await self._next.handle(request, terminal)
        return await terminal(request)

    @abstractmethod
    async def handle(self, request: Request, terminal: TerminalCall) -> Response: ...



class RequestIDHandler(MiddlewareHandler):
    name = "request_id"
    HEADER = "X-Request-ID"

    async def handle(self, request: Request, terminal: TerminalCall) -> Response:
        rid = request.headers.get(self.HEADER) or uuid.uuid4().hex
        request.state.request_id = rid
        structlog.contextvars.bind_contextvars(request_id=rid)
        try:
            response = await self._continue(request, terminal)
            response.headers[self.HEADER] = rid
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id")


class ErrorTranslatingHandler(MiddlewareHandler):
    name = "error_translator"

    async def handle(self, request: Request, terminal: TerminalCall) -> Response:
        try:
            return await self._continue(request, terminal)
        except Exception as exc:
            rid = getattr(request.state, "request_id", None)
            log.exception(
                "unhandled_exception",
                error=str(exc),
                type=exc.__class__.__name__,
                path=request.url.path,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "type": exc.__class__.__name__,
                    "request_id": rid,
                },
            )


class TimingHandler(MiddlewareHandler):
    name = "timing"
    HEADER = "X-Process-Time-Ms"

    async def handle(self, request: Request, terminal: TerminalCall) -> Response:
        start = time.perf_counter()
        response = await self._continue(request, terminal)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers[self.HEADER] = str(elapsed_ms)
        request.state.elapsed_ms = elapsed_ms
        return response


class LoggingHandler(MiddlewareHandler):

    name = "logging"

    async def handle(self, request: Request, terminal: TerminalCall) -> Response:
        response = await self._continue(request, terminal)
        log.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed_ms=getattr(request.state, "elapsed_ms", None),
            client=request.client.host if request.client else None,
        )
        return response


class RateLimitHandler(MiddlewareHandler):

    name = "rate_limit"
    EXEMPT_PATHS = ("/health", "/docs", "/openapi.json", "/redoc")

    def __init__(self, max_per_minute: int = 240):
        super().__init__()
        self._buckets: dict[str, list[float]] = {}
        self._max = max_per_minute
        self._window = 60.0
        self._lock = asyncio.Lock()

    def _exempt(self, path: str) -> bool:
        return any(path == p or path.startswith(p + "/") for p in self.EXEMPT_PATHS)

    async def handle(self, request: Request, terminal: TerminalCall) -> Response:
        if self._exempt(request.url.path):
            return await self._continue(request, terminal)

        ip = request.client.host if request.client else "unknown"
        now = time.time()
        async with self._lock:
            bucket = self._buckets.setdefault(ip, [])
            cutoff = now - self._window
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)
            if len(bucket) >= self._max:
                retry_after = int(self._window - (now - bucket[0]))
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={
                        "detail": f"Rate limit exceeded ({self._max}/min)",
                        "retry_after_seconds": retry_after,
                    },
                )
            bucket.append(now)

        return await self._continue(request, terminal)



def build_chain() -> MiddlewareHandler:
    """
    Order matters. Outer handlers see the request first AND the response last,
    which means their post-processing runs on EVERY response — including the
    one synthesized by ErrorTranslating when an endpoint raises.

        RequestID  →  Timing  →  Logging  →  ErrorTranslating  →  RateLimit  →  endpoint

    - RequestID outermost so every response (success OR translated error)
      gets the X-Request-ID header.
    - Timing next, so X-Process-Time-Ms is added to error responses too.
    - Logging logs every response (FastAPI's own exception handlers run inside
      the endpoint call, so Logging sees the final status).
    - ErrorTranslating catches anything Logging/handlers didn't deal with.
    - RateLimit nearest the endpoint — can short-circuit before any work runs.
    """
    head = RequestIDHandler()
    head.set_next(TimingHandler()) \
        .set_next(LoggingHandler()) \
        .set_next(ErrorTranslatingHandler()) \
        .set_next(RateLimitHandler(max_per_minute=240))
    return head


class ChainMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, chain_head: MiddlewareHandler):
        super().__init__(app)
        self.chain_head = chain_head

    async def dispatch(self, request: Request, call_next: TerminalCall) -> Response:
        return await self.chain_head.handle(request, call_next)


def attach_chain(app: FastAPI) -> None:
    chain = build_chain()
    app.add_middleware(ChainMiddleware, chain_head=chain)

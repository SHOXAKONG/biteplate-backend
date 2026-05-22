"""Unit tests for the Chain of Responsibility middleware."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.responses import JSONResponse, Response

from app.core.middleware import (
    ErrorTranslatingHandler,
    LoggingHandler,
    MiddlewareHandler,
    RateLimitHandler,
    RequestIDHandler,
    TimingHandler,
    build_chain,
)


def make_request(path: str = "/", headers: dict | None = None, client_host: str = "1.2.3.4"):
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        headers=headers or {},
        state=SimpleNamespace(),
        client=SimpleNamespace(host=client_host),
        method="GET",
    )


async def _ok(_request) -> Response:
    return Response(status_code=200, content="ok")


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_chain_links_in_order():
    a = ErrorTranslatingHandler()
    b = RequestIDHandler()
    c = TimingHandler()
    a.set_next(b).set_next(c)
    assert a._next is b
    assert b._next is c
    assert c._next is None


def test_request_id_handler_generates_id_and_sets_header():
    h = RequestIDHandler()
    req = make_request()
    resp = run(h.handle(req, _ok))  # pyright: ignore[reportArgumentType]
    assert resp.headers["X-Request-ID"]
    assert len(resp.headers["X-Request-ID"]) == 32
    assert getattr(req.state, "request_id") == resp.headers["X-Request-ID"]


def test_request_id_handler_reuses_incoming_header():
    h = RequestIDHandler()
    req = make_request(headers={"X-Request-ID": "abc-123"})
    resp = run(h.handle(req, _ok))  # pyright: ignore[reportArgumentType]
    assert resp.headers["X-Request-ID"] == "abc-123"


def test_timing_handler_adds_process_time_header():
    h = TimingHandler()
    req = make_request()

    async def slow(_request):
        await asyncio.sleep(0.01)
        return Response(status_code=200, content="ok")

    resp = run(h.handle(req, slow))  # pyright: ignore[reportArgumentType]
    ms = float(resp.headers["X-Process-Time-Ms"])
    assert ms >= 5  # at least ~10ms minus jitter


def test_rate_limit_short_circuits_after_threshold():
    h = RateLimitHandler(max_per_minute=3)
    req = make_request(client_host="9.9.9.9")
    # First 3 pass through.
    for _ in range(3):
        resp = run(h.handle(req, _ok))  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 200
    # 4th gets blocked.
    resp = run(h.handle(req, _ok))  # pyright: ignore[reportArgumentType]
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_rate_limit_per_ip_isolation():
    h = RateLimitHandler(max_per_minute=2)
    a = make_request(client_host="1.1.1.1")
    b = make_request(client_host="2.2.2.2")
    # IP A exhausts its budget.
    for _ in range(2):
        run(h.handle(a, _ok))  # pyright: ignore[reportArgumentType]
    blocked = run(h.handle(a, _ok))  # pyright: ignore[reportArgumentType]
    assert blocked.status_code == 429
    # IP B is untouched.
    fresh = run(h.handle(b, _ok))  # pyright: ignore[reportArgumentType]
    assert fresh.status_code == 200


def test_rate_limit_exempts_health_path():
    h = RateLimitHandler(max_per_minute=1)
    req = make_request(path="/health")
    # 10 hits to /health all pass even though limit is 1.
    for _ in range(10):
        resp = run(h.handle(req, _ok))  # pyright: ignore[reportArgumentType]
        assert resp.status_code == 200


def test_error_translator_catches_exceptions_below():
    h = ErrorTranslatingHandler()
    req = make_request()

    async def boom(_request):
        raise RuntimeError("kaboom")

    resp = run(h.handle(req, boom))  # pyright: ignore[reportArgumentType]
    assert resp.status_code == 500
    assert isinstance(resp, JSONResponse)


def test_logging_handler_passes_through_response_unchanged():
    h = LoggingHandler()
    req = make_request()
    setattr(req.state, "elapsed_ms", 12.3)
    resp = run(h.handle(req, _ok))  # pyright: ignore[reportArgumentType]
    assert resp.status_code == 200


def test_build_chain_wires_full_pipeline():
    chain = build_chain()
    # Walk the chain and collect the names.
    names = []
    node: MiddlewareHandler | None = chain
    while node is not None:
        names.append(node.name)
        node = node._next
    assert names == ["request_id", "timing", "logging", "error_translator", "rate_limit"]


def test_error_response_still_gets_request_id_and_timing_headers():
    """When a handler below ErrorTranslating raises, the synthesized 500
    response must still pass through RequestID and Timing on the way out so
    callers can correlate the error with a request id."""
    chain = build_chain()
    req = make_request(headers={"X-Request-ID": "corr-abc"})

    async def boom(_request):
        raise RuntimeError("kaboom")

    resp = run(chain.handle(req, boom))  # pyright: ignore[reportArgumentType]
    assert resp.status_code == 500
    assert resp.headers["X-Request-ID"] == "corr-abc"
    assert "X-Process-Time-Ms" in resp.headers


def test_full_chain_response_has_all_headers():
    chain = build_chain()
    req = make_request()
    resp = run(chain.handle(req, _ok))  # pyright: ignore[reportArgumentType]
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"]
    assert resp.headers["X-Process-Time-Ms"]


def test_short_circuit_skips_lower_links():
    """Rate-limit returning 429 means the terminal is never called."""
    chain = build_chain()
    # Burn out one IP's budget on the same chain.
    req = make_request(client_host="5.5.5.5")
    # The default budget is high (240). Replace the rate handler with a tight one.
    node = chain
    while node and not isinstance(node, RateLimitHandler):
        node = node._next
    assert isinstance(node, RateLimitHandler)
    node._max = 1
    run(chain.handle(req, _ok))  # pyright: ignore[reportArgumentType]
    blocked = run(chain.handle(req, _ok))  # pyright: ignore[reportArgumentType]
    assert blocked.status_code == 429

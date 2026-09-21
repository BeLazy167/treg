"""The relay carries a caller's declared Content-Length upstream instead of re-framing the body chunked.

Meta's Graph API edge does not read a `Transfer-Encoding: chunked` request body: every relayed
POST arrived bodyless and an ad creative failed "Ad incomplete" (live, 2026-09-19). The bytes are
the caller's, unaltered, so the caller's own length is exact.
"""

from __future__ import annotations

import httpx
import pytest

from treg.application.call.types import UpstreamRequest
from treg.infra.upstream import relay as relay_module
from treg.models import Tool


def _tool() -> Tool:
    return Tool(org_id=1, name="echo", owner="t", base_url="https://echo.example",
                host="echo.example", bindings=[])


async def _relay(monkeypatch, raw_headers: tuple[tuple[bytes, bytes], ...]) -> httpx.Headers:
    seen: dict[str, httpx.Headers] = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        seen["headers"] = req.headers
        try:
            seen["body"] = req.content
        except httpx.RequestNotRead:
            seen["body"] = b"".join([chunk async for chunk in req.stream])
        return httpx.Response(200, content=b"ok")

    async def body():
        yield b"abc"

    monkeypatch.setattr(relay_module.get_settings(), "proxy_ssrf_check", False, raising=False)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        req = UpstreamRequest(method="POST", raw_headers=raw_headers, query_items=(),
                              body_stream=body, has_body=True)
        resp = await relay_module.relay(req, "https://echo.example/p", _tool(), {}, client)
        assert resp.status == 200
        await resp.close()
    assert seen["body"] == b"abc"
    return seen["headers"]


@pytest.mark.asyncio
async def test_declared_content_length_is_carried_not_chunked(monkeypatch) -> None:
    headers = await _relay(monkeypatch, ((b"content-type", b"application/json"),
                                         (b"content-length", b"3")))
    assert headers.get("content-length") == "3"
    assert "transfer-encoding" not in headers


@pytest.mark.asyncio
async def test_chunked_caller_stays_chunked(monkeypatch) -> None:
    headers = await _relay(monkeypatch, ((b"content-type", b"application/json"),
                                         (b"transfer-encoding", b"chunked")))
    assert headers.get("transfer-encoding") == "chunked"
    assert "content-length" not in headers

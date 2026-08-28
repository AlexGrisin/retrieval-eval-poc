"""The seam that makes the mock disposable.

The skill talks to a KnowledgeClient. Three implementations exist today:
FakeKnowledgeGraph (in process), MCPKnowledgeClient, RESTKnowledgeClient. When
the real server exists, whichever of the latter two matches its actual
transport is what changes -- the skill, the cases, and the harness do not.

Both network clients funnel through _response_from_payload(): the only thing
that differs between transports is HOW a dict is obtained from the wire (an
MCP CallToolResult vs an httpx Response), never how that dict becomes a
SearchResponse. One parsing path, so the two transports cannot silently
diverge on it.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Protocol

from .contracts import Citation, Entity, SearchHit, SearchRequest, SearchResponse


class KnowledgeClient(Protocol):
    def search(self, request: SearchRequest) -> SearchResponse: ...


class SpyClient:
    """Wraps any client and records the tool call that was actually emitted.

    This is what makes L1 assertions real rather than circular: we check what
    the skill *sent*, not just what the backend chose to return.

    Also times each call. Transport-agnostic on purpose: wrapping here (not in
    the runner) captures MCP/REST round-trip and serialization overhead too,
    not just the fake backend's own compute time -- real signal even before a
    real server exists, per LATENCY-MEASUREMENT-PLAN.md.
    """

    def __init__(self, inner: KnowledgeClient) -> None:
        self._inner = inner
        self.calls: list[dict[str, Any]] = []
        self.durations_ms: list[float] = []

    def search(self, request: SearchRequest) -> SearchResponse:
        self.calls.append(request.as_tool_call())
        start = time.perf_counter()
        try:
            return self._inner.search(request)
        finally:
            self.durations_ms.append((time.perf_counter() - start) * 1000)

    @property
    def last_call(self) -> dict[str, Any] | None:
        return self.calls[-1] if self.calls else None

    @property
    def last_duration_ms(self) -> float | None:
        return self.durations_ms[-1] if self.durations_ms else None


class MCPKnowledgeClient:
    """Talks to a knowledge server over MCP instead of in process.

    `target` is anything the SDK's Client accepts: an MCPServer instance
    (in-memory transport, used by the suite), or a URL string for a running
    server.

    Imports the SDK lazily so in-process ranking runs do not load MCP.
    """

    def __init__(self, target: Any) -> None:
        self._target = target

    def search(self, request: SearchRequest) -> SearchResponse:
        return asyncio.run(self._call(request))

    async def _call(self, request: SearchRequest) -> SearchResponse:
        from mcp.client.client import Client

        args = request.as_tool_call()["args"]
        async with Client(self._target, raise_exceptions=True) as client:
            result = await client.call_tool("kb_search", args)
        return _response_from_payload(_payload_from_mcp_result(result))

    def __repr__(self) -> str:  # shows up in run records
        return f"MCPKnowledgeClient({self._target!r})"


class RESTKnowledgeClient:
    """Talks to a knowledge server over REST instead of in process.

    `target` is either a running server's base URL (e.g.
    "http://localhost:8001"), or a FastAPI app instance -- in the latter case
    httpx's ASGITransport talks to it in-process, the REST equivalent of
    MCPKnowledgeClient's in-memory transport, so the suite never binds a real
    port.
    """

    def __init__(self, target: Any) -> None:
        self._target = target

    def search(self, request: SearchRequest) -> SearchResponse:
        return asyncio.run(self._call(request))

    async def _call(self, request: SearchRequest) -> SearchResponse:
        import httpx

        body = request.as_tool_call()["args"]
        if isinstance(self._target, str):
            client_kwargs: dict[str, Any] = {"base_url": self._target}
        else:
            client_kwargs = {
                "transport": httpx.ASGITransport(app=self._target),
                "base_url": "http://test",
            }
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.post("/kb/search", json=body)
        if resp.status_code != 200:
            raise ValueError(f"REST call failed [{resp.status_code}]: {resp.text}")
        return _response_from_payload(resp.json())

    def __repr__(self) -> str:  # shows up in run records
        return f"RESTKnowledgeClient({self._target!r})"


def _payload_from_mcp_result(result: Any) -> dict[str, Any]:
    """Extract the response dict from an MCP CallToolResult.

    Structured output may or may not be present; the text fallback is a JSON
    blob that has to be sniffed. This is the part that does not exist in an
    in-process call, and it is where real integrations break.
    """
    payload: dict[str, Any] | None = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    if payload is not None:
        return payload

    text = ""
    for block in getattr(result, "content", []) or []:
        text += getattr(block, "text", "")
    if not text:
        raise ValueError(f"no parseable content in tool result: {result!r}")
    return json.loads(text)


def _response_from_payload(payload: dict[str, Any]) -> SearchResponse:
    """The one place a wire dict becomes a SearchResponse, for every transport."""
    if not isinstance(payload, dict) or "results" not in payload:
        raise ValueError(f"response does not match the response contract: {payload!r}")

    return SearchResponse(
        results=[
            SearchHit(
                entity=Entity(**row["entity"]),
                title=row["title"],
                snippet=row["snippet"],
                score=row["score"],
                matched_by=row["matched_by"],
                citations=[Citation(**c) for c in row.get("citations", [])],
            )
            for row in payload["results"]
        ],
    )

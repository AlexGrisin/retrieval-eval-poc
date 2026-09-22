"""The client that talks to the real knowledge server over MCP.

The skill talks to a KnowledgeClient; MCPKnowledgeClient is the one
implementation, and it is a thin wire adapter -- the skill, the cases, and the
harness build and consume transport-neutral contracts (skill/contracts.py)
regardless of what sits on the other end of `target`.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Protocol

from .contracts import Citation, Entity, SearchHit, SearchRequest, SearchResponse

# The knowledge server's kb_search envelope key, confirmed against a live call --
# see skill/client.py's _response_from_payload docstring.
WIRE_RESULTS_KEY = "result"


class KnowledgeClient(Protocol):
    def search(self, request: SearchRequest) -> SearchResponse: ...


class SpyClient:
    """Wraps any client and records the tool call that was actually emitted.

    This is what makes L1 assertions real rather than circular: we check what
    the skill *sent*, not just what the backend chose to return.

    Also times each call. Wrapping here (not in the runner) captures the real
    MCP round-trip and serialization overhead, not just skill-side compute time,
    per LATENCY-MEASUREMENT-PLAN.md.
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
    """Talks to the real knowledge server over MCP.

    `target` is anything the SDK's Client accepts -- in practice a streamable-HTTP
    URL such as http://127.0.0.1:8000/mcp.

    Imports the SDK lazily so importing this module never requires it.
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


def _payload_from_mcp_result(result: Any) -> dict[str, Any]:
    """Extract the response dict from an MCP CallToolResult.

    Structured output may or may not be present; the text fallback is a JSON
    blob that has to be sniffed.
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
    """The one place a wire dict becomes a SearchResponse.

    The knowledge server returns its hits under `result`, not `results` -- verified
    against tools/list and a live kb_search call. Parsed strictly: accepting both
    spellings would let the server rename the envelope without any test noticing,
    which is the drift this layer exists to catch.
    """
    if not isinstance(payload, dict) or WIRE_RESULTS_KEY not in payload:
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
            for row in payload[WIRE_RESULTS_KEY]
        ],
    )

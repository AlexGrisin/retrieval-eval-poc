"""Deterministic validation at the skill/client/server contract boundaries."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import ValidationError

from skill.schemas import SearchResponseOut


def expected_tool_call(case: dict) -> dict:
    """Build the request oracle from case data, independently of skill contracts."""
    return {
        "tool": "kb_search",
        "args": {
            "domain": case["domain"],
            "query": case["query"],
            "limit": case.get("limit", 10),
        },
    }


def check_emitted_tool_call(actual: dict | None, case: dict) -> str | None:
    """Compare the emitted call with the case's independent request oracle."""
    expected = case.get("expect_tool_call") or expected_tool_call(case)
    normalized_expected = json.loads(json.dumps(expected))
    normalized_actual = json.loads(json.dumps(actual))
    if normalized_actual == normalized_expected:
        return None
    return (
        "tool call mismatch\n"
        f"    expected: {normalized_expected}\n"
        f"    actual:   {normalized_actual}"
    )


def check_response_contract(response: Any) -> str | None:
    """Require the decoded response to match the published response schema."""
    try:
        payload = response.as_dict()
        SearchResponseOut.model_validate(payload, strict=True)
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        return f"response does not match the published contract: {exc}"
    return None


def check_server_rejects_invalid_request(
    spy: Any,
    query: str,
    domain: str,
    invalid_fields: dict,
    transport: str,
) -> str | None:
    """Bypass the skill and require the server boundary to reject invalid input."""
    args = {"domain": domain, "query": query, **invalid_fields}

    def mentions_invalid_field(message: str) -> bool:
        lowered = message.lower()
        return any(str(key).lower() in lowered for key in invalid_fields)

    if transport == "mcp":
        from mcp.client.client import Client

        async def call_mcp():
            async with Client(spy._inner._target) as client:
                return await client.call_tool("kb_search", args)

        try:
            result = asyncio.run(call_mcp())
        except Exception as exc:
            if mentions_invalid_field(str(exc)):
                return None
            return f"server rejected the call for the wrong reason: {exc}"
        if not getattr(result, "is_error", False):
            return "server accepted an invalid request"
        error_text = " ".join(
            getattr(block, "text", "") for block in getattr(result, "content", []) or []
        )
        if mentions_invalid_field(error_text):
            return None
        return f"server rejected the call for the wrong reason: {error_text or result!r}"

    if transport == "rest":
        import httpx

        async def call_rest():
            target = spy._inner._target
            client_args = (
                {"base_url": target}
                if isinstance(target, str)
                else {
                    "transport": httpx.ASGITransport(app=target),
                    "base_url": "http://test",
                }
            )
            async with httpx.AsyncClient(**client_args) as client:
                return await client.post("/kb/search", json=args)

        response = asyncio.run(call_rest())
        if response.status_code == 422:
            if mentions_invalid_field(response.text):
                return None
            return f"server rejected the call for the wrong reason: {response.text}"
        if response.status_code == 200:
            return "server accepted an invalid request"
        return (
            "server rejected the call for the wrong reason: "
            f"[{response.status_code}] {response.text}"
        )

    raise ValueError(f"no server-side check defined for transport {transport!r}")

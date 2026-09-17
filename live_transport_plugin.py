"""Pytest plugin: let --transport mcp target a real, network-reachable server.

    .venv/bin/pytest -m evaluation --transport mcp \\
        -p live_transport_plugin --live-server-url http://127.0.0.1:8000/mcp

Opt-in only. Without --live-server-url this plugin does nothing, and
--transport mcp keeps meaning exactly what it means everywhere else in this
repo: an in-process fake, no port bound (see harness/runner.py::make_skill).
That meaning matters to every other consumer -- the default pytest suite,
probe.py -- so it is redirected conditionally, from a separate opt-in
plugin, rather than changed at its source.

Reusing this over a bespoke script (see run_live_eval.py, an earlier,
simpler cut at the same idea) buys the whole pytest suite for free: the same
case:level:check IDs, the same Allure suite/story attachments and captured
JSON, xdist's single-process guard for --transport mcp, everything -- for
free, because the only thing this plugin changes is which KnowledgeClient
make_skill("mcp", ...) builds.

Known integration finding this plugin works around, not fixes: the live
knowledge-server wraps kb_search hits under a top-level "result" key, but
skill/client.py's _response_from_payload expects "results" and cannot parse
a real response. LiveMCPClient below does its own parsing instead of
patching that function -- the mismatch is a real contract bug worth fixing
in skill/client.py separately, not something to paper over indefinitely.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import harness.runner as runner
from skill.client import SpyClient, _payload_from_mcp_result
from skill.contracts import Citation, Entity, SearchHit, SearchResponse
from skill.skill import SearchSkill


def pytest_addoption(parser):
    parser.addoption(
        "--live-server-url",
        action="store",
        default=None,
        help="when set, --transport mcp targets this real MCP server instead "
        "of the in-process fake (requires -p live_transport_plugin)",
    )


class LiveMCPClient:
    """Same KnowledgeClient interface as skill.client.MCPKnowledgeClient, but
    parses the real server's actual response envelope (top-level "result",
    not "results" -- see module docstring)."""

    def __init__(self, url: str) -> None:
        # Named _target, not _url: harness/validators/contract.py's
        # check_server_rejects_invalid_request reaches into spy._inner._target
        # directly to open its own raw connection for the invalid-request probe,
        # matching skill.client.MCPKnowledgeClient's exact attribute name.
        self._target = url

    def search(self, request):
        return asyncio.run(self._call(request))

    async def _call(self, request):
        from mcp.client.client import Client

        args = request.as_tool_call()["args"]
        async with Client(self._target, raise_exceptions=True) as client:
            result = await client.call_tool("kb_search", args)
        payload = _payload_from_mcp_result(result)
        rows = payload.get("result", payload.get("results", []))
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
                for row in rows
            ]
        )

    def __repr__(self) -> str:
        return f"LiveMCPClient({self._target!r})"


def make_live_skill(url: str) -> tuple[SearchSkill, SpyClient]:
    spy = SpyClient(LiveMCPClient(url))
    return SearchSkill(spy), spy


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    url = config.getoption("--live-server-url")
    if not url:
        return

    original_make_skill = runner.make_skill

    def patched_make_skill(corpus: Path, transport: str):
        if transport == "mcp":
            return make_live_skill(url)
        return original_make_skill(corpus, transport)

    runner.make_skill = patched_make_skill

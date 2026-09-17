#!/usr/bin/env python3
"""Run the case suite against a LIVE, network-reachable knowledge server.

    python3 run_live_eval.py --server-url http://127.0.0.1:8000/mcp --domain paastry

Every other case-driven entry point (pytest's --transport mcp/rest, and
probe.py) talks to an in-process fake seeded from fixtures/corpus.yaml -- see
harness/runner.py::make_skill. None of them ever bind a real port or talk to
a real backend. This script reuses that same exact evaluation code
(harness.runner.run_case: same checks, same ranking metrics) but points it at
a real server instead, through one narrow, in-memory monkeypatch of
make_skill -- the function the module's own docstring already calls "the
seam" for swapping backends. It does not touch make_skill on disk, and it
adds no new pytest transport.

Known integration finding (worked around here, not fixed -- see
LiveMCPClient): the live knowledge-server wraps kb_search hits under a
top-level "result" key. skill/client.py's _response_from_payload expects
"results" and raises trying to parse a real response. That mismatch is a
real contract bug between this repo's assumptions and the live server; it
belongs in the checked-in client eventually, not permanently papered over
here.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import harness.runner as runner  # noqa: E402
from harness.definitions.cases import load_cases  # noqa: E402
from skill.client import SpyClient, _payload_from_mcp_result  # noqa: E402
from skill.contracts import Citation, Entity, SearchHit, SearchResponse  # noqa: E402
from skill.skill import SearchSkill  # noqa: E402


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


def install_live_transport(server_url: str) -> None:
    """Monkeypatch harness.runner.make_skill for transport="live", in this
    process only. Falls through to the original for every other transport."""
    original_make_skill = runner.make_skill

    def patched_make_skill(corpus: Path, transport: str):
        if transport == "live":
            return make_live_skill(server_url)
        return original_make_skill(corpus, transport)

    runner.make_skill = patched_make_skill


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--server-url", default="http://127.0.0.1:8000/mcp")
    ap.add_argument(
        "--domain", default=None, help="only run cases for this domain, e.g. paastry"
    )
    ap.add_argument(
        "--cases", default=str(ROOT / "cases"), help="case directory to load"
    )
    args = ap.parse_args()

    install_live_transport(args.server_url)

    dummy_corpus = ROOT / "fixtures" / "corpus.yaml"  # unused for transport="live"
    cases = load_cases(Path(args.cases))
    if args.domain:
        cases = [c for c in cases if c.get("domain") == args.domain]

    exit_code = 0
    for case in cases:
        result = runner.run_case(case, dummy_corpus, "live")
        status = "PASS" if result["passed"] else "FAIL"
        if not result["passed"]:
            exit_code = 1
        print(f"{status}  {case['id']}  metrics={result['metrics']}")
        for check in result["checks"]:
            if check["status"] == "fail":
                print(f"    FAIL {check['name']}: {check['detail']}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

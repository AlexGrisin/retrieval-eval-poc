#!/usr/bin/env python3
"""Manual probe: drive the kb_search skill by hand.

    python3 probe.py "why was the pricing rounding bug fixed?"
    python3 probe.py "..." --domain paastry --show-call
    python3 probe.py                      # interactive; blank line or Ctrl-D to quit

Prints exactly what the skill renders, so what you see here is what an agent
would receive. --show-call prints the MCP tool call that was emitted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from skill.client import SpyClient
from skill.contracts import ContractError
from skill.fake_server import FakeKnowledgeGraph
from skill.skill import SearchSkill


def build(corpus: str, transport: str = "inprocess") -> tuple[SearchSkill, SpyClient]:
    if transport == "mcp":
        from server_mcp import build_server
        from skill.client import MCPKnowledgeClient

        spy = SpyClient(MCPKnowledgeClient(build_server(corpus)))
    elif transport == "rest":
        from server_rest import build_app
        from skill.client import RESTKnowledgeClient

        spy = SpyClient(RESTKnowledgeClient(build_app(corpus)))
    else:
        spy = SpyClient(FakeKnowledgeGraph(corpus))
    return SearchSkill(spy), spy


def ask(skill: SearchSkill, spy: SpyClient, query: str, args) -> None:
    try:
        result = skill.search(domain=args.domain, query=query, limit=args.limit)
    except ContractError as exc:
        print(f"\nContractError: {exc}\n(correct behaviour -- the argument was "
              "rejected, not silently dropped)\n")
        return

    if args.show_call:
        print("\n--- emitted MCP tool call " + "-" * 40)
        print(json.dumps(spy.last_call, indent=2))

    print("\n--- what the agent receives " + "-" * 38)
    print(result.rendered)
    if args.scores:
        print("--- scores " + "-" * 53)
        for hit in result.response.results:
            print(f"  {hit.entity.identity}  score={hit.score}  {hit.matched_by}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?")
    ap.add_argument("--domain", default="paastry")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--show-call", action="store_true")
    ap.add_argument("--scores", action="store_true")
    ap.add_argument("--corpus", default=str(ROOT / "fixtures" / "corpus.yaml"))
    ap.add_argument("--transport", choices=["inprocess", "mcp", "rest"], default="inprocess")
    args = ap.parse_args()

    skill, spy = build(args.corpus, args.transport)

    if args.query:
        ask(skill, spy, args.query, args)
        return 0

    print(f"domain {args.domain}   (blank line to quit)")
    while True:
        try:
            q = input("\nquery> ").strip()
        except EOFError:
            return 0
        if not q:
            return 0
        ask(skill, spy, q, args)


if __name__ == "__main__":
    raise SystemExit(main())

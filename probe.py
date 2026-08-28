#!/usr/bin/env python3
"""Manual probe: drive the retrieval skill by hand.

    python3 probe.py "how do we handle retries on payment failures?"
    python3 probe.py "..." --department finance --show-call
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
from skill.fake_server import FakeKnowledgeServer
from skill.skill import RetrievalSkill


def build(corpus: str, transport: str = "inprocess") -> tuple[RetrievalSkill, SpyClient]:
    if transport == "mcp":
        from server_mcp import build_server
        from skill.client import MCPKnowledgeClient

        spy = SpyClient(MCPKnowledgeClient(build_server(corpus)))
    elif transport == "rest":
        from server_rest import build_app
        from skill.client import RESTKnowledgeClient

        spy = SpyClient(RESTKnowledgeClient(build_app(corpus)))
    else:
        spy = SpyClient(FakeKnowledgeServer(corpus))
    return RetrievalSkill(spy), spy


def ask(skill: RetrievalSkill, spy: SpyClient, query: str, args) -> None:
    filters: dict = {"validity": args.validity}
    if args.veracity:
        filters["veracity"] = args.veracity
    if args.domain:
        filters["domain"] = args.domain
    if args.bad_filter:
        filters["colour"] = "red"  # deliberately invalid, to see the contract bite

    try:
        result = skill.retrieve(
            query=query,
            context={"department": args.department, "product": args.product},
            filters=filters,
            k=args.k,
            output_format=args.format,
        )
    except ContractError as exc:
        print(f"\nContractError: {exc}\n(correct behaviour -- the filter was rejected,"
              " not silently dropped)\n")
        return

    if args.show_call:
        print("\n--- emitted MCP tool call " + "-" * 40)
        print(json.dumps(spy.last_call, indent=2))

    print("\n--- what the agent receives " + "-" * 38)
    print(result.rendered)
    if args.scores:
        print("--- scores " + "-" * 53)
        for r in result.response.results:
            print(f"  {r.note_id}@{r.version}  score={r.score}  {r.veracity}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?")
    ap.add_argument("--department", default="commerce")
    ap.add_argument("--product", default="shop")
    ap.add_argument("--veracity", nargs="*", default=["verified"])
    ap.add_argument("--validity", default="current",
                    help="'current' hides superseded notes; any other value shows them")
    ap.add_argument("--domain", nargs="*")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--format", default="full",
                    choices=["brief", "full", "citations_only"])
    ap.add_argument("--show-call", action="store_true")
    ap.add_argument("--scores", action="store_true")
    ap.add_argument("--bad-filter", action="store_true",
                    help="inject an unknown filter key to see it rejected")
    ap.add_argument("--corpus", default=str(ROOT / "fixtures" / "corpus.yaml"))
    ap.add_argument("--transport", choices=["inprocess", "mcp", "rest"], default="inprocess")
    args = ap.parse_args()

    skill, spy = build(args.corpus, args.transport)

    if args.query:
        ask(skill, spy, args.query, args)
        return 0

    print(f"scope {args.department}/{args.product} · veracity {args.veracity} "
          f"· validity {args.validity}   (blank line to quit)")
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

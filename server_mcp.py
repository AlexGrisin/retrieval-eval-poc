#!/usr/bin/env python3
"""A stand-in knowledge server, exposed over MCP.

Same fake backend as the in-process suite: same corpus, same token-overlap
ranking, same meaningless scores. What this adds is a real protocol boundary,
so the request crosses a declared input schema, serialises to JSON, and comes
back as content blocks.

The one behavioural difference that matters: the closed argument vocabulary is
enforced *here*, by the tool's own schema (`extra="forbid"`), rather than only
client side in `SearchRequest.__post_init__`. The platform's own principle is
that a client side check can be bypassed, so this is the first point at which
that contract is actually enforced.

    python3 server_mcp.py                 # stdio, for agent registration
    python3 server_mcp.py --http          # streamable HTTP, for Verity and browsers

This file is the only one that imports the mcp SDK. Wire schemas (SearchIn,
SearchResponseOut) live in skill/schemas.py, shared with server_rest.py, so MCP
and REST validate against the same pydantic models rather than two definitions
that could drift. The MCP SDK remains optional for in-process ranking runs.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from skill.contracts import SearchRequest
from skill.fake_server import FakeKnowledgeGraph
from skill.schemas import Domain, QueryText, SearchResponseOut

ROOT = Path(__file__).resolve().parent
DEFAULT_CORPUS = ROOT / "fixtures" / "corpus.yaml"


def build_server(corpus: str | Path = DEFAULT_CORPUS) -> MCPServer:
    backend = FakeKnowledgeGraph(corpus)
    server = MCPServer(
        name="knowledge-server-stand-in",
        instructions=(
            "Stand-in knowledge graph over fixture data. Ranking is token overlap, "
            "not embeddings: results are structurally correct and qualitatively "
            "meaningless. Do not treat scores as retrieval quality."
        ),
    )

    @server.tool(
        name="kb_search",
        description=(
            "Find entities in a domain's knowledge graph by free text. Returns "
            "ranked, deduplicated hits carrying entity identity and citations."
        ),
    )
    def kb_search(
        domain: Domain,
        query: QueryText,
        limit: int = 10,
    ) -> SearchResponseOut:
        request = SearchRequest(domain=domain, query=query, limit=limit)
        return SearchResponseOut(**backend.search(request).as_dict())

    return server


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--http", action="store_true", help="serve streamable HTTP")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    server = build_server(args.corpus)
    if args.http:
        os.environ.setdefault("PORT", str(args.port))
        asyncio.run(server.run_streamable_http_async())
    else:
        asyncio.run(server.run_stdio_async())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

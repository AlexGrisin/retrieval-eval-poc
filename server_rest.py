#!/usr/bin/env python3
"""A stand-in knowledge server, exposed over REST.

Same fake backend as server_mcp.py -- same corpus, same token-overlap ranking,
same meaningless scores, same fixture data. This is the second of the surfaces
the Component Guide names for the Knowledge server ("MCP, REST, and CLI"),
built specifically to make the multi-transport risk testable rather than
assumed: one contract, multiple surfaces, nothing forcing them to agree unless
the same cases run against each and produce identical results.

Validates against the SAME pydantic models as the MCP server
(skill/schemas.py), so the closed argument vocabulary and the response shape
cannot drift between transports independently -- FastAPI's request/response
validation IS the schema enforcement here, the direct REST equivalent of the
MCP tool's published input_schema/output_schema.

    python3 server_rest.py                  # uvicorn on :8001
    python3 server_rest.py --port 9000

For tests, the suite never binds a real port: httpx's ASGITransport talks to
the FastAPI app in-process, the REST equivalent of MCP's InMemoryTransport.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI, HTTPException

from skill.contracts import SearchRequest
from skill.fake_server import FakeKnowledgeGraph
from skill.schemas import SearchIn, SearchResponseOut

ROOT = Path(__file__).resolve().parent
DEFAULT_CORPUS = ROOT / "fixtures" / "corpus.yaml"


def build_app(corpus: str | Path = DEFAULT_CORPUS) -> FastAPI:
    backend = FakeKnowledgeGraph(corpus)
    app = FastAPI(
        title="knowledge-server-stand-in",
        description=(
            "Stand-in knowledge graph over fixture data. Ranking is token overlap, "
            "not embeddings: results are structurally correct and qualitatively "
            "meaningless. Do not treat scores as retrieval quality."
        ),
    )

    @app.post("/kb/search", response_model=SearchResponseOut)
    def kb_search(body: SearchIn) -> SearchResponseOut:
        request = SearchRequest(domain=body.domain, query=body.query, limit=body.limit)
        try:
            return SearchResponseOut(**backend.search(request).as_dict())
        except Exception as exc:  # pydantic validation failure building the response
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args()

    import uvicorn

    uvicorn.run(build_app(args.corpus), host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

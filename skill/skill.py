"""The kb_search skill itself.

Two responsibilities, in order, and nothing else:
  1. Turn a domain + query into a valid request.
  2. Invoke the knowledge server as one MCP tool call.

Explicitly NOT responsible for: enforcing access control, re-ranking, caching,
or filtering results after they arrive. All enforcement is server-side; a
client that post-filters is a client that can be bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import KnowledgeClient
from .contracts import SearchRequest, SearchResponse
from .formatter import render


@dataclass
class SearchResult:
    rendered: str
    response: SearchResponse
    request: SearchRequest


class SearchSkill:
    def __init__(self, client: KnowledgeClient, default_limit: int = 10) -> None:
        self._client = client
        self._default_limit = default_limit

    def search(
        self,
        domain: str,
        query: str,
        limit: int | None = None,
    ) -> SearchResult:
        request = SearchRequest(
            domain=domain,
            query=query,
            limit=limit or self._default_limit,
        )
        response = self._client.search(request)
        return SearchResult(
            rendered=render(request, response), response=response, request=request
        )

"""The retrieval skill itself.

Three responsibilities, in order, and nothing else:
  1. Turn caller context + filters into a valid request (closed filter vocabulary).
  2. Invoke the knowledge server as one MCP tool call.
  3. Format the response per the output contract.

Explicitly NOT responsible for: enforcing access control, re-ranking, caching,
or filtering results after they arrive. All enforcement is server-side; a client
that post-filters is a client that can be bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import KnowledgeClient
from .contracts import Filters, RetrieveRequest, RetrieveResponse, Scope
from .formatter import render


@dataclass
class RetrievalResult:
    rendered: str
    response: RetrieveResponse
    request: RetrieveRequest


class RetrievalSkill:
    def __init__(
        self,
        client: KnowledgeClient,
        default_k: int = 10,
        default_format: str = "full",
    ) -> None:
        self._client = client
        self._default_k = default_k
        self._default_format = default_format

    def retrieve(
        self,
        query: str,
        context: dict,
        filters: dict | None = None,
        k: int | None = None,
        output_format: str | None = None,
    ) -> RetrievalResult:
        request = RetrieveRequest(
            query=query,
            scope=Scope(
                department=context["department"], product=context.get("product")
            ),
            filters=Filters.from_dict(filters),
            k=k or self._default_k,
            format=output_format or self._default_format,
        )
        response = self._client.retrieve(request)
        return RetrievalResult(
            rendered=render(request, response), response=response, request=request
        )

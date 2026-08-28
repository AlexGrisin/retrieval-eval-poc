"""Wire contracts for the kb_search skill.

These dataclasses ARE the contract. They are deliberately dumb: no behaviour
beyond validation, so that swapping the fake backend for the real MCP client
cannot change the shape of a request or a response.

Swap to pydantic BaseModel when the project has it; field names stay identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

ALLOWED_MATCHED_BY = frozenset({"vector", "fulltext", "both"})


class ContractError(ValueError):
    """Raised when a caller violates the skill's request contract."""


@dataclass(frozen=True)
class SearchRequest:
    domain: str
    query: str
    limit: int = 10

    def __post_init__(self) -> None:
        if not self.domain.strip():
            raise ContractError("domain must not be blank")
        if not self.query.strip():
            raise ContractError("query must not be blank")
        if not (1 <= self.limit <= 200):
            raise ContractError("limit must be between 1 and 200")

    def as_tool_call(self) -> dict[str, Any]:
        """Exactly what goes over MCP. Tests assert on this dict."""
        return {
            "tool": "kb_search",
            "args": {
                "domain": self.domain,
                "query": self.query,
                "limit": self.limit,
            },
        }


@dataclass(frozen=True)
class Entity:
    """Addressed by label + business key, e.g. `Service / pricing-api`."""

    label: str
    key: str

    @property
    def identity(self) -> str:
        """The one identity string used everywhere a bare ID is needed."""
        return f"{self.label}/{self.key}"


@dataclass(frozen=True)
class Citation:
    source_system: str
    reference: str


@dataclass(frozen=True)
class SearchHit:
    entity: Entity
    title: str
    snippet: str
    score: float
    matched_by: str
    citations: list[Citation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.matched_by not in ALLOWED_MATCHED_BY:
            raise ContractError(f"unknown matched_by: {self.matched_by!r}")
        # A wrong-typed score (e.g. a string) is a wire-contract fault, not a
        # bounds fault -- leave it for the pydantic schema layer to catch by
        # type, same as every other field here. Dataclasses stay "dumb".
        if isinstance(self.score, (int, float)) and not (0.0 <= self.score <= 1.0):
            raise ContractError("score must be between 0 and 1")


@dataclass
class SearchResponse:
    results: list[SearchHit] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "results": [
                {
                    "entity": asdict(hit.entity),
                    "title": hit.title,
                    "snippet": hit.snippet,
                    "score": hit.score,
                    "matched_by": hit.matched_by,
                    "citations": [asdict(c) for c in hit.citations],
                }
                for hit in self.results
            ]
        }

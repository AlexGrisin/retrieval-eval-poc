"""Wire contracts for the retrieval skill.

These dataclasses ARE the contract. They are deliberately dumb: no behaviour
beyond validation, so that swapping the fake backend for the real MCP client
cannot change the shape of a request or a response.

Swap to pydantic BaseModel when the project has it; field names stay identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# The filter vocabulary is a CLOSED set. An unknown key is an error, never a
# silently ignored argument -- a dropped filter looks like better recall while
# actually being a scope leak, and that is the failure this guards.
ALLOWED_FILTER_KEYS = frozenset({"domain", "veracity", "validity", "memory_type"})
ALLOWED_VERACITY = frozenset({"verified", "derived"})
ALLOWED_FORMATS = frozenset({"brief", "full", "citations_only"})


class ContractError(ValueError):
    """Raised when a caller violates the skill's request contract."""


@dataclass(frozen=True)
class Scope:
    """Drives the vocabulary scope chain: product -> department -> core."""

    department: str
    product: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"department": self.department, "product": self.product}


@dataclass(frozen=True)
class Filters:
    domain: list[str] | None = None
    veracity: list[str] | None = None
    validity: str = "current"
    memory_type: list[str] | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "Filters":
        raw = raw or {}
        unknown = set(raw) - ALLOWED_FILTER_KEYS
        if unknown:
            raise ContractError(
                f"unknown filter key(s): {sorted(unknown)}; "
                f"allowed: {sorted(ALLOWED_FILTER_KEYS)}"
            )
        veracity = raw.get("veracity")
        if veracity is not None:
            bad = set(veracity) - ALLOWED_VERACITY
            if bad:
                raise ContractError(f"unknown veracity value(s): {sorted(bad)}")
        return cls(
            domain=raw.get("domain"),
            veracity=veracity,
            validity=raw.get("validity", "current"),
            memory_type=raw.get("memory_type"),
        )

    def as_dict(self) -> dict[str, Any]:
        # Only non-null keys go on the wire, so the emitted call is easy to assert on.
        out: dict[str, Any] = {"validity": self.validity}
        for key in ("domain", "veracity", "memory_type"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out


@dataclass(frozen=True)
class RetrieveRequest:
    query: str
    scope: Scope
    filters: Filters
    k: int = 10
    format: str = "full"

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ContractError("query must not be blank")
        if self.format not in ALLOWED_FORMATS:
            raise ContractError(f"unknown format: {self.format}")
        if self.k <= 0:
            raise ContractError("k must be positive")

    def as_tool_call(self) -> dict[str, Any]:
        """Exactly what goes over MCP. Tests assert on this dict.

        Named with an underscore rather than `knowledge.retrieve`: MCP tool names
        come from Python identifiers and dots are not portable across clients. A
        contract change, small but real, and the request-contract case changed with it.
        """
        return {
            "tool": "knowledge_retrieve",
            "args": {
                "query": self.query,
                "scope": self.scope.as_dict(),
                "filters": self.filters.as_dict(),
                "k": self.k,
                "format": self.format,
            },
        }


@dataclass(frozen=True)
class NoteResult:
    note_id: str
    version: int
    title: str
    claim: str
    veracity: str
    valid_to: str | None
    source_system: str
    source_locator: str
    source_version: str
    score: float

    @property
    def note_ref(self) -> str:
        return f"{self.note_id}@{self.version}"

    @property
    def source_ref(self) -> str:
        return f"{self.source_system}:{self.source_locator}@{self.source_version}"


@dataclass
class RetrieveResponse:
    results: list[NoteResult] = field(default_factory=list)
    facets: dict[str, dict[str, int]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "results": [asdict(r) for r in self.results],
            "facets": self.facets,
        }

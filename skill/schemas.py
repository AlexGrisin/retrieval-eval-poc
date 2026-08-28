"""Wire schemas shared across every server transport.

Defined once, imported by server_mcp.py and server_rest.py both. One contract,
multiple surfaces, nothing forcing them to agree. Two independent pydantic
definitions of "a search hit" can drift silently; one definition imported
twice cannot.

These mirror skill.contracts.SearchHit / SearchResponse exactly. That pair is
the transport-free dataclass contract the skill and the test suite use; these
are the same shape declared as pydantic models so each transport's SDK can
publish a real schema (extra="forbid" on the way in, on the way out).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

QueryText = Annotated[
    str,
    Field(min_length=1, pattern=r"\S", description="Non-blank retrieval query"),
]

Domain = Annotated[
    str,
    Field(min_length=1, pattern=r"\S", description="Domain every call is scoped to"),
]


class SearchIn(BaseModel):
    """The full request body, transport-neutral (an MCP tool call unpacks these
    as separate arguments; a REST endpoint accepts this as one JSON body)."""

    model_config = ConfigDict(extra="forbid")

    domain: Domain
    query: QueryText
    limit: Annotated[int, Field(ge=1, le=200)] = 10


class EntityOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    key: str


class CitationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_system: str
    reference: str


class SearchHitOut(BaseModel):
    """Mirrors skill.contracts.SearchHit. A real server returning a renamed or
    missing field fails at the schema, before any client-side code runs."""

    model_config = ConfigDict(extra="forbid")

    entity: EntityOut
    title: str
    snippet: str
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    matched_by: Literal["vector", "fulltext", "both"]
    citations: list[CitationOut]


class SearchResponseOut(BaseModel):
    """Mirrors skill.contracts.SearchResponse."""

    model_config = ConfigDict(extra="forbid")

    results: list[SearchHitOut]

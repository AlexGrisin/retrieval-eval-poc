"""The published response schema, checked against every decoded search result.

Mirrors skill.contracts.SearchHit / SearchResponse exactly. That pair is the
transport-free dataclass contract the skill and the test suite use; this is
the same shape declared as a pydantic model (extra="forbid") so
harness/validators/contract.py::check_response_contract can catch a renamed,
missing, or wrongly typed field before it reaches the skill.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


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

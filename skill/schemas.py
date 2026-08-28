"""Wire schemas shared across every server transport.

Defined once, imported by server_mcp.py and server_rest.py both. This is the
fix for the risk named when REST was still deferred: one contract, multiple
surfaces, nothing forcing them to agree. Two independent pydantic definitions
of "a note result" can drift silently; one definition imported twice cannot.

These mirror skill.contracts.NoteResult / RetrieveResponse exactly. That pair
is the transport-free dataclass contract the skill and the test suite use;
these are the same shape declared as pydantic models so each transport's SDK
can publish a real schema (extra="forbid" on the way in, on the way out).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

QueryText = Annotated[
    str,
    Field(min_length=1, pattern=r"\S", description="Non-blank retrieval query"),
]


class ScopeIn(BaseModel):
    """Caller scope. Drives the vocabulary scope chain: product, department, core."""

    model_config = ConfigDict(extra="forbid")

    department: str = Field(description="Owning department, e.g. commerce")
    product: str | None = Field(default=None, description="Product or experience")


class FiltersIn(BaseModel):
    """Closed filter vocabulary. An unknown key is rejected, never ignored."""

    model_config = ConfigDict(extra="forbid")

    domain: list[str] | None = None
    veracity: list[Literal["verified", "derived"]] | None = None
    validity: str = "current"
    memory_type: list[str] | None = None


class RetrieveIn(BaseModel):
    """The full request body, transport-neutral (an MCP tool call unpacks these
    as separate arguments; a REST endpoint accepts this as one JSON body)."""

    model_config = ConfigDict(extra="forbid")

    query: QueryText
    scope: ScopeIn
    filters: FiltersIn | None = None
    k: int = 10
    format: str = "full"


class NoteResultOut(BaseModel):
    """Mirrors skill.contracts.NoteResult. A real server returning a renamed or
    missing field fails at the schema, before any client-side code runs, rather
    than only being caught reactively when _parse() crashes on NoteResult(**row).
    """

    model_config = ConfigDict(extra="forbid")

    note_id: str
    version: int
    title: str
    claim: str
    veracity: Literal["verified", "derived"]
    valid_to: str | None
    source_system: str
    source_locator: str
    source_version: str
    score: float


class RetrieveResponseOut(BaseModel):
    """Mirrors skill.contracts.RetrieveResponse."""

    model_config = ConfigDict(extra="forbid")

    results: list[NoteResultOut]
    facets: dict[str, dict[str, int]]

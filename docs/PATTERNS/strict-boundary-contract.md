# Strict Boundary Contract (Pydantic v2)

## Description

Every payload that crosses a trust boundary — a wire request/response, a
judge input/output, a run manifest, a case's answer-evaluation contract —
is a `pydantic.BaseModel` with `model_config = ConfigDict(extra="forbid",
strict=True)`, plus `field_validator`s that reject blank/whitespace-only
strings. Extra fields and type coercion are both refused: a renamed,
missing, or wrongly-typed field fails loudly at the model boundary instead
of surfacing later as a confusing `AttributeError` or a silently-truncated
value.

A schema is defined **once** and imported everywhere it is needed, never
redefined per consumer. `skill/schemas.py` mirrors `skill/contracts.py`
exactly and is imported by both `server_mcp.py` and `server_rest.py`, so
the two transports validate against the same pydantic models rather than
two definitions that could drift apart silently.

Use this pattern whenever you add a new external-facing or cross-module
data contract: an agent response shape, a judge record, a wire request or
response body, a run manifest section, a case sub-schema.

**Evidence (read directly):**
- `skill/schemas.py` — `ScopeIn`, `FiltersIn`, `RetrieveIn`, `NoteResultOut`, `RetrieveResponseOut`
- `harness/agent/models.py` — `Citation`, `AgentResponse`, `AnswerExpectations`, `AnswerEvaluationSpec`, `AgentCheckResult`, `AgentRun`
- `harness/judges/models.py` — `JudgeInput`, `JudgeScore`, `JudgeRecord`, `JudgeOutcome`, `JudgeConfig`

## Template / Example

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MyBoundaryModel(BaseModel):
    """One line: what boundary this crosses and who owns the other side."""

    # EXTENSION POINT: always forbid extras and force strict typing —
    # a wire contract must fail on drift, not silently coerce or ignore it.
    model_config = ConfigDict(extra="forbid", strict=True)

    required_field: str = Field(min_length=1)
    optional_field: str | None = None

    # EXTENSION POINT: reject blank-but-nonempty strings explicitly;
    # min_length=1 alone still accepts "   ".
    @field_validator("required_field")
    @classmethod
    def required_field_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    # EXTENSION POINT: cross-field invariants go in a model_validator
    # (mode="after"), never checked ad hoc by a caller.
    @model_validator(mode="after")
    def cross_field_invariant(self) -> "MyBoundaryModel":
        return self
```

Do not redefine an equivalent shape a second time for a second transport or
consumer — import the one definition (see `multi-transport-adapter.md` for
how MCP and REST share `skill/schemas.py`).

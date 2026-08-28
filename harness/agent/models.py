"""Provisional evaluation-side contracts for a captured agent response.

The production answer-generating agent should ultimately own the response schema.
Until that contract exists, these strict models make the intended evaluation
boundary explicit without pretending that this POC executes a live agent.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Citation(BaseModel):
    """An answer's citation, identified the same way kb_search identifies
    entities: `label/key` (see skill.contracts.Entity.identity)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    label: str = Field(min_length=1)
    key: str = Field(min_length=1)

    @field_validator("label", "key")
    @classmethod
    def is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @property
    def ref(self) -> str:
        return f"{self.label}/{self.key}"


class AgentResponse(BaseModel):
    """Structured final response captured from an answer-generating agent."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["answered", "insufficient_context"]
    answer: str
    citations: list[Citation] = Field(default_factory=list)

    @field_validator("answer")
    @classmethod
    def answer_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("citations")
    @classmethod
    def citations_are_unique(cls, value: list[Citation]) -> list[Citation]:
        refs = [citation.ref for citation in value]
        if len(refs) != len(set(refs)):
            raise ValueError("citations must be unique")
        return value


class AnswerExpectations(BaseModel):
    """Exact, deterministic answer expectations declared by a case."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["answered", "insufficient_context"] | None = None
    required_citations: list[Citation] = Field(default_factory=list)
    must_not_cite: list[Citation] = Field(default_factory=list)

    @field_validator("required_citations", "must_not_cite")
    @classmethod
    def citation_expectations_are_unique(
        cls, value: list[Citation]
    ) -> list[Citation]:
        refs = [citation.ref for citation in value]
        if len(refs) != len(set(refs)):
            raise ValueError("citation expectations must be unique")
        return value

    @model_validator(mode="after")
    def citation_expectations_do_not_conflict(self) -> "AnswerExpectations":
        required = {citation.ref for citation in self.required_citations}
        forbidden = {citation.ref for citation in self.must_not_cite}
        overlap = sorted(required & forbidden)
        if overlap:
            raise ValueError(
                f"citations cannot be both required and forbidden: {overlap}"
            )
        return self


class AnswerEvaluationSpec(BaseModel):
    """Answer expectations and judges attached to one evaluation case."""

    model_config = ConfigDict(extra="forbid", strict=True)

    expect: AnswerExpectations = Field(default_factory=AnswerExpectations)
    rubrics: list[str] = Field(min_length=1)
    reference_answer: str | None = None

    @field_validator("rubrics")
    @classmethod
    def rubrics_are_unique_and_nonblank(cls, value: list[str]) -> list[str]:
        if any(not rubric.strip() for rubric in value):
            raise ValueError("rubric names must not be blank")
        if len(value) != len(set(value)):
            raise ValueError("rubric names must be unique")
        return value

    @field_validator("reference_answer")
    @classmethod
    def reference_answer_is_nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def correctness_has_reference(self) -> "AnswerEvaluationSpec":
        if "answer_correctness" in self.rubrics and not self.reference_answer:
            raise ValueError("answer_correctness requires reference_answer")
        return self


class AgentCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    status: Literal["ok", "fail", "skip"]
    detail: str = ""
    traceability: str
    source: str


class AgentRun(BaseModel):
    """One captured execution shared by deterministic checks, metrics, and judges."""

    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str
    question: str
    retrieved_context: str
    response: AgentResponse | None
    retrieval_result: dict[str, Any]
    checks: list[AgentCheckResult]
    answer_passed: bool
    deterministic_passed: bool
    rubrics: list[str]
    reference_answer: str | None = None

"""Strict data contracts for generated-answer judging."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values, load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class JudgeConfigurationError(ValueError):
    pass


class JudgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str
    criterion: str
    question: str
    retrieved_context: str
    generated_answer: str
    reference_answer: str | None = None


class JudgeScore(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    criterion: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=1)

    @field_validator("criterion", "explanation")
    @classmethod
    def score_text_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class JudgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str
    criterion: str
    score: float
    explanation: str
    requested_model: str
    model_version: str
    actual_model: str
    prompt_version: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    prompt_hash: str
    rubric_hash: str
    input_hash: str
    cache_key: str
    cached: bool
    retrieval_passed: bool
    gateway_response_id: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)


class JudgeOutcome(BaseModel):
    """A semantic criterion was either scored or deliberately not run."""

    model_config = ConfigDict(extra="forbid", strict=True)

    criterion: str
    status: Literal["scored", "not_run"]
    record: JudgeRecord | None = None
    reason: str | None = None

    @field_validator("criterion")
    @classmethod
    def criterion_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def status_matches_payload(self) -> "JudgeOutcome":
        if self.status == "scored" and (self.record is None or self.reason is not None):
            raise ValueError("a scored outcome requires a record and no reason")
        if self.status == "not_run" and (self.record is not None or not self.reason):
            raise ValueError("a not_run outcome requires a reason and no record")
        return self


class JudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    gateway_url: str
    model_id: str
    model_version: str
    prompt_version: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    token: str | None = None
    timeout_seconds: float = Field(default=60.0, gt=0)

    @field_validator("gateway_url", "model_id", "model_version", "prompt_version")
    @classmethod
    def config_value_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("model_id", "model_version")
    @classmethod
    def model_is_pinned(cls, value: str) -> str:
        if value.lower().endswith("latest"):
            raise ValueError("must identify a pinned version, not 'latest'")
        return value

    @classmethod
    def from_env(
        cls,
        prompt_version: str,
        env_file: Path = DEFAULT_ENV_FILE,
    ) -> "JudgeConfig":
        # A project-local .env is authoritative when present. CI normally has
        # no such file and therefore falls back to its process environment.
        file_values = dotenv_values(env_file)
        load_dotenv(env_file, override=False)

        def setting(name: str) -> str:
            file_value = file_values.get(name)
            if isinstance(file_value, str) and file_value.strip():
                return file_value
            return os.getenv(name, "")

        values = {
            "gateway_url": setting("LLM_GATEWAY_URL"),
            "model_id": setting("LLM_JUDGE_MODEL"),
            "model_version": setting("LLM_JUDGE_MODEL_VERSION"),
        }
        missing = [name for name, value in values.items() if not value.strip()]
        if missing:
            env_names = {
                "gateway_url": "LLM_GATEWAY_URL",
                "model_id": "LLM_JUDGE_MODEL",
                "model_version": "LLM_JUDGE_MODEL_VERSION",
            }
            raise JudgeConfigurationError(
                "live judge requires " + ", ".join(env_names[name] for name in missing)
            )
        if any(
            values[name].lower().endswith("latest")
            for name in ("model_id", "model_version")
        ):
            raise JudgeConfigurationError(
                "judge model and version must be pinned, not 'latest'"
            )
        token = setting("LLM_GATEWAY_TOKEN") or None
        return cls(
            **values,
            prompt_version=prompt_version,
            token=token,
        )


def score_schema(criterion: str) -> dict[str, Any]:
    """JSON Schema sent to the Gateway as a strict structured-output contract."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["criterion", "score", "explanation"],
        "properties": {
            "criterion": {"type": "string", "enum": [criterion]},
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "explanation": {"type": "string", "minLength": 1},
        },
    }

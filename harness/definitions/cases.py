"""Load and validate deployed-skill evaluation cases."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from harness.agent.models import AnswerEvaluationSpec

REQUIRED_KEYS = {"title", "why", "query", "domain", "persona"}
ALLOWED_KEYS = REQUIRED_KEYS | {"expect", "expect_tool_calls", "answer_evaluation"}
ALLOWED_EXPECT_KEYS = {"required_entities", "must_not_return"}
CASE_ID_PATTERN = re.compile(r"case-([0-9]{3})-[a-z0-9]+(?:-[a-z0-9]+)*")
ENTITY_IDENTITY_PATTERN = re.compile(r"[A-Za-z]+/\S+")


class CaseSpecError(ValueError):
    pass


def _mapping(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise CaseSpecError(f"{where} must be a mapping")
    return value


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaseSpecError(f"{where} must be a non-empty string")
    return value


def _entity_identity(value: Any, where: str) -> str:
    value = _string(value, where)
    if not ENTITY_IDENTITY_PATTERN.fullmatch(value):
        raise CaseSpecError(f"{where} must look like Label/key; got {value!r}")
    return value


def _validate_entities(value: Any, where: str, *, required: bool) -> None:
    if not isinstance(value, list) or (required and not value):
        qualifier = "a non-empty" if required else "a"
        raise CaseSpecError(f"{where} must be {qualifier} list")
    for index, entity in enumerate(value):
        _entity_identity(entity, f"{where}[{index}]")
    if len(value) != len(set(value)):
        raise CaseSpecError(f"{where} must contain unique identities")


def _validate_tool_calls(value: Any, source: str) -> None:
    tool_calls = _mapping(value, f"{source}.expect_tool_calls")
    unknown = tool_calls.keys() - {"required", "forbidden_tools", "max_calls"}
    if unknown:
        raise CaseSpecError(
            f"{source}.expect_tool_calls has unknown key(s): {sorted(unknown)}"
        )

    required_calls = tool_calls.get("required")
    if not isinstance(required_calls, list) or not required_calls:
        raise CaseSpecError(
            f"{source}.expect_tool_calls.required must be a non-empty list"
        )
    for index, required_call in enumerate(required_calls):
        where = f"{source}.expect_tool_calls.required[{index}]"
        required_call = _mapping(required_call, where)
        if set(required_call) != {"tool", "args"}:
            raise CaseSpecError(f"{where} must contain exactly 'tool' and 'args'")
        _string(required_call["tool"], f"{where}.tool")
        _mapping(required_call["args"], f"{where}.args")

    forbidden_tools = tool_calls.get("forbidden_tools", [])
    if not isinstance(forbidden_tools, list) or not all(
        isinstance(tool, str) and tool.strip() for tool in forbidden_tools
    ):
        raise CaseSpecError(
            f"{source}.expect_tool_calls.forbidden_tools must be a list of tool names"
        )

    max_calls = tool_calls.get("max_calls")
    if max_calls is not None and (
        not isinstance(max_calls, int) or isinstance(max_calls, bool) or max_calls < 1
    ):
        raise CaseSpecError(
            f"{source}.expect_tool_calls.max_calls must be a positive integer"
        )


def validate_case(
    case: Any,
    source: str = "<case>",
    *,
    case_id: str | None = None,
) -> dict:
    """Validate one authored deployed-skill case."""
    case = _mapping(case, source)
    missing = REQUIRED_KEYS - case.keys()
    if missing:
        raise CaseSpecError(f"{source} is missing required key(s): {sorted(missing)}")
    unknown = case.keys() - ALLOWED_KEYS
    if unknown:
        raise CaseSpecError(f"{source} has unknown key(s): {sorted(unknown)}")

    if case_id is not None:
        case_id = _string(case_id, f"{source} filename")
        if not CASE_ID_PATTERN.fullmatch(case_id):
            raise CaseSpecError(
                f"{source} filename must look like case-001-ownership.yaml; "
                f"got {case_id!r}"
            )
    for key in REQUIRED_KEYS:
        _string(case[key], f"{source}.{key}")

    expect = _mapping(case.get("expect", {}), f"{source}.expect")
    unknown_expect = expect.keys() - ALLOWED_EXPECT_KEYS
    if unknown_expect:
        raise CaseSpecError(
            f"{source}.expect has unknown key(s): {sorted(unknown_expect)}"
        )
    if "required_entities" in expect:
        _validate_entities(
            expect["required_entities"],
            f"{source}.expect.required_entities",
            required=True,
        )
    if "must_not_return" in expect:
        _validate_entities(
            expect["must_not_return"],
            f"{source}.expect.must_not_return",
            required=False,
        )

    if "expect_tool_calls" not in case:
        raise CaseSpecError(f"{source} must declare expect_tool_calls")
    _validate_tool_calls(case["expect_tool_calls"], source)

    if "answer_evaluation" not in case:
        raise CaseSpecError(f"{source} must declare answer_evaluation")
    try:
        AnswerEvaluationSpec.model_validate(case["answer_evaluation"], strict=True)
    except ValidationError as exc:
        raise CaseSpecError(f"{source}.answer_evaluation is invalid: {exc}") from exc

    return {"id": case_id, **case} if case_id is not None else case


def get_answer_evaluation(case: dict) -> AnswerEvaluationSpec:
    return AnswerEvaluationSpec.model_validate(case["answer_evaluation"], strict=True)


def load_case(path: Path) -> dict:
    try:
        parsed = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise CaseSpecError(f"{path.name} is not valid YAML: {exc}") from exc
    return validate_case(parsed, path.name, case_id=path.stem)


def load_cases(directory: Path) -> list[dict]:
    cases = [
        load_case(path)
        for path in sorted(directory.glob("*.yaml"))
        if not path.name.startswith("_")
    ]
    if not cases:
        raise CaseSpecError(f"{directory} contains no evaluation cases")
    numbers = [
        int(CASE_ID_PATTERN.fullmatch(case["id"]).group(1))
        for case in cases
    ]
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        raise CaseSpecError(
            "case numbering must start at 001 and be contiguous; "
            f"got {numbers}"
        )
    return cases

"""Define, load, and validate dataset-driven evaluation cases.

Cases remain dictionaries so the runner does not gain a second object model, but
every dictionary is validated once at the boundary. Typos and incomplete relevance
definitions therefore fail before the target under test is invoked.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from harness.agent.models import AnswerEvaluationSpec

REQUIRED_KEYS = {"title", "why", "query", "domain"}
ALLOWED_KEYS = REQUIRED_KEYS | {
    "limit",
    "expect",
    "expect_tool_call",
    "probe_invalid_request",
    "answer_evaluation",
}
CASE_ID_PATTERN = re.compile(r"case-([0-9]{3})-[a-z0-9]+(?:-[a-z0-9]+)*")
ALLOWED_EXPECT_KEYS = {
    "relevant",
    "must_not_return",
    "expected_first_result",
}
# Entity identity: "Label/key", per skill.contracts.Entity.identity.
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


def validate_case(
    case: Any,
    source: str = "<case>",
    *,
    case_id: str | None = None,
) -> dict:
    """Validate authored case fields and optionally attach a filename-derived ID."""
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
                f"{source} filename must look like "
                f"case-001-retries-ranking.yaml; got {case_id!r}"
            )
    for key in ("title", "why", "query", "domain"):
        _string(case[key], f"{source}.{key}")

    if "limit" in case and (not isinstance(case["limit"], int) or case["limit"] <= 0):
        raise CaseSpecError(f"{source}.limit must be a positive integer")
    if "probe_invalid_request" in case:
        _mapping(case["probe_invalid_request"], f"{source}.probe_invalid_request")

    expect = _mapping(case.get("expect", {}), f"{source}.expect")
    unknown_expect = expect.keys() - ALLOWED_EXPECT_KEYS
    if unknown_expect:
        raise CaseSpecError(
            f"{source}.expect has unknown key(s): {sorted(unknown_expect)}"
        )

    relevant = expect.get("relevant")
    if relevant is not None:
        if not isinstance(relevant, list) or not relevant:
            raise CaseSpecError(f"{source}.expect.relevant must be a non-empty list")
        seen_entities: set[str] = set()
        for index, relevance_label in enumerate(relevant):
            where = f"{source}.expect.relevant[{index}]"
            relevance_label = _mapping(relevance_label, where)
            missing_label = {"entity", "grade"} - relevance_label.keys()
            if missing_label:
                raise CaseSpecError(
                    f"{where} is missing required key(s): {sorted(missing_label)}"
                )
            entity = _entity_identity(relevance_label["entity"], f"{where}.entity")
            if entity in seen_entities:
                raise CaseSpecError(f"{source} grades entity {entity!r} more than once")
            seen_entities.add(entity)
            if relevance_label["grade"] not in {0, 1, 2}:
                raise CaseSpecError(f"{where}.grade must be 0, 1, or 2")

    if "must_not_return" in expect:
        forbidden = expect["must_not_return"]
        if not isinstance(forbidden, list) or not all(isinstance(n, str) for n in forbidden):
            raise CaseSpecError(
                f"{source}.expect.must_not_return must be a list of entity identities"
            )
        for index, entity in enumerate(forbidden):
            _entity_identity(entity, f"{source}.expect.must_not_return[{index}]")
    if "expected_first_result" in expect:
        _entity_identity(
            expect["expected_first_result"],
            f"{source}.expect.expected_first_result",
        )
    if "expect_tool_call" in case:
        tool_call = _mapping(case["expect_tool_call"], f"{source}.expect_tool_call")
        _string(tool_call.get("tool"), f"{source}.expect_tool_call.tool")
        _mapping(tool_call.get("args"), f"{source}.expect_tool_call.args")

    if "answer_evaluation" in case:
        try:
            AnswerEvaluationSpec.model_validate(case["answer_evaluation"], strict=True)
        except ValidationError as exc:
            raise CaseSpecError(f"{source}.answer_evaluation is invalid: {exc}") from exc

    return {"id": case_id, **case} if case_id is not None else case


def get_answer_evaluation(case: dict) -> AnswerEvaluationSpec | None:
    """Return the optional answer-evaluation contract of a validated case."""
    value = case.get("answer_evaluation")
    if value is None:
        return None
    return AnswerEvaluationSpec.model_validate(value, strict=True)


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
    ids = [case["id"] for case in cases]
    numbers = sorted(
        int(match.group(1))
        for case_id in ids
        if (match := CASE_ID_PATTERN.fullmatch(case_id))
    )
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        raise CaseSpecError(
            "case numbering must start at 001 and be contiguous; "
            f"got {numbers}"
        )
    return cases

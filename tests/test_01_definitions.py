"""Malformed evaluation definitions fail before a target can run."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.definitions.cases import load_cases, validate_case

ROOT = Path(__file__).resolve().parents[1]


CASES = load_cases(ROOT / "cases")


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            case,
            id=f"{case['id']}:definition:case_valid",
            marks=pytest.mark.case_check(case["id"], "definition"),
        )
        for case in CASES
    ],
)
@pytest.mark.evaluation
def test_committed_case_is_valid(case):
    authored = {key: value for key, value in case.items() if key != "id"}
    assert validate_case(
        authored,
        f"{case['id']}.yaml",
        case_id=case["id"],
    ) == case

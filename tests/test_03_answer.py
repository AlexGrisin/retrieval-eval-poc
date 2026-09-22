"""End-to-end answer evaluation keeps exact checks ahead of semantic judging."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.agent.runner import applicable_answer_checks
from harness.definitions.cases import load_cases
from harness.validators import ANSWER_CHECKS

ROOT = Path(__file__).resolve().parents[1]


CASES = load_cases(ROOT / "cases")


def _answer_check_params():
    for case in CASES:
        for name in applicable_answer_checks(case):
            yield pytest.param(
                case["id"],
                name,
                id=f"{case['id']}:answer:{name.removeprefix('answer:')}",
                marks=[
                    getattr(pytest.mark, ANSWER_CHECKS[name]["status"]),
                    pytest.mark.case_check(case["id"], "answer"),
                ],
            )


@pytest.mark.parametrize(
    "case_id,check_name",
    list(_answer_check_params()),
)
@pytest.mark.evaluation
def test_agent_check_is_explicit_and_traceable(captured_runs, case_id, check_name):
    run = captured_runs[case_id]
    found = [check for check in run.checks if check.name == check_name]

    assert len(found) == 1
    assert found[0].status == "ok"
    assert found[0].traceability != "UNTRACEABLE"
    assert found[0].source
    assert run.answer_passed is True
    assert run.deterministic_passed is True

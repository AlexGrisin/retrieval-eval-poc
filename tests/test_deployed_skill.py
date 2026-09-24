"""End-to-end checks against the deployed ``okf-knowledge`` skill."""

from __future__ import annotations

import json

import allure
import pytest

from tests.support import load_cases

CASES = load_cases()


@pytest.mark.agent_target
@pytest.mark.evaluation
@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(
            case["id"],
            id=f"{case['id']}:answer:deployed_skill",
            marks=pytest.mark.case_check(case["id"], "answer"),
        )
        for case in CASES
    ],
)
def test_deployed_skill(agent_case_results, case_id, trial):
    outcome = agent_case_results[case_id, trial]
    allure.dynamic.parameter("trial", trial)
    allure.attach(
        json.dumps(
            [call.as_dict() for call in outcome.evidence.tool_calls],
            indent=2,
            default=str,
            sort_keys=True,
        ),
        name="actual tool trace",
        attachment_type=allure.attachment_type.JSON,
    )
    allure.attach(
        outcome.evidence.final_answer,
        name="actual final answer",
        attachment_type=allure.attachment_type.TEXT,
    )
    allure.attach(
        "\n".join(outcome.failures) or "no failures",
        name="deterministic evaluation",
        attachment_type=allure.attachment_type.TEXT,
    )

    diagnostic = (
        "\n".join(outcome.failures)
        + "\n\nObserved tools:\n"
        + json.dumps(
            [
                {
                    "tool": call.tool,
                    "args": call.args,
                    "is_error": call.is_error,
                }
                for call in outcome.evidence.tool_calls
            ],
            indent=2,
            default=str,
            sort_keys=True,
        )
        + "\n\nFinal answer:\n"
        + outcome.evidence.final_answer
    )
    assert outcome.passed, diagnostic

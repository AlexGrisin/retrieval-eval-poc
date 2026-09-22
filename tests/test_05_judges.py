"""Live LLM-judge scoring is reporting-only and opt-in via --judge."""

from __future__ import annotations

import json
from pathlib import Path

import allure
import pytest

from harness.definitions.cases import get_answer_evaluation, load_cases
from harness.judges.gateway import OpenAIResponsesGateway
from harness.judges.models import JudgeConfig
from harness.judges.prompt import PROMPT_VERSION
from harness.judges.runner import DEFAULT_CACHE, run_agent_judges

ROOT = Path(__file__).resolve().parents[1]
CASES = load_cases(ROOT / "cases")
CASES_BY_ID = {case["id"]: case for case in CASES}


@pytest.fixture(scope="session")
def live_judge_outcomes(request, captured_runs):
    """Run all case-declared rubrics once and share their outcomes across reports."""
    if not request.config.getoption("--judge"):
        pytest.skip("requires --judge and configured LLM Gateway")
    config = JudgeConfig.from_env(PROMPT_VERSION)
    gateway = OpenAIResponsesGateway(config)
    cache: dict[str, list] = {}

    def outcomes_for(case_id: str):
        if case_id not in cache:
            cache[case_id] = run_agent_judges(
                run=captured_runs[case_id],
                gateway=gateway,
                config=config,
                cache_dir=DEFAULT_CACHE,
            )
        return cache[case_id]

    return outcomes_for


@pytest.mark.judge
@pytest.mark.evaluation
@pytest.mark.parametrize(
    ("case_id", "rubric_name"),
    [
        pytest.param(
            case["id"],
            rubric_name,
            id=f"{case['id']}:judge:{rubric_name}",
            marks=pytest.mark.case_check(case["id"], "judge"),
        )
        for case in CASES
        if (evaluation := get_answer_evaluation(case)) is not None
        for rubric_name in evaluation.rubrics
    ],
)
def test_live_llm_judge_is_reporting_only(live_judge_outcomes, case_id, rubric_name):
    outcomes = live_judge_outcomes(case_id)
    declared = CASES_BY_ID[case_id]
    evaluation = get_answer_evaluation(declared)
    assert evaluation is not None
    assert [outcome.criterion for outcome in outcomes] == evaluation.rubrics
    outcome = next(item for item in outcomes if item.criterion == rubric_name)
    assert outcome.status == "scored"
    record = outcome.record
    assert record is not None
    allure.attach(
        json.dumps(record.model_dump(), indent=2, default=str, sort_keys=True),
        name="judge verdict",
        attachment_type=allure.attachment_type.JSON,
    )
    print(
        f"{record.case_id} {record.criterion}={record.score}: "
        f"{record.explanation}"
    )

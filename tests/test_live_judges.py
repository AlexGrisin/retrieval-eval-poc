"""Optional semantic judges over the captured deployed-skill answers."""

from __future__ import annotations

import json

import allure
import pytest

from harness.definitions.cases import get_answer_evaluation
from harness.judges.gateway import OpenAIResponsesGateway
from harness.judges.loader import load_rubrics
from harness.judges.models import JudgeConfig
from harness.judges.prompt import PROMPT_VERSION
from harness.judges.runner import (
    DEFAULT_CACHE,
    run_agent_judges,
    summarize_judge_outcome,
)
from tests.support import load_cases

CASES = load_cases()


@pytest.fixture(scope="session")
def agent_live_judge_outcomes(agent_case_results, run_artifacts, pytestconfig):
    config = JudgeConfig.from_env(PROMPT_VERSION)
    gateway = OpenAIResponsesGateway(config)
    rubrics = load_rubrics()
    run_artifacts.set_metadata(
        "judge",
        {
            "enabled": True,
            "gateway_url": config.gateway_url,
            "model_id": config.model_id,
            "model_version": config.model_version,
            "prompt_version": config.prompt_version,
            "temperature": config.temperature,
            "gate_enabled": pytestconfig.getoption("--judge-gate"),
        },
    )
    cache: dict[tuple[str, int], list] = {}

    def outcomes_for(case_id: str, trial: int):
        key = (case_id, trial)
        if key not in cache:
            cache[key] = run_agent_judges(
                run=agent_case_results[key].agent_run,
                gateway=gateway,
                config=config,
                cache_dir=DEFAULT_CACHE,
                judge_failed_runs=True,
            )
            run_artifacts.record_judges(
                case_id,
                trial,
                [
                    summarize_judge_outcome(outcome, rubrics[outcome.criterion])
                    for outcome in cache[key]
                ],
            )
        return cache[key]

    return outcomes_for


@pytest.mark.agent_target
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
        for rubric_name in get_answer_evaluation(case).rubrics
    ],
)
def test_deployed_skill_live_judge(
    agent_live_judge_outcomes, case_id, rubric_name, trial, request
):
    outcomes = agent_live_judge_outcomes(case_id, trial)
    outcome = next(item for item in outcomes if item.criterion == rubric_name)
    rubric = load_rubrics()[rubric_name]
    result = summarize_judge_outcome(outcome, rubric)
    allure.attach(
        json.dumps(result, indent=2, sort_keys=True),
        name="judge result and threshold",
        attachment_type=allure.attachment_type.JSON,
    )
    assert outcome.status == "scored", outcome.reason
    if request.config.getoption("--judge-gate"):
        assert result["above_threshold"], (
            f"judge score {result['score']} is below {rubric_name} threshold "
            f"{result['threshold']}: {result['explanation']}"
        )

"""Optional semantic judges over the captured deployed-skill answers."""

from __future__ import annotations

import pytest

from harness.definitions.cases import get_answer_evaluation
from harness.judges.gateway import OpenAIResponsesGateway
from harness.judges.models import JudgeConfig
from harness.judges.prompt import PROMPT_VERSION
from harness.judges.runner import DEFAULT_CACHE, run_agent_judges
from tests.support import load_cases

CASES = load_cases()


@pytest.fixture(scope="session")
def agent_live_judge_outcomes(agent_case_results, run_artifacts):
    config = JudgeConfig.from_env(PROMPT_VERSION)
    gateway = OpenAIResponsesGateway(config)
    run_artifacts.set_metadata(
        "judge",
        {
            "enabled": True,
            "gateway_url": config.gateway_url,
            "model_id": config.model_id,
            "model_version": config.model_version,
            "prompt_version": config.prompt_version,
            "temperature": config.temperature,
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
    agent_live_judge_outcomes, case_id, rubric_name, trial
):
    outcomes = agent_live_judge_outcomes(case_id, trial)
    outcome = next(item for item in outcomes if item.criterion == rubric_name)
    assert outcome.status == "scored"

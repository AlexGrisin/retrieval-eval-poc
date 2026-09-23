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
def agent_live_judge_outcomes(agent_case_results):
    config = JudgeConfig.from_env(PROMPT_VERSION)
    gateway = OpenAIResponsesGateway(config)
    cache: dict[str, list] = {}

    def outcomes_for(case_id: str):
        if case_id not in cache:
            cache[case_id] = run_agent_judges(
                run=agent_case_results[case_id].agent_run,
                gateway=gateway,
                config=config,
                cache_dir=DEFAULT_CACHE,
            )
        return cache[case_id]

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
    agent_live_judge_outcomes, case_id, rubric_name
):
    outcomes = agent_live_judge_outcomes(case_id)
    outcome = next(item for item in outcomes if item.criterion == rubric_name)
    assert outcome.status == "scored"

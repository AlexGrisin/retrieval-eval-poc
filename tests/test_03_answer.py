"""End-to-end answer evaluation keeps exact checks ahead of semantic judging."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from harness.agent.runner import applicable_answer_checks, evaluate_agent_response
from harness.definitions.agent_responses import load_agent_response
from harness.definitions.cases import load_cases, validate_case
from harness.judges.gateway import GatewayResponse
from harness.judges.models import JudgeConfig
from harness.judges.prompt import PROMPT_VERSION
from harness.judges.runner import run_agent_judges
from harness.validators import ANSWER_CHECKS
from tests.support import framework_id

ROOT = Path(__file__).resolve().parents[1]


def _judge_config() -> JudgeConfig:
    return JudgeConfig(
        gateway_url="https://gateway.example.test/v1",
        model_id="judge-deployment",
        model_version="2026-08-01",
        prompt_version=PROMPT_VERSION,
    )


class CriterionGateway:
    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def evaluate(self, prompt: str, schema: dict) -> GatewayResponse:
        self.calls += 1
        self.prompts.append(prompt)
        criterion = schema["properties"]["criterion"]["enum"][0]
        return GatewayResponse(
            result={
                "criterion": criterion,
                "score": 1.0,
                "explanation": f"The captured answer satisfies {criterion}.",
            },
            actual_model="judge-deployment-2026-08-01",
        )


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


def _response_fixture(name: str) -> dict:
    path = ROOT / "fixtures" / "agent_responses" / f"{name}.yaml"
    return load_agent_response(path).model_dump()


def _evaluate(response: dict, retrieval_result: dict, case: dict):
    return evaluate_agent_response(
        case=case,
        retrieval_result=retrieval_result,
        response=response,
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


@framework_id("synthetic:answer:unretrieved_citation_rejected")
def test_unretrieved_citation_fails_deterministically(
    synthetic_case, synthetic_retrieval_result
):
    response = _response_fixture("case-001-retries-ranking")
    response["citations"].append({"note_id": "n-9999", "version": 1})

    run = _evaluate(response, synthetic_retrieval_result, synthetic_case)
    failed = {check.name: check.detail for check in run.checks if check.status == "fail"}

    assert run.deterministic_passed is False
    assert failed == {
        "answer:citations_were_retrieved": (
            "answer cites note versions that were not retrieved: ['n-9999@1']"
        )
    }


@framework_id("synthetic:answer:missing_required_citation_rejected")
def test_missing_required_citation_fails_deterministically(
    synthetic_case, synthetic_retrieval_result
):
    response = _response_fixture("case-001-retries-ranking")
    response["citations"] = response["citations"][:-1]

    run = _evaluate(response, synthetic_retrieval_result, synthetic_case)
    failed = {check.name: check.detail for check in run.checks if check.status == "fail"}

    assert failed == {
        "answer:required_citations": "answer is missing required citations: ['n-0003@2']"
    }


@framework_id("synthetic:answer:forbidden_citation_rejected")
def test_forbidden_citation_fails_even_when_it_was_not_retrieved(
    synthetic_case, synthetic_retrieval_result
):
    response = _response_fixture("case-001-retries-ranking")
    response["citations"].append({"note_id": "n-0004", "version": 1})

    run = _evaluate(response, synthetic_retrieval_result, synthetic_case)
    failed = {check.name for check in run.checks if check.status == "fail"}

    assert failed == {
        "answer:citations_were_retrieved",
        "answer:must_not_cite",
    }


@framework_id("synthetic:answer:wrong_status_rejected")
def test_wrong_structured_answer_status_fails_without_an_llm(
    synthetic_case, synthetic_retrieval_result
):
    response = _response_fixture("case-001-retries-ranking")
    response["status"] = "insufficient_context"

    run = _evaluate(response, synthetic_retrieval_result, synthetic_case)
    failed = {check.name: check.detail for check in run.checks if check.status == "fail"}

    assert failed == {
        "answer:expected_status": (
            "unexpected answer status: expected answered, got insufficient_context"
        )
    }


@framework_id("synthetic:answer:malformed_response_stops_dependent_checks")
def test_malformed_agent_response_skips_dependent_checks(
    synthetic_case, synthetic_retrieval_result
):
    response = _response_fixture("case-001-retries-ranking")
    response["unexpected"] = True

    run = _evaluate(response, synthetic_retrieval_result, synthetic_case)

    assert run.response is None
    assert run.deterministic_passed is False
    assert run.checks[0].name == "answer:response_contract_valid"
    assert run.checks[0].status == "fail"
    assert all(check.status == "skip" for check in run.checks[1:])


@framework_id("synthetic:answer:blank_answer_rejected")
def test_blank_answer_fails_the_response_contract(
    synthetic_case, synthetic_retrieval_result
):
    response = _response_fixture("case-001-retries-ranking")
    response["answer"] = "   "

    run = _evaluate(response, synthetic_retrieval_result, synthetic_case)

    assert run.response is None
    assert run.deterministic_passed is False
    assert run.checks[0].name == "answer:response_contract_valid"
    assert run.checks[0].status == "fail"
    assert "must not be blank" in run.checks[0].detail
    assert all(check.status == "skip" for check in run.checks[1:])


@framework_id("synthetic:answer:failed_prerequisites_stop_judge")
def test_judge_is_not_called_when_deterministic_prerequisites_fail(
    tmp_path, synthetic_case, synthetic_retrieval_result
):
    response = _response_fixture("case-001-retries-ranking")
    response["citations"].append({"note_id": "n-9999", "version": 1})
    run = _evaluate(response, synthetic_retrieval_result, synthetic_case)
    gateway = CriterionGateway()

    outcomes = run_agent_judges(
        run=run,
        gateway=gateway,
        config=_judge_config(),
        cache_dir=tmp_path / "judge-cache",
    )

    assert gateway.calls == 0
    assert {outcome.status for outcome in outcomes} == {"not_run"}
    assert all(
        "answer:citations_were_retrieved" in outcome.reason
        for outcome in outcomes
    )


@framework_id("synthetic:answer:diagnostic_judge_override")
def test_failed_run_can_be_judged_only_with_diagnostic_override(
    tmp_path, synthetic_case, synthetic_retrieval_result
):
    response = _response_fixture("case-001-retries-ranking")
    response["status"] = "insufficient_context"
    run = _evaluate(response, synthetic_retrieval_result, synthetic_case)
    gateway = CriterionGateway()

    outcomes = run_agent_judges(
        run=run,
        gateway=gateway,
        config=_judge_config(),
        cache_dir=tmp_path / "judge-cache",
        judge_failed_runs=True,
    )

    assert gateway.calls == 3
    assert [(outcome.criterion, outcome.status) for outcome in outcomes] == [
        ("faithfulness", "scored"),
        ("relevancy", "scored"),
        ("answer_correctness", "scored"),
    ]


@framework_id("synthetic:answer:judge_reuses_captured_run")
def test_valid_captured_run_is_judged_without_rerunning_retrieval(
    tmp_path, synthetic_agent_run
):
    run = synthetic_agent_run
    gateway = CriterionGateway()

    outcomes = run_agent_judges(
        run=run,
        gateway=gateway,
        config=_judge_config(),
        cache_dir=tmp_path / "judge-cache",
    )

    assert gateway.calls == 3
    assert {outcome.status for outcome in outcomes} == {"scored"}
    assert all(outcome.record and outcome.record.score == 1.0 for outcome in outcomes)
    assert all(run.question in prompt for prompt in gateway.prompts)
    assert all('"retrieved_context"' in prompt for prompt in gateway.prompts)
    assert all("n-0001@3" in prompt for prompt in gateway.prompts)


@framework_id("synthetic:answer:case_declared_rubrics_authoritative")
def test_case_declared_rubrics_are_authoritative(
    tmp_path, synthetic_case, synthetic_retrieval_result
):
    case = deepcopy(synthetic_case)
    case["answer_evaluation"] = {
        "expect": {"status": "insufficient_context"},
        "rubrics": ["relevancy"],
    }
    case_id = case.pop("id")
    case = validate_case(case, f"{case_id}.yaml", case_id=case_id)
    run = evaluate_agent_response(
        case=case,
        retrieval_result=synthetic_retrieval_result,
        response=_response_fixture("insufficient-context"),
    )
    gateway = CriterionGateway()

    outcomes = run_agent_judges(
        run=run,
        gateway=gateway,
        config=_judge_config(),
        cache_dir=tmp_path / "judge-cache",
    )

    assert gateway.calls == 1
    assert [(outcome.criterion, outcome.status) for outcome in outcomes] == [
        ("relevancy", "scored"),
    ]

"""Malformed evaluation definitions fail before a target can run."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.definitions.cases import (
    CaseSpecError,
    get_answer_evaluation,
    load_cases,
    validate_case,
)
from harness.definitions.agent_responses import load_agent_responses
from harness.definitions.rubrics import RubricSpecError, validate_rubric_spec
from harness.execution import CaseExecutions
from harness.judges.loader import load_rubrics
from harness.validators import CHECKS
from tests.support import framework_id

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


@framework_id("suite:definition:case_inventory_complete")
def test_case_inventory_is_complete():
    assert {case["id"] for case in CASES} == {
        "case-001-rounding-fix-ranking",
        "case-002-superseded-knowledge",
        "case-003-domain-isolation",
        "case-004-malformed-argument-rejected",
        "case-005-response-contract",
        "case-006-blank-query-rejected",
    }


@framework_id("synthetic:definition:derived_case_metadata_rejected")
def test_filename_derived_metadata_is_not_authored():
    case = {
        "id": "case-999-redundant-metadata",
        "kind": "metric",
        "title": "Redundant metadata",
        "why": "The filename and declared expectations already provide it.",
        "query": "question",
        "domain": "paastry",
    }

    with pytest.raises(CaseSpecError, match="unknown key.*id.*kind"):
        validate_case(case)


@framework_id("synthetic:definition:incomplete_relevance_label_rejected")
def test_incomplete_relevance_label_is_rejected():
    case = {
        "title": "Incomplete relevance label",
        "why": "A grade-less relevance label must not silently count as ungraded.",
        "query": "question",
        "domain": "paastry",
        "expect": {"relevant": [{"entity": "Story/PAAS-201"}]},
    }

    with pytest.raises(CaseSpecError, match="missing required key.*grade"):
        validate_case(case)


@framework_id("synthetic:definition:malformed_entity_identity_rejected")
def test_malformed_entity_identity_is_rejected():
    case = {
        "title": "Malformed entity identity",
        "why": "An identity without Label/key shape must fail before execution.",
        "query": "question",
        "domain": "paastry",
        "expect": {"relevant": [{"entity": "PAAS-201", "grade": 2}]},
    }

    with pytest.raises(CaseSpecError, match="must look like Label/key"):
        validate_case(case)


@framework_id("synthetic:definition:unknown_expectation_rejected")
def test_unknown_expectation_is_rejected():
    case = {
        "title": "Unknown expectation key",
        "why": "A typo must not silently reduce coverage.",
        "query": "question",
        "domain": "paastry",
        "expect": {"every_result_has_note_reference": True},
    }

    with pytest.raises(CaseSpecError, match="unknown key"):
        validate_case(case)


@framework_id("suite:definition:committed_rubrics_valid")
def test_committed_rubrics_are_valid():
    assert set(load_rubrics()) == {"answer_correctness", "faithfulness", "relevancy"}


@framework_id("suite:definition:selected_rubrics_known")
def test_answer_evaluation_selects_known_rubrics():
    rubric_ids = set(load_rubrics())
    evaluations = {
        case["id"]: evaluation
        for case in CASES
        if (evaluation := get_answer_evaluation(case)) is not None
    }

    assert evaluations, "at least one case must exercise generated-answer evaluation"
    assert all(set(evaluation.rubrics) <= rubric_ids for evaluation in evaluations.values())


@framework_id("suite:definition:agent_response_fixtures_valid")
def test_committed_agent_response_fixtures_are_valid():
    responses = load_agent_responses(ROOT / "fixtures" / "agent_responses")
    answer_case_ids = {
        case["id"] for case in CASES if get_answer_evaluation(case) is not None
    }

    assert answer_case_ids <= set(responses)
    assert set(responses) - answer_case_ids == {"insufficient-context"}


@framework_id("synthetic:definition:answer_correctness_requires_reference")
def test_answer_correctness_requires_a_reference_answer():
    case = {
        "title": "Missing reference answer",
        "why": "Answer correctness needs an explicit comparison target.",
        "query": "question",
        "domain": "paastry",
        "answer_evaluation": {"rubrics": ["answer_correctness"]},
    }

    with pytest.raises(CaseSpecError, match="requires reference_answer"):
        validate_case(case)


@framework_id("synthetic:definition:rubric_threshold_bounded")
def test_rubric_threshold_is_bounded():
    path = Path("faithfulness.yaml")
    spec = {
        "name": "faithfulness",
        "display_name": "Faithfulness",
        "type": "geval",
        "description": "description",
        "criteria": "criteria",
        "threshold": 1.5,
    }

    with pytest.raises(RubricSpecError, match="between 0 and 1"):
        validate_rubric_spec(path, spec)


@framework_id("suite:definition:every_check_traceable")
def test_every_check_is_traceable():
    missing = [
        name
        for name, metadata in CHECKS.items()
        if metadata["status"] == "UNTRACEABLE"
    ]

    assert not missing, f"checks missing traceability: {missing}"


@framework_id("synthetic:execution:case_is_lazy_and_cached")
def test_case_execution_is_lazy_and_cached(tmp_path):
    calls = []

    def execute(case, corpus, transport):
        calls.append((case["id"], corpus, transport))
        return {"id": case["id"]}

    executions = CaseExecutions(
        [{"id": "case-a"}, {"id": "case-b"}],
        tmp_path / "corpus.yaml",
        "mcp",
        tmp_path / "responses",
        case_runner=execute,
    )

    assert executions.executed_ids == ()
    assert executions["case-a"]["retrieval_result"] == {"id": "case-a"}
    assert executions["case-a"]["retrieval_result"] == {"id": "case-a"}
    assert executions.executed_ids == ("case-a",)
    assert calls == [("case-a", tmp_path / "corpus.yaml", "mcp")]

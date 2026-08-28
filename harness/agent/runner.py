"""Evaluate one captured agent response without rerunning retrieval."""

from __future__ import annotations

from typing import Any

from harness.agent.models import (
    AgentCheckResult,
    AgentRun,
)
from harness.definitions.cases import get_answer_evaluation
from harness.validators.answer import (
    check_citations_were_retrieved,
    check_expected_answer_status,
    check_must_not_cite,
    check_required_citations,
    validate_agent_response_contract,
)
from harness.validators.registry import describe


def applicable_answer_checks(case: dict) -> tuple[str, ...]:
    """Return deterministic answer checks in their execution/reporting order."""
    evaluation = get_answer_evaluation(case)
    if evaluation is None:
        return ()
    names = [
        "answer:response_contract_valid",
        "answer:citations_were_retrieved",
    ]
    if evaluation.expect.status is not None:
        names.append("answer:expected_status")
    if evaluation.expect.required_citations:
        names.append("answer:required_citations")
    if evaluation.expect.must_not_cite:
        names.append("answer:must_not_cite")
    return tuple(names)


def evaluate_agent_response(
    *,
    case: dict,
    retrieval_result: dict,
    response: Any,
) -> AgentRun:
    """Build the single execution artifact consumed by checks, metrics, and judges.

    The caller supplies the response and the retrieval trace captured from the same
    agent execution. This function never reruns retrieval.
    """
    evaluation = get_answer_evaluation(case)
    if evaluation is None:
        raise ValueError(f"{case['id']} does not declare answer_evaluation")
    if retrieval_result.get("id") != case["id"]:
        raise ValueError(
            f"captured retrieval result is for {retrieval_result.get('id')!r}, "
            f"expected {case['id']!r}"
        )

    checks: list[AgentCheckResult] = []

    def record(name: str, detail: str | None) -> None:
        meta = describe(name)
        checks.append(
            AgentCheckResult(
                name=name,
                status="ok" if detail is None else "fail",
                detail=detail or "",
                traceability=meta["status"],
                source=meta["source"],
            )
        )

    def skip(name: str, reason: str) -> None:
        meta = describe(name)
        checks.append(
            AgentCheckResult(
                name=name,
                status="skip",
                detail=reason,
                traceability=meta["status"],
                source=meta["source"],
            )
        )

    parsed, contract_detail = validate_agent_response_contract(response)
    record("answer:response_contract_valid", contract_detail)

    dependent_checks = applicable_answer_checks(case)[1:]

    if parsed is None:
        for name in dependent_checks:
            skip(name, "requires a valid agent response")
    else:
        record(
            "answer:citations_were_retrieved",
            check_citations_were_retrieved(parsed, retrieval_result),
        )
        if evaluation.expect.status is not None:
            record(
                "answer:expected_status",
                check_expected_answer_status(parsed, evaluation.expect.status),
            )
        if evaluation.expect.required_citations:
            record(
                "answer:required_citations",
                check_required_citations(parsed, evaluation.expect.required_citations),
            )
        if evaluation.expect.must_not_cite:
            record(
                "answer:must_not_cite",
                check_must_not_cite(parsed, evaluation.expect.must_not_cite),
            )

    answer_passed = all(check.status != "fail" for check in checks)
    retrieval_passed = bool(retrieval_result.get("passed"))
    return AgentRun(
        case_id=case["id"],
        question=case["query"],
        retrieved_context=retrieval_result.get("trace", {}).get("rendered", ""),
        response=parsed,
        retrieval_result=retrieval_result,
        checks=checks,
        answer_passed=answer_passed,
        deterministic_passed=retrieval_passed and answer_passed,
        rubrics=evaluation.rubrics,
        reference_answer=evaluation.reference_answer,
    )

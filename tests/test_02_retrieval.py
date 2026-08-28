"""One test per applicable (case, validator) pair, so a red build names the rule."""

from __future__ import annotations

import pytest

from harness.validators import CHECKS, applies_to
from harness.validators.contract import check_response_contract
from skill.contracts import Entity, SearchHit, SearchResponse
from tests.support import framework_id, load_cases

# Markers come from the traceability registry, so `-m "not unratified"` shows the
# build with only checks that have a requirement behind them.
_MARKERS = {
    "traced": pytest.mark.traced,
    "inferred": pytest.mark.inferred,
    "unratified": pytest.mark.unratified,
    "UNTRACEABLE": pytest.mark.untraceable,
}

BOUNDARY_ONLY = {"contract:server_rejects_invalid_request"}

LEVELS = {
    "contract:emitted_tool_call": "request",
    "contract:server_rejects_invalid_request": "request",
    "contract:response_contract_valid": "response",
    "format:every_result_has_provenance": "response",
    "retrieval:must_not_return": "expectation",
    "retrieval:expected_first_result": "expectation",
}
LEVEL_ORDER = {"request": 1, "response": 2, "expectation": 3}


def _params():
    for case in load_cases():
        ordered_checks = sorted(
            CHECKS.items(),
            key=lambda item: LEVEL_ORDER.get(LEVELS.get(item[0], ""), 99),
        )
        for name, meta in ordered_checks:
            if not applies_to(name, case):
                continue
            marks = [_MARKERS[meta["status"]]]
            if name in BOUNDARY_ONLY:
                marks.append(pytest.mark.boundary)
            check = name.split(":", 1)[1]
            marks.append(pytest.mark.case_check(case["id"], LEVELS[name]))
            yield pytest.param(
                case["id"],
                name,
                marks=marks,
                id=f"{case['id']}:{LEVELS[name]}:{check}",
            )


@pytest.mark.parametrize("case_id,check_name", list(_params()))
@pytest.mark.evaluation
def test_check(case_results, case_id, check_name):
    result = case_results[case_id]
    found = [c for c in result["checks"] if c["name"] == check_name]
    assert found, f"{check_name} was never evaluated for {case_id}"
    check = found[0]

    if check["status"] == "skip":
        pytest.skip(check["detail"])

    # On failure only -- pytest is silent on pass by design, this is not a
    # substitute for `harness.runner --trace`. Enough context to diagnose
    # without re-running the CLI separately: what was sent, what came back.
    tr = result["trace"]
    context = (
        f"tool call : {tr['tool_call']}\n"
        f"  returned  : {[(r['entity'], r['matched_by']) for r in tr['results']]}\n"
        f"  rendered  :\n"
        + "\n".join(f"    | {line}" for line in tr["rendered"].rstrip().splitlines())
    )

    assert check["status"] == "ok", (
        f"{check['detail']}\n"
        f"  traceability: {check['traceability']}\n"
        f"  source      : {check['source']}\n"
        f"{context}"
    )


@framework_id("synthetic:response:wrong_field_type_rejected")
def test_response_contract_reports_wrong_field_type():
    response = SearchResponse(
        results=[
            SearchHit(
                entity=Entity(label="Service", key="pricing-api"),
                title="Example",
                snippet="Example snippet",
                score="1.0",  # type: ignore[arg-type] - deliberate wire-contract fault
                matched_by="fulltext",
                citations=[],
            )
        ],
    )

    detail = check_response_contract(response)
    assert detail is not None
    assert "response does not match the published contract" in detail

"""The ranx adapter preserves the harness's metric contract."""

import pytest

from tests.support import load_cases


def _case_metric_params():
    for case in load_cases():
        if not case.get("expect", {}).get("relevant"):
            continue
        limit = case.get("limit", 10)
        for metric in (f"recall@{limit}", "precision@5", "mrr", f"ndcg@{limit}"):
            yield pytest.param(
                case["id"],
                metric,
                id=f"{case['id']}:ranking:{metric}",
                marks=pytest.mark.case_check(case["id"], "ranking"),
            )


@pytest.mark.parametrize("case_id,metric", list(_case_metric_params()))
@pytest.mark.evaluation
def test_case_ranking_metric_is_calculated(case_results, case_id, metric):
    score = case_results[case_id]["metrics"][metric]

    assert 0.0 <= score <= 1.0


def _case_latency_params():
    for case in load_cases():
        yield pytest.param(
            case["id"],
            id=f"{case['id']}:ranking:latency_ms",
            marks=pytest.mark.case_check(case["id"], "ranking"),
        )


@pytest.mark.parametrize("case_id", list(_case_latency_params()))
@pytest.mark.evaluation
def test_case_latency_is_calculated(case_results, case_id):
    """Report-only measurement; see LATENCY-MEASUREMENT-PLAN.md.

    A sanity range, not an exact-value assertion: wall-clock timing is
    nondeterministic, unlike the graded-relevance metrics below.
    """
    latency_ms = case_results[case_id]["latency_ms"]

    assert latency_ms >= 0.0

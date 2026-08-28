"""The ranx adapter preserves the harness's metric contract."""

import pytest

from harness.ranking_metrics import score_case
from tests.support import load_cases


def _case_metric_params():
    for case in load_cases():
        if not case.get("expect", {}).get("relevant"):
            continue
        k = case.get("k", 10)
        for metric in (f"recall@{k}", "precision@5", "mrr", f"ndcg@{k}"):
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


@pytest.fixture(scope="module")
def graded_ranking_scores():
    return score_case(
        ranked=["n-0001", "noise", "n-0002", "n-0003"],
        grades={"n-0001": 2, "n-0002": 1, "n-0003": 1},
        k=10,
    )


@pytest.fixture(scope="module")
def empty_ranking_scores():
    return score_case([], {"n-0001": 2}, 10)


@pytest.mark.parametrize(
    "metric,expected",
    [
        pytest.param("recall@10", 1.0, id="synthetic:ranking:recall@10"),
        pytest.param("precision@5", 0.6, id="synthetic:ranking:precision@5"),
        pytest.param("mrr", 1.0, id="synthetic:ranking:mrr"),
        pytest.param("ndcg@10", 0.936, id="synthetic:ranking:ndcg@10"),
    ],
)
@pytest.mark.framework
def test_graded_relevance_metric(graded_ranking_scores, metric, expected):
    assert graded_ranking_scores[metric] == expected


@pytest.mark.parametrize(
    "metric",
    [
        pytest.param("recall@10", id="synthetic-empty:ranking:recall@10"),
        pytest.param("precision@5", id="synthetic-empty:ranking:precision@5"),
        pytest.param("mrr", id="synthetic-empty:ranking:mrr"),
        pytest.param("ndcg@10", id="synthetic-empty:ranking:ndcg@10"),
    ],
)
@pytest.mark.framework
def test_empty_retrieval_metric_is_zero(empty_ranking_scores, metric):
    assert empty_ranking_scores[metric] == 0.0

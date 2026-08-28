"""Framework tests for versioned manifests and baseline compatibility."""

from __future__ import annotations

from copy import deepcopy

import pytest

from harness.baselines import (
    BaselineFormatError,
    build_run_manifest,
    compare_records,
    validate_record,
)
from tests.support import ROOT, framework_id


def _record(value: float = 1.0) -> dict:
    return {
        "manifest": {
            "schema_version": 1,
            "compatibility": {
                "common": {
                    "corpus_hash": "corpus-a",
                    "case_set_hash": "cases-a",
                    "transport": "mcp",
                },
                "profiles": {
                    "ranking": {
                        "profile_version": "ranking-v1",
                        "metrics": ["ndcg@10"],
                        "regression_policy": "absolute-drop-v1",
                        "absolute_drop_tolerance": 0.02,
                    }
                },
            },
            "target": {
                "knowledge_server_version": "server-1",
                "retrieval_skill_version": "skill-1",
            },
            "comparison": {"change_under_test": []},
            "run": {"run_at": "2026-08-28T10:00:00Z"},
        },
        "cases": [{"id": "case-001", "metrics": {"ndcg@10": value}}],
    }


@framework_id("suite:baseline:identical_runs_are_compatible")
def test_identical_runs_are_compatible_when_run_metadata_differs():
    baseline = _record()
    current = deepcopy(baseline)
    current["manifest"]["run"]["run_at"] = "2026-08-29T10:00:00Z"

    comparison = compare_records(baseline, current)

    assert comparison.compatible
    assert comparison.regressions == []


@framework_id("suite:baseline:controlled_input_change_is_rejected")
def test_controlled_input_change_is_rejected():
    baseline = _record()
    current = deepcopy(baseline)
    current["manifest"]["compatibility"]["common"]["corpus_hash"] = "corpus-b"

    comparison = compare_records(baseline, current)

    assert not comparison.compatible
    assert [difference.path for difference in comparison.differences] == [
        "compatibility.common.corpus_hash"
    ]


@framework_id("suite:baseline:undeclared_target_change_is_rejected")
def test_undeclared_target_change_is_rejected():
    baseline = _record()
    current = deepcopy(baseline)
    current["manifest"]["target"]["knowledge_server_version"] = "server-2"

    comparison = compare_records(baseline, current)

    assert not comparison.compatible
    assert comparison.differences[0].path == "target.knowledge_server_version"


@framework_id("suite:baseline:declared_target_change_is_comparable")
def test_declared_target_change_is_comparable():
    baseline = _record()
    current = deepcopy(baseline)
    current["manifest"]["target"]["knowledge_server_version"] = "server-2"
    current["manifest"]["comparison"]["change_under_test"] = [
        "target.knowledge_server_version"
    ]

    comparison = compare_records(baseline, current)

    assert comparison.compatible


@framework_id("suite:baseline:changed_case_inventory_is_rejected")
def test_changed_case_inventory_is_rejected():
    baseline = _record()
    current = deepcopy(baseline)
    current["cases"].append({"id": "case-002", "metrics": {}})

    comparison = compare_records(baseline, current)

    assert not comparison.compatible
    assert comparison.differences[0].path == "cases.ids"


@framework_id("suite:baseline:changed_metric_inventory_is_rejected")
def test_changed_metric_inventory_is_rejected():
    baseline = _record()
    current = deepcopy(baseline)
    current["cases"][0]["metrics"]["mrr"] = 1.0

    comparison = compare_records(baseline, current)

    assert not comparison.compatible
    assert comparison.differences[0].path == "cases.case-001.metrics"


@pytest.mark.parametrize(
    ("current_value", "expected_regressions"),
    [(0.98, 0), (0.9799, 1)],
    ids=[
        "suite:baseline:tolerance_boundary_is_allowed",
        "suite:baseline:drop_beyond_tolerance_regresses",
    ],
)
@pytest.mark.framework
def test_regression_policy_boundary(current_value, expected_regressions):
    comparison = compare_records(_record(), _record(current_value))

    assert comparison.compatible
    assert len(comparison.regressions) == expected_regressions


@framework_id("suite:baseline:unknown_manifest_version_is_rejected")
def test_unknown_manifest_version_is_rejected():
    record = _record()
    record["manifest"]["schema_version"] = 2

    with pytest.raises(BaselineFormatError, match="schema_version must be 1"):
        validate_record(record)


@framework_id("suite:baseline:change_under_test_is_target_only")
def test_change_under_test_can_only_name_target_fields():
    record = _record()
    record["manifest"]["comparison"]["change_under_test"] = [
        "compatibility.common.corpus_hash"
    ]

    with pytest.raises(BaselineFormatError, match="only target fields"):
        validate_record(record)


@framework_id("suite:baseline:unknown_target_change_is_rejected")
def test_change_under_test_must_name_a_recorded_target_field():
    record = _record()
    record["manifest"]["comparison"]["change_under_test"] = [
        "target.unrecorded_version"
    ]

    with pytest.raises(BaselineFormatError, match="unknown target field"):
        validate_record(record)


@framework_id("suite:baseline:system_metadata_cannot_override_case_identity")
def test_system_metadata_cannot_override_evaluation_managed_identity():
    with pytest.raises(BaselineFormatError, match="cannot override.*case_set_hash"):
        build_run_manifest(
            root=ROOT,
            corpus=ROOT / "fixtures" / "corpus.yaml",
            cases=ROOT / "cases",
            corpus_version="fixture-test",
            transport="inprocess",
            executions=1,
            mode="mock",
            system_metadata={"compatibility": {"case_set_hash": "forged"}},
        )

"""Versioned run manifests and strict baseline compatibility rules."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable


MANIFEST_VERSION = 1
RANKING_PROFILE_VERSION = "ranking-v1"
REGRESSION_POLICY_VERSION = "absolute-drop-v1"
DEFAULT_TOLERANCE = 0.02
HASHED_SUFFIXES = {".json", ".lock", ".py", ".toml", ".yaml", ".yml"}
INSTRUMENT_MANAGED_FIELDS = {
    "evaluation_profile",
    "target_interface",
    "mode",
    "transport",
    "executions",
    "corpus_version",
    "corpus_hash",
    "case_set_hash",
    "contracts_hash",
    "orchestration_hash",
    "dependency_lock_hash",
    "python",
    "mcp_sdk",
}


class BaselineFormatError(ValueError):
    """A saved or current run does not satisfy the baseline record contract."""


@dataclass(frozen=True)
class CompatibilityDifference:
    path: str
    baseline: Any
    current: Any


@dataclass(frozen=True)
class MetricDelta:
    case_id: str
    metric: str
    baseline: float
    current: float
    delta: float
    regression: bool


@dataclass(frozen=True)
class BaselineComparison:
    differences: list[CompatibilityDifference] = field(default_factory=list)
    metric_deltas: list[MetricDelta] = field(default_factory=list)

    @property
    def compatible(self) -> bool:
        return not self.differences

    @property
    def regressions(self) -> list[MetricDelta]:
        return [delta for delta in self.metric_deltas if delta.regression]


def _files(paths: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if path.is_file():
            files.add(path)
            continue
        if path.is_dir():
            for candidate in path.rglob("*"):
                if (
                    candidate.is_file()
                    and candidate.suffix in HASHED_SUFFIXES
                    and "__pycache__" not in candidate.parts
                    and ".pytest_cache" not in candidate.parts
                ):
                    files.add(candidate)
    return sorted(files)


def hash_paths(root: Path, *paths: Path) -> str:
    """Hash both relative path and content so renames are version changes."""
    digest = hashlib.sha256()
    selected = _files(paths)
    if not selected:
        raise BaselineFormatError("cannot fingerprint an empty path set")
    for path in selected:
        try:
            identity = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            identity = path.resolve().as_posix()
        digest.update(identity.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "absent"


def _merge(base: dict[str, Any], override: Any, name: str) -> dict[str, Any]:
    if override is None:
        return base
    if not isinstance(override, dict):
        raise BaselineFormatError(f"system metadata {name!r} must be an object")
    return {**base, **override}


def build_run_manifest(
    *,
    root: Path,
    corpus: Path,
    cases: Path,
    corpus_version: str,
    transport: str,
    executions: int,
    mode: str,
    system_metadata: dict[str, Any] | None = None,
    change_under_test: Iterable[str] = (),
) -> dict[str, Any]:
    """Build a production-shaped manifest for the currently selected target.

    ``system_metadata`` is the seam used by a real Knowledge Server integration.
    Its ``compatibility`` values describe controlled inputs and configuration;
    ``target`` values describe the implementation whose version may be compared.
    """
    metadata = system_metadata or {}
    if not isinstance(metadata, dict):
        raise BaselineFormatError("system metadata must be a JSON object")
    unknown_metadata = set(metadata) - {"compatibility", "target", "run"}
    if unknown_metadata:
        raise BaselineFormatError(
            f"system metadata has unknown section(s): {sorted(unknown_metadata)}"
        )

    corpus_hash = hash_paths(root, corpus)
    case_set_hash = hash_paths(root, cases)
    contracts_hash = hash_paths(
        root,
        root / "skill" / "contracts.py",
        root / "skill" / "schemas.py",
        root / "server_mcp.py",
        root / "server_rest.py",
    )
    orchestration_hash = hash_paths(
        root,
        root / "harness" / "baselines.py",
        root / "harness" / "definitions",
        root / "harness" / "execution.py",
        root / "harness" / "runner.py",
    )
    validator_hash = hash_paths(root, root / "harness" / "validators")
    ranking_hash = hash_paths(root, root / "harness" / "ranking_metrics.py")
    dependency_lock_hash = hash_paths(root, root / "uv.lock")
    retrieval_skill_version = hash_paths(root, root / "skill")
    server_paths = [root / "skill" / "fake_server.py"]
    if transport == "mcp":
        server_paths.append(root / "server_mcp.py")
    elif transport == "rest":
        server_paths.append(root / "server_rest.py")
    knowledge_server_version = hash_paths(root, *server_paths)

    common = {
        "evaluation_profile": "retrieval-and-agent-read-path",
        "evaluation_level": "component",
        "target_interface": "knowledge-server",
        "environment_class": "controlled-synthetic",
        "mode": mode,
        "transport": transport,
        "executions": executions,
        "corpus_version": corpus_version,
        "corpus_hash": corpus_hash,
        "case_set_hash": case_set_hash,
        "contracts_hash": contracts_hash,
        "orchestration_hash": orchestration_hash,
        "dependency_lock_hash": dependency_lock_hash,
        "python": sys.version.split()[0],
        "mcp_sdk": _package_version("mcp"),
        "corpus_snapshot": f"{corpus_version}:{corpus_hash}",
        "index_schema_version": "fixture-v1",
        "chunking_version": "not-applicable",
        "embedding_model": "not-applicable-token-overlap",
        "embedding_model_version": "not-applicable",
        "embedding_dimensions": 0,
        "vocabulary_version": "fixture-v1",
        "ontology_version": "fixture-v1",
        "permission_policy_version": "fixture-scope-v1",
    }
    compatibility_metadata = metadata.get("compatibility")
    if compatibility_metadata is not None:
        if not isinstance(compatibility_metadata, dict):
            raise BaselineFormatError(
                "system metadata 'compatibility' must be an object"
            )
        protected_overrides = set(compatibility_metadata) & INSTRUMENT_MANAGED_FIELDS
        if protected_overrides:
            raise BaselineFormatError(
                "system metadata cannot override evaluation-managed compatibility "
                f"field(s): {sorted(protected_overrides)}"
            )
    common = _merge(common, compatibility_metadata, "compatibility")

    target = {
        "knowledge_server_version": knowledge_server_version,
        "retrieval_skill_version": retrieval_skill_version,
        "graph_vector_store": "fixture-memory",
        "graph_vector_store_version": "fixture-v1",
        "index_build_id": corpus_hash,
        "retrieval_configuration_version": "token-overlap-v1",
    }
    target = _merge(target, metadata.get("target"), "target")

    run = {
        "run_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }
    run = _merge(run, metadata.get("run"), "run")

    declared_changes = []
    for field_name in change_under_test:
        canonical = (
            field_name if field_name.startswith("target.") else f"target.{field_name}"
        )
        if canonical not in declared_changes:
            declared_changes.append(canonical)

    return {
        "schema_version": MANIFEST_VERSION,
        "compatibility": {
            "common": common,
            "profiles": {
                "validators": {
                    "validator_implementation_hash": validator_hash,
                },
                "ranking": {
                    "profile_version": RANKING_PROFILE_VERSION,
                    "metric_implementation_hash": ranking_hash,
                    "metrics": ["recall@k", "precision@5", "mrr", "ndcg@k"],
                    "regression_policy": REGRESSION_POLICY_VERSION,
                    "absolute_drop_tolerance": DEFAULT_TOLERANCE,
                },
                # Report-only: compare_records()/validate_record() are only ever
                # called with result_family="ranking" (see runner.py), so this
                # profile is descriptive metadata, never read for compatibility
                # or regression gating. No regression_policy/tolerance until a
                # real threshold is approved -- see LATENCY-MEASUREMENT-PLAN.md.
                "latency": {
                    "profile_version": "latency-v1",
                    "measurement": "wall_clock_ms_per_search_call",
                    "gated": False,
                },
            },
        },
        "target": target,
        "comparison": {"change_under_test": declared_changes},
        "run": run,
    }


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BaselineFormatError(f"{path} must be an object")
    return value


def validate_record(record: Any, *, result_family: str = "ranking") -> dict[str, Any]:
    record = _require_mapping(record, "run record")
    manifest = _require_mapping(record.get("manifest"), "manifest")
    if manifest.get("schema_version") != MANIFEST_VERSION:
        raise BaselineFormatError(
            "manifest.schema_version must be "
            f"{MANIFEST_VERSION}; got {manifest.get('schema_version')!r}"
        )
    compatibility = _require_mapping(
        manifest.get("compatibility"), "manifest.compatibility"
    )
    _require_mapping(compatibility.get("common"), "manifest.compatibility.common")
    profiles = _require_mapping(
        compatibility.get("profiles"), "manifest.compatibility.profiles"
    )
    _require_mapping(
        profiles.get(result_family),
        f"manifest.compatibility.profiles.{result_family}",
    )
    _require_mapping(manifest.get("target"), "manifest.target")
    comparison = _require_mapping(manifest.get("comparison"), "manifest.comparison")
    changes = comparison.get("change_under_test")
    if not isinstance(changes, list) or not all(isinstance(item, str) for item in changes):
        raise BaselineFormatError(
            "manifest.comparison.change_under_test must be a list of field names"
        )
    if any(not item.startswith("target.") for item in changes):
        raise BaselineFormatError(
            "change_under_test may declare only target fields"
        )
    target = _require_mapping(manifest.get("target"), "manifest.target")
    unknown_changes = [
        item for item in changes if item.removeprefix("target.") not in target
    ]
    if unknown_changes:
        raise BaselineFormatError(
            f"change_under_test names unknown target field(s): {unknown_changes}"
        )
    cases = record.get("cases")
    if not isinstance(cases, list):
        raise BaselineFormatError("cases must be an array")
    ids: list[str] = []
    for index, case in enumerate(cases):
        case = _require_mapping(case, f"cases[{index}]")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise BaselineFormatError(f"cases[{index}].id must be a nonblank string")
        metrics = case.get("metrics")
        if not isinstance(metrics, dict):
            raise BaselineFormatError(f"cases[{index}].metrics must be an object")
        if not all(
            isinstance(name, str)
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for name, value in metrics.items()
        ):
            raise BaselineFormatError(
                f"cases[{index}].metrics must map names to numeric values"
            )
        ids.append(case_id)
    if len(ids) != len(set(ids)):
        raise BaselineFormatError("case IDs must be unique")
    return record


def _flatten(value: dict[str, Any], prefix: str) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, item in sorted(value.items()):
        path = f"{prefix}.{key}"
        if isinstance(item, dict):
            flattened.update(_flatten(item, path))
        else:
            flattened[path] = item
    return flattened


def _mapping_differences(
    baseline: dict[str, Any], current: dict[str, Any], prefix: str
) -> list[CompatibilityDifference]:
    old = _flatten(baseline, prefix)
    new = _flatten(current, prefix)
    return [
        CompatibilityDifference(path, old.get(path), new.get(path))
        for path in sorted(set(old) | set(new))
        if old.get(path) != new.get(path)
    ]


def compare_records(
    baseline: Any,
    current: Any,
    *,
    result_family: str = "ranking",
) -> BaselineComparison:
    baseline = validate_record(baseline, result_family=result_family)
    current = validate_record(current, result_family=result_family)
    old_manifest = baseline["manifest"]
    new_manifest = current["manifest"]

    differences = _mapping_differences(
        old_manifest["compatibility"]["common"],
        new_manifest["compatibility"]["common"],
        "compatibility.common",
    )
    differences.extend(
        _mapping_differences(
            old_manifest["compatibility"]["profiles"][result_family],
            new_manifest["compatibility"]["profiles"][result_family],
            f"compatibility.profiles.{result_family}",
        )
    )

    allowed = set(new_manifest["comparison"]["change_under_test"])
    target_differences = _mapping_differences(
        old_manifest["target"], new_manifest["target"], "target"
    )
    differences.extend(diff for diff in target_differences if diff.path not in allowed)

    old_cases = {case["id"]: case for case in baseline["cases"]}
    new_cases = {case["id"]: case for case in current["cases"]}
    if old_cases.keys() != new_cases.keys():
        differences.append(
            CompatibilityDifference(
                "cases.ids", sorted(old_cases), sorted(new_cases)
            )
        )
    else:
        for case_id in sorted(old_cases):
            old_metrics = old_cases[case_id]["metrics"]
            new_metrics = new_cases[case_id]["metrics"]
            if old_metrics.keys() != new_metrics.keys():
                differences.append(
                    CompatibilityDifference(
                        f"cases.{case_id}.metrics",
                        sorted(old_metrics),
                        sorted(new_metrics),
                    )
                )

    if differences:
        return BaselineComparison(differences=differences)

    tolerance = new_manifest["compatibility"]["profiles"][result_family].get(
        "absolute_drop_tolerance"
    )
    if not isinstance(tolerance, (int, float)):
        raise BaselineFormatError(
            f"{result_family} profile has no numeric absolute_drop_tolerance"
        )
    if isinstance(tolerance, bool) or not math.isfinite(float(tolerance)) or tolerance < 0:
        raise BaselineFormatError(
            f"{result_family} profile absolute_drop_tolerance must be finite and nonnegative"
        )

    deltas: list[MetricDelta] = []
    for case_id in sorted(new_cases):
        for metric in sorted(new_cases[case_id]["metrics"]):
            old_value = float(old_cases[case_id]["metrics"][metric])
            new_value = float(new_cases[case_id]["metrics"][metric])
            delta = round(new_value - old_value, 10)
            deltas.append(
                MetricDelta(
                    case_id=case_id,
                    metric=metric,
                    baseline=old_value,
                    current=new_value,
                    delta=delta,
                    regression=delta < -float(tolerance),
                )
            )
    return BaselineComparison(metric_deltas=deltas)


def load_record(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BaselineFormatError(f"cannot read baseline {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BaselineFormatError(f"baseline {path} is not valid JSON: {exc}") from exc
    return validate_record(payload)


def write_record(path: Path, record: dict[str, Any]) -> None:
    validate_record(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

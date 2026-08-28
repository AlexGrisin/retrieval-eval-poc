# Versioned Compatibility Manifest + Regression Gate

## Description

`harness/baselines.py::build_run_manifest()` produces a
`schema_version`-stamped manifest split into:
- `compatibility.common` — environment/target-independent facts (mode,
  transport, corpus/case/contract/orchestration hashes, python version…)
- `compatibility.profiles.<family>` — per-result-family facts (today:
  `"validators"` and `"ranking"`, each with their own implementation hash
  and, for ranking, a numeric `absolute_drop_tolerance`)
- `target` — facts about the implementation under test, which **is**
  allowed to change between baseline and current run
- `comparison.change_under_test` — an explicit allow-list of which
  `target.*` fields may legitimately differ from the baseline for this
  comparison

`compare_records()` refuses to compare two runs whose `common` or
`profiles` fields differ, or whose `target` fields differ **outside** the
declared `change_under_test` allow-list (`BaselineComparison.compatible`
is false) — the whole point being that comparing metrics across an
incompatible environment/contract change would produce a meaningless
number. Only once compatibility is established does it compute per-case
metric deltas against `absolute_drop_tolerance` to flag regressions.
Compatibility and metric regression are two separate, sequential
questions — never conflated into one pass/fail score.

`validate_record()` is the single gate both `load_record()` (reading a
baseline from disk) and `write_record()` (writing a new one) pass through,
so a malformed manifest can never reach disk or be used for comparison —
mirrors `fixture-load-and-validate.md`'s "validate once, at the boundary"
idea, applied to run records instead of authored YAML.

## Template / Example

```python
# Adding a new result family (e.g. "safety") to compare independently of
# "ranking":

common["evaluation_profile"] = "..."  # unchanged, environment-level facts

profiles = {
    "validators": {...},
    "ranking": {...},
    # EXTENSION POINT: new family gets its own profile block with its own
    # implementation hash and, if it has numeric metrics, its own
    # absolute_drop_tolerance — never reuse another family's tolerance.
    "safety": {
        "profile_version": "safety-v1",
        "metric_implementation_hash": hash_paths(root, root / "harness" / "safety.py"),
        "metrics": ["violation_rate"],
        "regression_policy": "absolute-drop-v1",
        "absolute_drop_tolerance": 0.0,
    },
}
```

```python
# Comparing under the new family — result_family threads through both
# validate_record() and compare_records() so an unrelated family's
# differences never block or pollute this comparison.
comparison = compare_records(baseline, current, result_family="safety")
if not comparison.compatible:
    ...  # refuse: environment/contract changed, metrics are not comparable
elif comparison.regressions:
    ...  # flag: same environment/contract, metric dropped beyond tolerance
```

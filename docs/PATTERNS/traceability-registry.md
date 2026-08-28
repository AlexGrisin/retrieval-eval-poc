# Traceability Registry + record/skip Idiom

## Description

A dict-based registry (`harness/validators/registry.py`'s `CHECKS` and
`ANSWER_CHECKS`) maps every check name to
`{declared_by, status, source, rationale}`, where `status` is one of
`traced` / `inferred` / `unratified`. `describe(name)` looks up this
metadata, and — critically — returns an explicit `"UNTRACEABLE"` sentinel
record for an unregistered name instead of raising `KeyError`. A typo'd or
forgotten check name therefore becomes a loud, uniform build-time
invariant failure ("check has no entry in the registry") rather than a
silent pass or an unhandled exception deep in a report generator.

Two independent call sites re-implement the same `record(name, ...)` /
`skip(name, reason)` closure pair around `describe()`:
`harness/runner.py`'s `run_case()` and `harness/agent/runner.py`'s
`evaluate_agent_response()`. Both look up `describe(name)`, attach
`traceability`/`source` to the result, and treat a missing registry entry
as an invariant failure — the same idiom, not shared code, because each
lives in a different result shape (a plain dict in `runner.py`, an
`AgentCheckResult` pydantic model in `agent/runner.py`).

`render_inventory()` in the same module renders the whole registry without
executing any case — see `self-documenting-inventory.md`.

## Template / Example

```python
# 1. Register the check's provenance BEFORE wiring it into a runner.
# harness/validators/registry.py
CHECKS["my_module:my_new_check"] = {
    "declared_by": "<where the requirement text lives, e.g. a case field>",
    "status": "traced",  # or "inferred" / "unratified" — be honest about this
    "source": "<spec section, task doc, or 'case-specific expectation'>",
    "rationale": (
        "<why this must be a deterministic build gate, not a softer score>"
    ),
}
```

```python
# 2. Reuse the record()/skip() shape at the call site — do not invent a
# second reporting convention.
def record(name: str, ok: bool, detail: str = "") -> None:
    meta = describe(name)
    checks.append({
        "name": name, "status": "ok" if ok else "fail", "detail": detail,
        "traceability": meta["status"], "source": meta["source"],
    })
    # EXTENSION POINT: an UNTRACEABLE check is itself an invariant failure —
    # never let an unregistered check name pass silently.
    if meta["status"] == "UNTRACEABLE":
        invariant_failures.append(
            f"check {name!r} has no entry in the registry; every check "
            "must record where its requirement comes from"
        )
    if not ok:
        invariant_failures.append(detail or name)


def skip(name: str, why: str) -> None:
    meta = describe(name)
    checks.append({
        "name": name, "status": "skip", "detail": why,
        "traceability": meta["status"], "source": meta["source"],
    })
```

A new family of checks (e.g. future safety checks) should get its own
`*_CHECKS` dict merged into `CHECKS` (as `ANSWER_CHECKS` is merged today),
plus an `applies_to(name, case)` branch — never inline ad hoc pass/fail
booleans without a registry entry.

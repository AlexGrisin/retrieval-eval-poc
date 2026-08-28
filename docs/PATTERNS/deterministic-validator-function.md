# Deterministic Validator Function

## Description

Every zero-tolerance check is a small, pure function named
`check_<requirement>(actual, expected, ...) -> str | None`. It returns
`None` on pass and a human-readable failure description on fail — never a
boolean, never an exception for an expected failure mode. Callers only
ever test `is None`; they never branch on the shape of the returned
string. This keeps every caller (`harness/runner.py`'s `record()`,
`harness/agent/runner.py`'s `record()`) uniform regardless of which
validator produced the detail, and it means a failure message is always
self-explanatory in a report without a second lookup.

**Evidence (read directly):** every function in `harness/validators/answer.py`,
`harness/validators/contract.py`, `harness/validators/retrieval.py`, and
`harness/validators/formatting.py` follows this exact shape, e.g.
`check_must_not_return`, `check_expected_first_result`,
`check_every_result_has_provenance`, `check_citations_were_retrieved`,
`check_response_contract`.

## Template / Example

```python
from __future__ import annotations


def check_my_requirement(actual: object, expected: object) -> str | None:
    """One line: what this check enforces and why it is zero-tolerance.

    Returns None on pass. Returns a description of the violation on fail —
    never raises for an expected failure, never returns True/False.
    """
    # EXTENSION POINT: comparison / lookup logic goes here.
    violation = actual != expected
    if violation:
        return f"my requirement violated: expected {expected!r}, got {actual!r}"
    return None
```

Wiring a new check into the runner:

```python
# in harness/runner.py's run_case(), or harness/agent/runner.py's
# evaluate_agent_response() — reuse the existing record()/skip() closures,
# do not invent a second reporting shape. See traceability-registry.md.
detail = check_my_requirement(actual_value, expected_value)
record("my_module:my_requirement", detail is None, detail or "")
```

Every new check name used with `record()`/`skip()` must also be added to
`harness/validators/registry.py`'s `CHECKS` (or `ANSWER_CHECKS`) — see
`traceability-registry.md`. An unregistered name is treated as an
`UNTRACEABLE` invariant failure by design, not a silent pass.

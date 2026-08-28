# Pytest Case-Check Marker & Traceability-Driven Test Generation

## Description

`tests/test_02_retrieval.py`'s `_params()` generates one parametrized
pytest test per `(case, applicable validator)` pair by iterating
`harness.validators.CHECKS` and calling `applies_to(name, case)` — so a
case file that doesn't declare, say, `expect.must_not_return` simply never
generates that test, rather than generating it and skipping at runtime for
the wrong reason (or worse, silently passing).

Every generated test carries:
- a `pytest.mark.case_check(case_id, level)` marker. Level ordering is
  fixed by `LEVEL_ORDER` (`tests/test_02_retrieval.py`) / `level_order`
  (`tests/conftest.py`'s `pytest_collection_modifyitems`), so
  request-level checks for a case always run and report before that same
  case's response/expectation/answer/ranking/judge-level checks.
- a traceability marker (`traced` / `inferred` / `unratified` /
  `untraceable`) derived directly from the same `describe()` metadata the
  CLI runner uses — so `pytest -m "not unratified"` filters the build down
  to only requirements with a ratified source, with zero duplicated
  bookkeeping between the CLI runner and the test suite.

`tests/support.py::framework_id()` gives a non-case, non-parametrized
"framework" test (a sanity check on a validator itself, not on a case) a
readable, stable pytest ID via the same indirect-parametrize trick pytest
normally reserves for real parametrization — see
`test_response_contract_reports_wrong_field_type` for an example
consumer. `tests/conftest.py::pytest_sessionstart` refuses `-n auto`
(xdist parallel workers) unless exactly `-m framework` is selected,
because letting evaluation cases run across workers would let one logical
case execute more than once — which the harness treats as a defect
(`FLAKY`), not as speedup.

## Template / Example

```python
# Generating one test per (case, applicable check):
def _params():
    for case in load_cases():
        for name, meta in sorted(CHECKS.items()):
            if not applies_to(name, case):
                continue  # EXTENSION POINT: never generate + skip; just don't generate
            marks = [_MARKERS[meta["status"]], pytest.mark.case_check(case["id"], LEVELS[name])]
            yield pytest.param(case["id"], name, marks=marks,
                                id=f"{case['id']}:{LEVELS[name]}:{name.split(':', 1)[1]}")


@pytest.mark.parametrize("case_id,check_name", list(_params()))
@pytest.mark.evaluation
def test_check(case_results, case_id, check_name):
    ...
```

```python
# Giving a non-case "framework" test a readable, stable ID:
from tests.support import framework_id

@framework_id("synthetic:response:wrong_field_type_rejected")
def test_my_framework_sanity_check():
    ...  # EXTENSION POINT: use this for any test that checks the
         # harness/validators themselves, not a specific evaluation case
```

# Pytest Case-Check Marker & Traceability-Driven Test Generation

> 2026-09-22: the `framework_id()` / `-m framework` half of this pattern was removed
> along with the entire framework-marked test layer -- every test now runs against the
> live knowledge server. The `case_check` marker and traceability-marker mechanism
> below is unaffected and still current.

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

`tests/conftest.py::pytest_sessionstart` refuses `-n auto` (xdist parallel workers)
unconditionally -- every test now hits the live knowledge server, and letting cases
run across workers would let one logical case execute more than once, which the
harness treats as a defect (`FLAKY`), not as speedup. pytest-xdist is not a project
dependency.

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

# Lazy Cached View Chain over Shared Execution

## Description

`harness/execution.py` layers three classes over one shared, expensive
execution so that independent consumers can request the same case
repeatedly without repeating the work:

- `CaseExecutions` — runs a case **at most once** (via an injected
  `case_runner`), caching the full captured input (`case`,
  `retrieval_result`, `response`) in a private `_cache` dict keyed by
  `case_id`, populated lazily in `__getitem__`.
- `CaseResults` — a thin view exposing just `.retrieval_result` from the
  same `CaseExecutions`, no cache of its own needed (it delegates every
  lookup through).
- `CapturedRuns` — a view that, the *first* time a `case_id` is requested,
  calls `evaluate_agent_response()` (an actual computation, not just a
  dict projection) and caches the resulting `AgentRun`; every subsequent
  request for the same `case_id` is a pure cache hit.

This lets pytest fixtures at session scope (`case_results` for
request/response/expectation-level checks, `captured_runs` for
answer/ranking/judge-level checks — see
`tests/conftest.py`) each request the same `case_id` independently across
many parametrized tests, with each additional request being a cache hit
rather than a second live call into the retrieval skill.

## Template / Example

```python
class CaseExecutions:
    """Execute each requested case once; cache its complete captured inputs."""

    def __init__(self, cases, corpus, transport, response_dir, *,
                 case_runner=run_case, response_loader=load_agent_response):
        self._cases = {case["id"]: case for case in cases}
        self._corpus, self._transport, self._response_dir = corpus, transport, response_dir
        self._case_runner, self._response_loader = case_runner, response_loader
        self._cache: dict[str, dict] = {}

    def __getitem__(self, case_id: str) -> dict:
        if case_id in self._cache:
            return self._cache[case_id]
        # EXTENSION POINT: the actual (expensive) execution happens here,
        # exactly once per case_id, on first access.
        execution = {"case": self._cases[case_id], ...}
        self._cache[case_id] = execution
        return execution


class MyDerivedView:
    """New view over the same shared executions — follow this exact shape."""

    def __init__(self, executions: CaseExecutions) -> None:
        self._executions = executions
        # EXTENSION POINT: a derived view keeps its OWN private cache if it
        # does further computation (like CapturedRuns); a pure projection
        # (like CaseResults) needs no cache of its own.
        self._cache: dict[str, object] = {}

    def __getitem__(self, case_id: str):
        if case_id in self._cache:
            return self._cache[case_id]
        execution = self._executions[case_id]  # reuses the shared cache
        # EXTENSION POINT: derive/compute from the shared execution here,
        # never re-run the underlying case.
        result = compute_my_thing(execution)
        self._cache[case_id] = result
        return result
```

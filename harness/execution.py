"""Lazy, case-scoped execution shared by pytest and future integrations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from harness.agent.runner import evaluate_agent_response
from harness.definitions.agent_responses import load_agent_response
from harness.definitions.cases import get_answer_evaluation
from harness.runner import run_case


class CaseExecutions:
    """Execute each requested case's retrieval once and cache it.

    Deliberately does NOT also load the case's answer fixture here. That used to
    happen in the same step, uncached on failure: a missing or malformed
    fixtures/agent_responses/<case_id>.yaml raised before the already-successful
    retrieval was cached, so every consumer -- including CaseResults, which never
    needs the fixture at all -- re-ran the live retrieval call and failed again.
    Retrieval and the answer fixture are independent failure domains; only
    CapturedRuns needs the latter, so it loads it itself, lazily, via
    load_response().
    """

    def __init__(
        self,
        cases: list[dict],
        server_url: str,
        response_dir: Path,
        *,
        case_runner: Callable[[dict, str], dict] = run_case,
        response_loader: Callable[[Path], Any] = load_agent_response,
    ) -> None:
        self._cases = {case["id"]: case for case in cases}
        self._server_url = server_url
        self._response_dir = response_dir
        self._case_runner = case_runner
        self._response_loader = response_loader
        self._cache: dict[str, dict] = {}

    def __getitem__(self, case_id: str) -> dict:
        if case_id not in self._cache:
            case = self._cases[case_id]
            retrieval_result = self._case_runner(case, self._server_url)
            self._cache[case_id] = {"case": case, "retrieval_result": retrieval_result}
        return self._cache[case_id]

    def load_response(self, case_id: str) -> Any:
        """Load the case's declared answer fixture. Not cached here -- CapturedRuns
        caches the evaluated run, which is the only thing that needs this value."""
        return self._response_loader(self._response_dir / f"{case_id}.yaml")

    @property
    def executed_ids(self) -> tuple[str, ...]:
        return tuple(self._cache)


class CaseResults:
    """Lazy retrieval-result view over case executions."""

    def __init__(self, executions: CaseExecutions) -> None:
        self._executions = executions

    def __getitem__(self, case_id: str) -> dict:
        return self._executions[case_id]["retrieval_result"]


class CapturedRuns:
    """Lazy deterministic answer-evaluation view over the same executions."""

    def __init__(self, executions: CaseExecutions) -> None:
        self._executions = executions
        self._cache: dict[str, object] = {}

    def __getitem__(self, case_id: str) -> object:
        if case_id in self._cache:
            return self._cache[case_id]
        execution = self._executions[case_id]
        if get_answer_evaluation(execution["case"]) is None:
            raise KeyError(f"{case_id} does not declare answer_evaluation")
        response = self._executions.load_response(case_id)
        run = evaluate_agent_response(
            case=execution["case"],
            retrieval_result=execution["retrieval_result"],
            response=response,
        )
        self._cache[case_id] = run
        return run

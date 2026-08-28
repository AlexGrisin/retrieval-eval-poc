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
    """Execute each requested case once and cache its complete captured inputs."""

    def __init__(
        self,
        cases: list[dict],
        corpus: Path,
        transport: str,
        response_dir: Path,
        *,
        case_runner: Callable[[dict, Path, str], dict] = run_case,
        response_loader: Callable[[Path], Any] = load_agent_response,
    ) -> None:
        self._cases = {case["id"]: case for case in cases}
        self._corpus = corpus
        self._transport = transport
        self._response_dir = response_dir
        self._case_runner = case_runner
        self._response_loader = response_loader
        self._cache: dict[str, dict] = {}

    def __getitem__(self, case_id: str) -> dict:
        if case_id in self._cache:
            return self._cache[case_id]

        case = self._cases[case_id]
        retrieval_result = self._case_runner(case, self._corpus, self._transport)
        response = None
        if get_answer_evaluation(case) is not None:
            response = self._response_loader(self._response_dir / f"{case_id}.yaml")
        execution = {
            "case": case,
            "retrieval_result": retrieval_result,
            "response": response,
        }
        self._cache[case_id] = execution
        return execution

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
        response = execution["response"]
        if response is None:
            raise KeyError(f"{case_id} does not declare answer_evaluation")
        run = evaluate_agent_response(
            case=execution["case"],
            retrieval_result=execution["retrieval_result"],
            response=response,
        )
        self._cache[case_id] = run
        return run

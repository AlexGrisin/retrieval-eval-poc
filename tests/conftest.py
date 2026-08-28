"""Pytest wiring for deterministic runtime validation.

CLI-first by design: these tests call the same `run_case` the CLI runner calls, so
there is one code path and no drift. Pytest owns per-check reporting and selection;
the CLI keeps the metrics, the baseline, the run manifest, and the FLAKY verdict.

Deliberately NOT here: any retry-on-failure plugin. A case that passes three times
in five is the finding, not something to rerun away.
"""

from __future__ import annotations

import json
from pathlib import Path

import allure
import pytest

from harness.agent.runner import evaluate_agent_response
from harness.definitions.agent_responses import load_agent_response
from harness.execution import CapturedRuns, CaseExecutions, CaseResults
from harness.runner import run_case
from tests.support import ROOT, load_cases

RESPONSE_DIR = ROOT / "fixtures" / "agent_responses"


def pytest_addoption(parser):
    parser.addoption(
        "--transport", action="store", default="inprocess",
        choices=["inprocess", "mcp", "rest"],
        help="inprocess calls the fake directly; mcp crosses a real protocol boundary",
    )
    parser.addoption(
        "--corpus", action="store", default=str(ROOT / "fixtures" / "corpus.yaml"),
        help="override the fixture corpus, e.g. a mutated one for a sabotage drill",
    )
    parser.addoption(
        "--judge", action="store_true", default=False,
        help="call the configured live LLM Gateway for generated-answer judging",
    )


def pytest_sessionstart(session):
    """Do not let xdist execute one real evaluation case in several workers."""
    worker_count = getattr(session.config.option, "numprocesses", None)
    mark_expression = (session.config.option.markexpr or "").strip()
    if worker_count and mark_expression != "framework":
        raise pytest.UsageError(
            "parallel workers are supported only with exactly '-m framework'; "
            "evaluation and live-judge runs must be single-process so every case "
            "executes once"
        )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """A normal pytest run must never make a live model call."""
    if not config.getoption("--judge"):
        selected, deselected = [], []
        for item in items:
            (deselected if item.get_closest_marker("judge") else selected).append(item)
        if deselected:
            config.hook.pytest_deselected(items=deselected)
            items[:] = selected

    case_order = {case["id"]: index for index, case in enumerate(load_cases())}
    level_order = {
        "definition": 1,
        "request": 2,
        "response": 3,
        "expectation": 4,
        "answer": 5,
        "ranking": 6,
        "judge": 7,
    }
    evaluation_positions = [
        index
        for index, item in enumerate(items)
        if item.get_closest_marker("evaluation")
    ]

    def evaluation_order(item):
        marker = item.get_closest_marker("case_check")
        if marker is None or len(marker.args) != 2:
            raise pytest.UsageError(
                f"evaluation item {item.nodeid} must declare "
                "@pytest.mark.case_check(case_id, level)"
            )
        case_id, level = marker.args
        return case_order[case_id], level_order[level]

    ordered_evaluation = sorted(
        (items[index] for index in evaluation_positions),
        key=evaluation_order,
    )
    for index, item in zip(evaluation_positions, ordered_evaluation):
        items[index] = item


def _attach_json(name: str, data) -> None:
    allure.attach(
        json.dumps(data, indent=2, default=str, sort_keys=True),
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )


@pytest.fixture(autouse=True)
def _allure_case_report(request):
    """Map the case:level:check hierarchy onto Allure and attach captured evidence.

    Suite/sub-suite/story mirror the existing `case_check` marker and parametrize
    id exactly, so the Allure tree needs no separate taxonomy to maintain. Evidence
    is attached in fixture teardown -- after the test body has run, pass or fail --
    so a passing case is still inspectable, not only a failing one.
    """
    marker = request.node.get_closest_marker("case_check")
    if marker is None:
        yield
        return

    case_id, level = marker.args
    allure.dynamic.parent_suite("Retrieval evaluation")
    allure.dynamic.suite(case_id)
    allure.dynamic.sub_suite(level)
    callspec = getattr(request.node, "callspec", None)
    if callspec is not None:
        parts = callspec.id.split(":", 2)
        if len(parts) == 3:
            allure.dynamic.story(parts[2])

    yield

    if "case_results" in request.fixturenames:
        result = request.getfixturevalue("case_results")[case_id]
        _attach_json("retrieval trace", result["trace"])
        _attach_json("ranking metrics", result["metrics"])
    if "captured_runs" in request.fixturenames:
        try:
            run = request.getfixturevalue("captured_runs")[case_id]
        except KeyError:
            pass
        else:
            _attach_json("captured agent run", run.model_dump())


@pytest.fixture(scope="session")
def transport(request) -> str:
    return request.config.getoption("--transport")


@pytest.fixture(scope="session")
def corpus(request) -> Path:
    return Path(request.config.getoption("--corpus"))


@pytest.fixture(scope="session")
def case_executions(transport, corpus) -> CaseExecutions:
    """Provide lazy, case-isolated execution and capture.

    The POC runs fixture-backed retrieval and then loads a saved final answer. Real
    integration replaces this provider with an agent adapter that captures retrieval
    and the final answer from one execution.
    """
    return CaseExecutions(load_cases(), corpus, transport, RESPONSE_DIR)


@pytest.fixture(scope="session")
def case_results(case_executions) -> CaseResults:
    """Expose captured retrieval results to stage 2 and stage 4 checks."""
    return CaseResults(case_executions)


@pytest.fixture(scope="session")
def captured_runs(case_executions) -> CapturedRuns:
    """Expose answer evaluation over each case's single captured execution."""
    return CapturedRuns(case_executions)


@pytest.fixture
def _framework_id(request):
    """Indirect parametrization target used only to expose readable pytest IDs."""
    return request.param


@pytest.fixture(scope="session")
def synthetic_case() -> dict:
    """Fixed local case for framework tests; never uses the selected target."""
    return next(
        case for case in load_cases()
        if case["id"] == "case-001-rounding-fix-ranking"
    )


@pytest.fixture(scope="session")
def synthetic_retrieval_result(synthetic_case) -> dict:
    return run_case(
        synthetic_case,
        ROOT / "fixtures" / "corpus.yaml",
        "inprocess",
    )


@pytest.fixture(scope="session")
def synthetic_agent_run(synthetic_case, synthetic_retrieval_result):
    response = load_agent_response(RESPONSE_DIR / "case-001-rounding-fix-ranking.yaml")
    return evaluate_agent_response(
        case=synthetic_case,
        retrieval_result=synthetic_retrieval_result,
        response=response,
    )

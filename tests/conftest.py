"""Pytest wiring for the real deployed-skill evaluation target."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

import allure
import pytest

from harness.agent.claude_target import (
    AgentCaseOutcome,
    ClaudeCodeSkillTarget,
    ClaudeTargetConfig,
    evaluate_agent_case,
)
from tests.support import ROOT, load_cases


def pytest_addoption(parser):
    parser.addoption(
        "--judge",
        action="store_true",
        default=False,
        help="call the configured live LLM Gateway after deterministic checks",
    )
    parser.addoption("--claude-bin", action="store", default="claude")
    parser.addoption("--agent-model", action="store", default=None)
    parser.addoption("--agent-effort", action="store", default=None)
    parser.addoption("--agent-timeout", action="store", type=int, default=300)
    parser.addoption("--plugin-dir", action="store", default=None)
    parser.addoption("--mcp-config", action="store", default=None)


def pytest_ignore_collect(collection_path, config):
    """Do not collect optional live judges unless they were explicitly requested."""
    return collection_path.name == "test_live_judges.py" and not config.getoption(
        "--judge"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Select optional judges, prevent duplicate live runs, and order by case."""
    worker_count = getattr(config.option, "numprocesses", None)
    if worker_count and any(
        item.get_closest_marker("agent_target") is not None for item in items
    ):
        raise pytest.UsageError(
            "parallel workers are not supported for live agent cases; "
            "use -m framework with -n"
        )

    case_order = {case["id"]: index for index, case in enumerate(load_cases())}
    level_order = {"answer": 1, "judge": 2}
    evaluation_positions = [
        index for index, item in enumerate(items)
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

    ordered = sorted(
        (items[index] for index in evaluation_positions),
        key=evaluation_order,
    )
    for index, item in zip(evaluation_positions, ordered):
        items[index] = item


@pytest.fixture(autouse=True)
def _allure_case_hierarchy(request):
    marker = request.node.get_closest_marker("case_check")
    if marker is not None:
        case_id, level = marker.args
        allure.dynamic.parent_suite("Deployed skill evaluation")
        allure.dynamic.suite(case_id)
        allure.dynamic.sub_suite(level)
        callspec = getattr(request.node, "callspec", None)
        if callspec is not None:
            parts = callspec.id.split(":", 2)
            if len(parts) == 3:
                allure.dynamic.story(parts[2])
    yield


@pytest.fixture(scope="session")
def agent_target(request) -> ClaudeCodeSkillTarget:
    workspace = ROOT.parent / "sysco-context-layer"
    default_plugin = (
        workspace
        / "sysco-context-layer-marketplace"
        / "plugins"
        / "sdp-context"
    )
    plugin_dir = Path(request.config.getoption("--plugin-dir") or default_plugin)
    mcp_config = Path(
        request.config.getoption("--mcp-config") or plugin_dir / ".mcp.json"
    )
    if not plugin_dir.is_dir():
        raise pytest.UsageError(f"plugin directory does not exist: {plugin_dir}")
    if not mcp_config.is_file():
        raise pytest.UsageError(f"MCP config does not exist: {mcp_config}")
    return ClaudeCodeSkillTarget(
        ClaudeTargetConfig(
            claude_bin=request.config.getoption("--claude-bin"),
            plugin_dir=plugin_dir,
            mcp_config=mcp_config,
            cwd=workspace,
            timeout_seconds=request.config.getoption("--agent-timeout"),
            model=request.config.getoption("--agent-model"),
            effort=request.config.getoption("--agent-effort"),
        )
    )


@pytest.fixture(scope="session")
def knowledge_server_ready(agent_target: ClaudeCodeSkillTarget) -> str:
    """Fail before model execution when the configured real server is unavailable."""
    try:
        config = json.loads(agent_target.config.mcp_config.read_text())
        servers = config["mcpServers"]
        server = servers.get("ks") or next(iter(servers.values()))
        mcp_url = server["url"]
        parts = urlsplit(mcp_url)
        health_url = urlunsplit((parts.scheme, parts.netloc, "/healthz", "", ""))
        with urlopen(health_url, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
    except (
        KeyError,
        StopIteration,
        TypeError,
        ValueError,
        OSError,
        URLError,
        RuntimeError,
    ) as exc:
        raise pytest.UsageError(
            "the real Knowledge Server is not ready; start it before evaluation. "
            f"MCP config: {agent_target.config.mcp_config}. Cause: {exc}"
        ) from exc
    return mcp_url


class _AgentCaseResults:
    def __init__(self, target: ClaudeCodeSkillTarget) -> None:
        self._target = target
        self._cases = {case["id"]: case for case in load_cases()}
        self._cache: dict[str, AgentCaseOutcome] = {}

    def __getitem__(self, case_id: str) -> AgentCaseOutcome:
        if case_id not in self._cache:
            case = self._cases[case_id]
            self._cache[case_id] = evaluate_agent_case(
                case, self._target.execute(case)
            )
        return self._cache[case_id]


@pytest.fixture(scope="session")
def agent_case_results(
    agent_target: ClaudeCodeSkillTarget,
    knowledge_server_ready: str,
) -> _AgentCaseResults:
    return _AgentCaseResults(agent_target)

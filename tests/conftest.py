"""Pytest wiring for the real deployed-skill evaluation target."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

import allure
import pytest
from dotenv import dotenv_values

from harness.agent.claude_target import (
    AgentCaseOutcome,
    ClaudeCodeSkillTarget,
    ClaudeTargetConfig,
    evaluate_agent_case,
)
from harness.aliases import AliasConfigurationError, AliasResolver
from harness.run_artifacts import (
    RunArtifacts,
    file_hash,
    git_metadata,
    server_snapshot,
    tree_hash,
)
from tests.support import ROOT, load_cases


LOCAL_ENV_VALUES = dotenv_values(ROOT / ".env")


def _runtime_path(request, option: str, environment: str) -> Path | None:
    """Resolve a portable path with CLI, local .env, then process-env precedence."""
    cli_value = request.config.getoption(option)
    local_value = LOCAL_ENV_VALUES.get(environment)
    environment_value = os.getenv(environment)
    value = next(
        (
            candidate
            for candidate in (cli_value, local_value, environment_value)
            if isinstance(candidate, str) and candidate.strip()
        ),
        None,
    )
    return Path(value).expanduser().resolve() if value else None


def _redact_outcome(outcome: AgentCaseOutcome, aliases: AliasResolver) -> AgentCaseOutcome:
    """Keep local corpus identifiers out of evidence, diagnostics, and judges."""
    evidence = outcome.evidence
    redacted_evidence = replace(
        evidence,
        tool_calls=[
            replace(
                call,
                args=aliases.redact(call.args),
                result=aliases.redact(call.result),
            )
            for call in evidence.tool_calls
        ],
        final_answer=aliases.redact(evidence.final_answer),
        raw_events=aliases.redact(evidence.raw_events),
        stderr=aliases.redact(evidence.stderr),
        usage=aliases.redact(evidence.usage),
    )
    response = outcome.agent_run.response
    if response is not None:
        response = response.model_copy(
            update={
                "answer": aliases.redact(response.answer),
                "citations": [
                    citation.model_copy(update={"key": aliases.redact(citation.key)})
                    for citation in response.citations
                ],
            }
        )
    redacted_run = outcome.agent_run.model_copy(
        update={
            "question": aliases.redact(outcome.agent_run.question),
            "retrieved_context": aliases.redact(outcome.agent_run.retrieved_context),
            "response": response,
            "retrieval_result": aliases.redact(outcome.agent_run.retrieval_result),
            "checks": [
                check.model_copy(
                    update={
                        "detail": aliases.redact(check.detail),
                        "source": aliases.redact(check.source),
                    }
                )
                for check in outcome.agent_run.checks
            ],
            "reference_answer": aliases.redact(outcome.agent_run.reference_answer),
        }
    )
    return replace(
        outcome,
        evidence=redacted_evidence,
        retrieval_result=aliases.redact(outcome.retrieval_result),
        agent_run=redacted_run,
        failures=aliases.redact(outcome.failures),
    )


def pytest_addoption(parser):
    parser.addoption(
        "--judge",
        action="store_true",
        default=False,
        help="score usable captured answers with the configured live LLM Gateway",
    )
    parser.addoption(
        "--judge-gate",
        action="store_true",
        default=False,
        help="fail judge tests whose scores are below authored rubric thresholds",
    )
    parser.addoption("--claude-bin", action="store", default="claude")
    parser.addoption("--agent-model", action="store", default=None)
    parser.addoption("--agent-effort", action="store", default=None)
    parser.addoption("--agent-timeout", action="store", type=int, default=300)
    parser.addoption(
        "--plugin-dir",
        action="store",
        default=None,
        help="skill plugin directory (or EVAL_PLUGIN_DIR in .env/environment)",
    )
    parser.addoption(
        "--mcp-config",
        action="store",
        default=None,
        help="MCP config file (or EVAL_MCP_CONFIG in .env/environment)",
    )
    parser.addoption(
        "--trials",
        action="store",
        type=int,
        default=1,
        help="independent Claude executions per live case (default: 1)",
    )
    parser.addoption(
        "--run-results-dir",
        action="store",
        default="run-results",
        help="directory for per-run manifest and captured evidence",
    )


def pytest_generate_tests(metafunc):
    """Add independent trial numbers without making case modules read pytest config."""
    if "trial" in metafunc.fixturenames:
        trials = metafunc.config.getoption("--trials")
        if trials < 1:
            raise pytest.UsageError("--trials must be at least 1")
        metafunc.parametrize("trial", range(1, trials + 1), ids=lambda trial: f"trial-{trial}")


def pytest_ignore_collect(collection_path, config):
    """Do not collect optional live judges unless they were explicitly requested."""
    return collection_path.name == "test_live_judges.py" and not config.getoption(
        "--judge"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Select optional judges, prevent duplicate live runs, and order by case."""
    if config.getoption("--judge-gate") and not config.getoption("--judge"):
        raise pytest.UsageError("--judge-gate requires --judge")
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
    plugin_dir = _runtime_path(request, "--plugin-dir", "EVAL_PLUGIN_DIR")
    if plugin_dir is None:
        raise pytest.UsageError(
            "plugin directory is required; pass --plugin-dir or set "
            "EVAL_PLUGIN_DIR in .env or the environment"
        )
    mcp_config = _runtime_path(request, "--mcp-config", "EVAL_MCP_CONFIG")
    if mcp_config is None:
        mcp_config = plugin_dir / ".mcp.json"
    if not plugin_dir.is_dir():
        raise pytest.UsageError(f"plugin directory does not exist: {plugin_dir}")
    if not mcp_config.is_file():
        raise pytest.UsageError(f"MCP config does not exist: {mcp_config}")
    return ClaudeCodeSkillTarget(
        ClaudeTargetConfig(
            claude_bin=request.config.getoption("--claude-bin"),
            plugin_dir=plugin_dir,
            mcp_config=mcp_config,
            cwd=ROOT,
            timeout_seconds=request.config.getoption("--agent-timeout"),
            model=request.config.getoption("--agent-model"),
            effort=request.config.getoption("--agent-effort"),
        )
    )


@pytest.fixture(scope="session")
def alias_resolver() -> AliasResolver:
    return AliasResolver.from_local_environment(LOCAL_ENV_VALUES)


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
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _domains_under_test() -> list[str]:
    domains = set()
    for case in load_cases():
        domains.update(("sdp", "paastry") if case["domain"] == "both" else (case["domain"],))
    return sorted(domains)


@pytest.fixture(scope="session")
def run_artifacts(
    request,
    agent_target,
    alias_resolver: AliasResolver,
    knowledge_server_ready: str,
) -> RunArtifacts:
    """Persist exactly which code, model settings, cases, and server data were used."""
    domains = _domains_under_test()
    try:
        server_before = alias_resolver.redact(
            server_snapshot(knowledge_server_ready, domains)
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise pytest.UsageError(
            "could not capture the Knowledge Server source registry; "
            f"do not run comparisons without it. Cause: {exc}"
        ) from exc
    manifest = {
        "schema_version": 1,
        "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "trials_per_case": request.config.getoption("--trials"),
        "cases": {case["id"]: file_hash(ROOT / "cases" / f"{case['id']}.yaml") for case in load_cases()},
        "evaluator": git_metadata(ROOT),
        "plugin": {
            "git": git_metadata(agent_target.config.plugin_dir),
            "tree_sha256": tree_hash(agent_target.config.plugin_dir),
            "mcp_config_sha256": file_hash(agent_target.config.mcp_config),
        },
        "claude": {
            "binary": agent_target.config.claude_bin,
            "version": _claude_version(agent_target.config.claude_bin),
            "requested_model": agent_target.config.model,
            "requested_effort": agent_target.config.effort,
            "timeout_seconds": agent_target.config.timeout_seconds,
        },
        "judge": {
            "enabled": request.config.getoption("--judge"),
            "gate_enabled": request.config.getoption("--judge-gate"),
        },
        "server_before": server_before,
        "attempts": [],
    }
    artifacts = RunArtifacts(Path(request.config.getoption("--run-results-dir")), manifest)

    def finish() -> None:
        try:
            artifacts.finish(
                alias_resolver.redact(server_snapshot(knowledge_server_ready, domains))
            )
        except Exception as exc:  # Preserve the original test outcome and explain comparability.
            artifacts.finish_with_server_error(f"{type(exc).__name__}: {exc}")

    request.addfinalizer(finish)
    return artifacts


def _claude_version(binary: str) -> str | None:
    try:
        completed = subprocess.run(
            [binary, "--version"], text=True, capture_output=True, check=False, timeout=10
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


class _AgentCaseResults:
    def __init__(
        self,
        target: ClaudeCodeSkillTarget,
        artifacts: RunArtifacts,
        aliases: AliasResolver,
    ) -> None:
        self._target = target
        self._cases = {case["id"]: case for case in load_cases()}
        self._artifacts = artifacts
        self._aliases = aliases
        self._cache: dict[tuple[str, int], AgentCaseOutcome] = {}

    def __getitem__(self, key: tuple[str, int]) -> AgentCaseOutcome:
        case_id, trial = key
        if key not in self._cache:
            case = self._cases[case_id]
            try:
                runtime_case = self._aliases.expand_case(case)
            except AliasConfigurationError as exc:
                raise pytest.UsageError(str(exc)) from exc
            outcome = _redact_outcome(
                evaluate_agent_case(runtime_case, self._target.execute(runtime_case)),
                self._aliases,
            )
            self._artifacts.record_outcome(case_id, trial, outcome)
            self._cache[key] = outcome
        return self._cache[key]


@pytest.fixture(scope="session")
def agent_case_results(
    agent_target: ClaudeCodeSkillTarget,
    alias_resolver: AliasResolver,
    knowledge_server_ready: str,
    run_artifacts: RunArtifacts,
) -> _AgentCaseResults:
    return _AgentCaseResults(
        agent_target,
        run_artifacts,
        alias_resolver,
    )

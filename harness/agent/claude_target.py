"""Execute and evaluate the deployed ``okf-knowledge`` Claude Code skill.

Each case starts a fresh Claude Code process, loads the real plugin, talks to the
real Knowledge Server over MCP, and evaluates the captured tool trace and final
user-visible answer from that same execution.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.agent.models import AgentResponse, AgentRun, Citation
from harness.agent.runner import evaluate_agent_response


ENTITY_LABELS = (
    "Service",
    "Team",
    "Person",
    "Repository",
    "Commit",
    "PullRequest",
    "Story",
    "Feature",
    "TestSuite",
    "DocChunk",
)
ENTITY_REFERENCE = re.compile(
    rf"\b({'|'.join(ENTITY_LABELS)})/([^\s,;\]\)]+)"
)
INSUFFICIENT_CONTEXT = re.compile(
    r"\b(?:not recorded|insufficient context|no relevant (?:knowledge|information))\b",
    re.IGNORECASE,
)
EXPLICIT_REFUSAL = re.compile(
    r"(?:^[\s#>*_-]*(?:not recorded|insufficient context)\b"
    r"|^[^\n]{0,100}\b(?:sdp|portal)\b[^\n]{0,80}:\**\s*not recorded\b)",
    re.IGNORECASE | re.MULTILINE,
)


class AgentTargetError(RuntimeError):
    """The real agent could not be executed or its event stream was unusable."""


def canonical_tool_name(name: str) -> str:
    """Collapse MCP namespace prefixes while retaining ordinary tool names."""
    if name.startswith("mcp__") and "__" in name:
        return name.rsplit("__", 1)[-1]
    return name


def _decode_jsonish(value: Any) -> Any:
    """Recover structured MCP output from Claude's possible content wrappers."""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    if isinstance(value, list):
        text_blocks = [
            item.get("text", "")
            for item in value
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if text_blocks and len(text_blocks) == len(value):
            return _decode_jsonish("".join(text_blocks))
    return value


@dataclass
class CapturedToolCall:
    id: str
    name: str
    args: dict[str, Any]
    result: Any = None
    is_error: bool = False

    @property
    def tool(self) -> str:
        return canonical_tool_name(self.name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tool": self.tool,
            "args": self.args,
            "result": self.result,
            "is_error": self.is_error,
        }


@dataclass
class CapturedExecution:
    tool_calls: list[CapturedToolCall]
    final_answer: str
    raw_events: list[dict[str, Any]]
    exit_code: int
    duration_ms: float
    stderr: str = ""
    model: str = ""
    session_id: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


def parse_stream_json(
    stdout: str,
    *,
    exit_code: int = 0,
    duration_ms: float = 0.0,
    stderr: str = "",
) -> CapturedExecution:
    """Parse Claude Code ``--output-format stream-json`` output.

    The parser deliberately uses the public block shapes (``tool_use``,
    ``tool_result``, and final ``result``) and preserves every raw event so a
    CLI format change is diagnosable rather than silently ignored.
    """
    events: list[dict[str, Any]] = []
    calls: list[CapturedToolCall] = []
    calls_by_id: dict[str, CapturedToolCall] = {}
    assistant_text: list[str] = []
    final_answer = ""
    model = ""
    session_id = ""
    usage: dict[str, Any] = {}

    for line_number, line in enumerate(stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AgentTargetError(
                f"Claude emitted non-JSON output on line {line_number}: {line[:160]!r}"
            ) from exc
        if not isinstance(event, dict):
            raise AgentTargetError(
                f"Claude event on line {line_number} is not an object"
            )
        events.append(event)
        event_type = event.get("type")
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        if isinstance(message.get("model"), str):
            model = message["model"]
        content = message.get("content") if isinstance(message.get("content"), list) else []

        if event_type == "assistant":
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    call = CapturedToolCall(
                        id=str(block.get("id", "")),
                        name=str(block.get("name", "")),
                        args=(
                            dict(block["input"])
                            if isinstance(block.get("input"), dict)
                            else {}
                        ),
                    )
                    calls.append(call)
                    if call.id:
                        calls_by_id[call.id] = call
                elif block.get("type") == "text" and isinstance(block.get("text"), str):
                    assistant_text.append(block["text"])

        if event_type == "user":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                call = calls_by_id.get(str(block.get("tool_use_id", "")))
                if call is not None:
                    call.result = _decode_jsonish(block.get("content"))
                    call.is_error = bool(block.get("is_error", False))

        if event_type == "result":
            if isinstance(event.get("result"), str):
                final_answer = event["result"]
            if isinstance(event.get("session_id"), str):
                session_id = event["session_id"]
            if isinstance(event.get("usage"), dict):
                usage = dict(event["usage"])

    if not final_answer:
        final_answer = "\n".join(text for text in assistant_text if text.strip()).strip()
    return CapturedExecution(
        tool_calls=calls,
        final_answer=final_answer,
        raw_events=events,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stderr=stderr,
        model=model,
        session_id=session_id,
        usage=usage,
    )


@dataclass(frozen=True)
class ClaudeTargetConfig:
    claude_bin: str
    plugin_dir: Path
    mcp_config: Path
    cwd: Path
    timeout_seconds: int = 300
    model: str | None = None
    effort: str | None = None


class ClaudeCodeSkillTarget:
    """Fresh-process executor for the actual packaged skill."""

    _MCP_TOOLS = (
        "mcp__plugin_sdp-context_ks__kb_search",
        "mcp__plugin_sdp-context_ks__kb_fetch",
        "mcp__plugin_sdp-context_ks__kb_related",
        "mcp__ks__kb_search",
        "mcp__ks__kb_fetch",
        "mcp__ks__kb_related",
    )
    _DENIED_TOOLS = ("Bash", "Read", "Write", "Edit", "Grep", "Glob", "WebFetch", "WebSearch")

    def __init__(self, config: ClaudeTargetConfig) -> None:
        self.config = config

    def execute(self, case: dict) -> CapturedExecution:
        domain_prefix = "" if case["domain"] == "both" else f"domain {case['domain']}: "
        prompt = f"/okf-knowledge {domain_prefix}{case['query']}"
        allowed = ",".join(("Skill", *self._MCP_TOOLS))
        command = [
            self.config.claude_bin,
            "-p",
            prompt,
            "--plugin-dir",
            str(self.config.plugin_dir),
            "--mcp-config",
            str(self.config.mcp_config),
            "--strict-mcp-config",
            "--allowedTools",
            allowed,
            "--disallowedTools",
            ",".join(self._DENIED_TOOLS),
            "--permission-mode",
            "dontAsk",
            "--permission-prompts",
            "none",
            "--output-format",
            "stream-json",
            "--verbose",
            "--forward-subagent-text",
            "--no-session-persistence",
        ]
        if self.config.model:
            command.extend(("--model", self.config.model))
        if self.config.effort:
            command.extend(("--effort", self.config.effort))

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=self.config.cwd,
                text=True,
                capture_output=True,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AgentTargetError(
                f"Claude executable not found: {self.config.claude_bin}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AgentTargetError(
                f"Claude agent timed out after {self.config.timeout_seconds}s"
            ) from exc
        duration_ms = (time.perf_counter() - started) * 1000
        return parse_stream_json(
            completed.stdout,
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            stderr=completed.stderr,
        )


def _walk_entities(value: Any) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(value, dict):
        entity = value.get("entity")
        if (
            isinstance(entity, dict)
            and isinstance(entity.get("label"), str)
            and isinstance(entity.get("key"), str)
        ):
            found.append({"label": entity["label"], "key": entity["key"]})
        for child in value.values():
            found.extend(_walk_entities(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_entities(child))
    return found


def entities_from_execution(execution: CapturedExecution) -> list[str]:
    identities: list[str] = []
    for call in execution.tool_calls:
        for entity in _walk_entities(call.result):
            identity = f"{entity['label']}/{entity['key']}"
            if identity not in identities:
                identities.append(identity)
    return identities


def response_from_answer(answer: str) -> AgentResponse | dict[str, Any]:
    """Parse the deployed skill's stable Coverage/Sources footer."""
    if not answer.strip():
        # Preserve this as a contract failure in the normal answer pipeline rather
        # than raising here and hiding the command's exit/stderr evidence.
        return {"status": "answered", "answer": answer, "citations": []}
    source_lines: list[str] = []
    in_sources = False
    for line in answer.splitlines():
        if line.strip().casefold() == "sources:":
            in_sources = True
            continue
        if in_sources:
            if line.strip() and not line.lstrip().startswith(("-", "*")):
                break
            source_lines.append(line)
    citations: list[Citation] = []
    seen: set[str] = set()
    for match in ENTITY_REFERENCE.finditer("\n".join(source_lines)):
        citation = Citation(label=match.group(1), key=match.group(2).rstrip(".:"))
        if citation.ref not in seen:
            citations.append(citation)
            seen.add(citation.ref)
    # A useful answer can legitimately say that one *field* is "not recorded"
    # (for example, line coverage or team membership). An explicit opening refusal
    # remains a refusal even if the answer cites irrelevant comparison evidence.
    explicit_refusal = bool(EXPLICIT_REFUSAL.search(answer))
    return AgentResponse(
        status=(
            "insufficient_context"
            if explicit_refusal
            or (not citations and INSUFFICIENT_CONTEXT.search(answer))
            else "answered"
        ),
        answer=answer,
        citations=citations,
    )


def _argument_matches(actual: Any, operator: str, expected: Any) -> bool:
    if operator.endswith("_contains"):
        if isinstance(actual, list) and isinstance(expected, list):
            return all(item in actual for item in expected)
        if isinstance(actual, str) and isinstance(expected, str):
            return expected.casefold() in actual.casefold()
        return False
    if operator.endswith("_at_least"):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and actual >= expected
        )
    return actual == expected


def _call_matches(call: CapturedToolCall, expected: dict[str, Any]) -> bool:
    if call.tool != canonical_tool_name(expected["tool"]):
        return False
    for authored_name, expected_value in expected.get("args", {}).items():
        if authored_name.endswith("_contains"):
            actual_name = authored_name.removesuffix("_contains")
        elif authored_name.endswith("_at_least"):
            actual_name = authored_name.removesuffix("_at_least")
        else:
            actual_name = authored_name
        if not _argument_matches(
            call.args.get(actual_name), authored_name, expected_value
        ):
            return False
    return True


def check_tool_expectations(case: dict, execution: CapturedExecution) -> list[str]:
    spec = case.get("expect_tool_calls", {})
    failures: list[str] = []
    unused = set(range(len(execution.tool_calls)))
    for expected in spec.get("required", []):
        match = next(
            (
                index
                for index in sorted(unused)
                if _call_matches(execution.tool_calls[index], expected)
            ),
            None,
        )
        if match is None:
            failures.append(f"required tool call not observed: {expected}")
        else:
            unused.remove(match)

    forbidden = {
        canonical_tool_name(name) for name in spec.get("forbidden_tools", [])
    }
    used_forbidden = sorted(
        {call.tool for call in execution.tool_calls if call.tool in forbidden}
    )
    if used_forbidden:
        failures.append(f"forbidden tool(s) used: {used_forbidden}")

    retrieval_calls = [call for call in execution.tool_calls if call.tool.startswith("kb_")]
    max_calls = spec.get("max_calls")
    if max_calls is not None and len(retrieval_calls) > max_calls:
        failures.append(
            f"retrieval call count {len(retrieval_calls)} exceeds maximum {max_calls}"
        )
    failed_calls = [call.tool for call in retrieval_calls if call.is_error]
    if failed_calls:
        failures.append(f"retrieval tool call(s) failed: {failed_calls}")
    return failures


@dataclass
class AgentCaseOutcome:
    evidence: CapturedExecution
    retrieval_result: dict[str, Any]
    agent_run: AgentRun
    failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures and self.agent_run.deterministic_passed


def evaluate_agent_case(case: dict, execution: CapturedExecution) -> AgentCaseOutcome:
    failures: list[str] = []
    if execution.exit_code != 0:
        failures.append(
            f"Claude exited with {execution.exit_code}: {execution.stderr.strip()}"
        )
    if not execution.final_answer.strip():
        failures.append("Claude produced no final answer")
    failures.extend(check_tool_expectations(case, execution))

    retrieved = entities_from_execution(execution)
    expected = case.get("expect", {}) or {}
    missing = sorted(set(expected.get("required_entities", [])) - set(retrieved))
    if missing:
        failures.append(f"required entities were not retrieved: {missing}")
    forbidden = sorted(set(expected.get("must_not_return", [])) & set(retrieved))
    if forbidden:
        failures.append(f"forbidden entities were retrieved: {forbidden}")

    trace_results = [
        {"entity": identity}
        for identity in retrieved
    ]
    retrieval_result = {
        "id": case["id"],
        "latency_ms": execution.duration_ms,
        "checks": [],
        "invariant_failures": list(failures),
        "passed": not failures,
        "trace": {
            "query": case["query"],
            "domain": case["domain"],
            "persona": case["persona"],
            "tool_call": execution.tool_calls[0].as_dict() if execution.tool_calls else None,
            "tool_calls": [call.as_dict() for call in execution.tool_calls],
            "calls": len(execution.tool_calls),
            "results": trace_results,
            "rendered": json.dumps(
                [call.as_dict() for call in execution.tool_calls],
                indent=2,
                default=str,
                sort_keys=True,
            ),
        },
    }
    response = response_from_answer(execution.final_answer)
    agent_run = evaluate_agent_response(
        case=case,
        retrieval_result=retrieval_result,
        response=response,
    )
    failures.extend(
        check.detail for check in agent_run.checks if check.status == "fail"
    )
    return AgentCaseOutcome(
        evidence=execution,
        retrieval_result=retrieval_result,
        agent_run=agent_run,
        failures=failures,
    )

"""Offline self-tests for the deployed-agent evaluator."""

from __future__ import annotations

import json

import pytest

from harness.agent.models import AgentResponse, Citation
from harness.agent.claude_target import (
    CapturedExecution,
    CapturedToolCall,
    check_tool_expectations,
    entities_from_execution,
    parse_stream_json,
    response_from_answer,
)
from harness.validators.answer import check_footer_format, check_forbidden_phrases

pytestmark = pytest.mark.framework


def _line(payload: dict) -> str:
    return json.dumps(payload)


def test_stream_parser_captures_tool_result_and_final_answer() -> None:
    stdout = "\n".join(
        [
            _line(
                {
                    "type": "assistant",
                    "message": {
                        "model": "pinned-model",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call-1",
                                "name": "mcp__ks__kb_search",
                                "input": {"domain": "sdp", "query": "scorebord", "limit": 20},
                            }
                        ],
                    },
                }
            ),
            _line(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "call-1",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": json.dumps(
                                            {
                                                "result": [
                                                    {
                                                        "entity": {
                                                            "label": "Service",
                                                            "key": "scoreboard",
                                                        }
                                                    }
                                                ]
                                            }
                                        ),
                                    }
                                ],
                            }
                        ]
                    },
                }
            ),
            _line(
                {
                    "type": "result",
                    "result": "Owner found.\n\nCoverage: sdp.\n\nSources:\n- Service/scoreboard — catalog:scoreboard",
                    "session_id": "session-1",
                    "usage": {"input_tokens": 10},
                }
            ),
        ]
    )

    execution = parse_stream_json(stdout, duration_ms=12.5)

    assert execution.model == "pinned-model"
    assert execution.session_id == "session-1"
    assert execution.tool_calls[0].tool == "kb_search"
    assert execution.tool_calls[0].result["result"][0]["entity"]["key"] == "scoreboard"
    assert entities_from_execution(execution) == ["Service/scoreboard"]
    assert execution.final_answer.startswith("Owner found")


def test_tool_expectations_support_subset_contains_and_minimum() -> None:
    execution = CapturedExecution(
        tool_calls=[
            CapturedToolCall(
                id="1",
                name="mcp__plugin_sdp-context_ks__kb_related",
                args={
                    "domain": "sdp",
                    "relationships": ["OWNS", "MEMBER_OF"],
                    "depth": 2,
                },
                result={"result": []},
            )
        ],
        final_answer="answer",
        raw_events=[],
        exit_code=0,
        duration_ms=1,
    )
    case = {
        "expect_tool_calls": {
            "required": [
                {
                    "tool": "kb_related",
                    "args": {
                        "domain": "sdp",
                        "relationships_contains": ["OWNS"],
                        "depth_at_least": 2,
                    },
                }
            ],
            "max_calls": 1,
        }
    }

    assert check_tool_expectations(case, execution) == []


def test_related_root_is_retrieved_only_when_the_graph_returns_a_relationship() -> None:
    execution = CapturedExecution(
        tool_calls=[
            CapturedToolCall(
                id="1",
                name="mcp__ks__kb_related",
                args={"label": "Repository", "key": "example/app"},
                result={
                    "result": [
                        {"entity": {"label": "Service", "key": "app"}}
                    ]
                },
            ),
            CapturedToolCall(
                id="2",
                name="mcp__ks__kb_related",
                args={"label": "Repository", "key": "missing"},
                result={"result": []},
            ),
        ],
        final_answer="answer",
        raw_events=[],
        exit_code=0,
        duration_ms=1,
    )

    assert entities_from_execution(execution) == [
        "Service/app",
        "Repository/example/app",
    ]


def test_answer_parser_only_treats_sources_footer_as_citations() -> None:
    answer = (
        "Story/WRONG is mentioned as prose.\n\n"
        "Coverage: both domains searched.\n\n"
        "Sources:\n"
        "- Team/dim-platin — catalog:dim-platin\n"
        "- Service/scoreboard — catalog:scoreboard"
    )

    response = response_from_answer(answer)

    assert response.status == "answered"
    assert [citation.ref for citation in response.citations] == [
        "Team/dim-platin",
        "Service/scoreboard",
    ]

    # Citation extraction is deliberately tolerant so a malformed footer produces
    # one precise footer-contract failure instead of cascading citation failures.
    bold_footer = response_from_answer(
        "Coverage: sdp.\n\n**Sources:**\n"
        "- Team/dim-platin — catalog:dim-platin"
    )
    assert [citation.ref for citation in bold_footer.citations] == ["Team/dim-platin"]


def test_answer_parser_recognises_honest_refusal() -> None:
    response = response_from_answer(
        "The on-call rotation is not recorded.\n\nCoverage: both domains searched.\n\nSources:"
    )

    assert response.status == "insufficient_context"
    assert response.citations == []

    equivalent_refusal = response_from_answer(
        "No on-call rotation is recorded for the portal.\n\n"
        "Coverage: sdp and paastry searched.\n\nSources:\n"
        "- DocChunk/comparison#0 — docs:comparison#0"
    )
    assert equivalent_refusal.status == "insufficient_context"
    assert [citation.ref for citation in equivalent_refusal.citations] == [
        "DocChunk/comparison#0"
    ]

    cited_comparison = response_from_answer(
        "**Not recorded.** No portal rotation was found.\n\n"
        "Coverage: sdp and paastry searched.\n\n"
        "Sources:\n- DocChunk/demo-runbook#0 — docs:demo-runbook#0"
    )
    assert cited_comparison.status == "insufficient_context"
    assert [citation.ref for citation in cited_comparison.citations] == [
        "DocChunk/demo-runbook#0"
    ]

    domain_scoped = response_from_answer(
        "## On-call rotation for the portal\n\n"
        "**`sdp` (the real portal):** not recorded.\n\n"
        "Coverage: sdp; paastry searched.\n\n"
        "Sources:\n- DocChunk/demo-runbook#0 — docs:demo-runbook#0"
    )
    assert domain_scoped.status == "insufficient_context"


def test_answer_parser_does_not_confuse_a_coverage_gap_with_refusal() -> None:
    response = response_from_answer(
        "Team/dim-platin owns it. Team membership is not recorded.\n\n"
        "Coverage: sdp.\n\n"
        "Sources:\n- Team/dim-platin — catalog:dim-platin"
    )

    assert response.status == "answered"
    assert [citation.ref for citation in response.citations] == ["Team/dim-platin"]


def test_footer_format_requires_plain_headers_and_stable_source_bullets() -> None:
    valid = AgentResponse(
        status="answered",
        answer=(
            "Team dim-platin owns scoreboard.\n\n"
            "Coverage: sdp.\n\n"
            "Sources:\n"
            "- Team/dim-platin — catalog:dim-platin, jira:dim-platin (unverified)"
        ),
        citations=[Citation(label="Team", key="dim-platin")],
    )
    assert check_footer_format(valid) is None

    bold_headers = valid.model_copy(
        update={
            "answer": (
                "Team dim-platin owns scoreboard.\n\n"
                "**Coverage:** sdp.\n\n"
                "**Sources:**\n"
                "- Team/dim-platin — catalog:dim-platin"
            )
        }
    )
    assert "unformatted line beginning 'Coverage:'" in check_footer_format(bold_headers)

    malformed_source = valid.model_copy(
        update={
            "answer": (
                "Team dim-platin owns scoreboard.\n\n"
                "Coverage: sdp.\n\n"
                "Sources:\n"
                "- Team/dim-platin — source_system: catalog"
            )
        }
    )
    assert "source_system:reference" in check_footer_format(malformed_source)

    refusal = AgentResponse(
        status="insufficient_context",
        answer="Not recorded.\n\nCoverage: sdp and paastry searched.\n\nSources:",
        citations=[],
    )
    assert check_footer_format(refusal) is None

    relationship_only = valid.model_copy(
        update={
            "answer": (
                "The commit belongs to the repository.\n\n"
                "Coverage: sdp.\n\n"
                "Sources:\n"
                "- Repository/example/app — "
                "(via IN_REPOSITORY relationship, incoming, distance 2, "
                "through Team/dim-platin)"
            ),
            "citations": [Citation(label="Repository", key="example/app")],
        }
    )
    assert check_footer_format(relationship_only) is None

    trailing_relationship_qualifiers = relationship_only.model_copy(
        update={
            "answer": (
                "The backend is impacted.\n\n"
                "Coverage: sdp.\n\n"
                "Sources:\n"
                "- Service/backend — (via DEPENDS_ON relationship) incoming, "
                "distance 1 from Feature/scoreboard-backend"
            ),
            "citations": [Citation(label="Service", key="backend")],
        }
    )
    assert check_footer_format(trailing_relationship_qualifiers) is None


def test_forbidden_phrases_are_checked_case_insensitively() -> None:
    response = AgentResponse(
        status="answered",
        answer=(
            "The service ROTATES WEEKLY.\n\n"
            "Coverage: paastry.\n\nSources:"
        ),
        citations=[],
    )

    detail = check_forbidden_phrases(response, ["rotates weekly", "rotates daily"])

    assert detail == "answer contains forbidden phrase(s): ['rotates weekly']"

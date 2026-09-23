"""Offline self-tests for the deployed-agent evaluator."""

from __future__ import annotations

import json

import pytest

from harness.agent.claude_target import (
    CapturedExecution,
    CapturedToolCall,
    check_tool_expectations,
    entities_from_execution,
    parse_stream_json,
    response_from_answer,
)

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


def test_answer_parser_recognises_honest_refusal() -> None:
    response = response_from_answer(
        "The on-call rotation is not recorded.\n\nCoverage: both domains searched.\n\nSources:"
    )

    assert response.status == "insufficient_context"
    assert response.citations == []

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

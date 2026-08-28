"""Deterministic validation of a captured final agent response."""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, ValidationError

from harness.agent.models import AgentResponse, Citation


def _payload(response: Any) -> Any:
    return response.model_dump() if isinstance(response, BaseModel) else response


def validate_agent_response_contract(
    response: Any,
) -> tuple[AgentResponse | None, str | None]:
    try:
        parsed = AgentResponse.model_validate(_payload(response), strict=True)
    except ValidationError as exc:
        return None, f"agent response does not match the published contract: {exc}"
    return parsed, None


def check_citations_were_retrieved(
    response: AgentResponse, retrieval_result: dict
) -> str | None:
    retrieved = {
        result["entity"]
        for result in retrieval_result.get("trace", {}).get("results", [])
    }
    unavailable = sorted(
        citation.ref for citation in response.citations if citation.ref not in retrieved
    )
    if unavailable:
        return f"answer cites entities that were not retrieved: {unavailable}"
    return None


def check_required_citations(
    response: AgentResponse, required: Iterable[Citation]
) -> str | None:
    actual = {citation.ref for citation in response.citations}
    missing = sorted(citation.ref for citation in required if citation.ref not in actual)
    if missing:
        return f"answer is missing required citations: {missing}"
    return None


def check_must_not_cite(
    response: AgentResponse, forbidden: Iterable[Citation]
) -> str | None:
    actual = {citation.ref for citation in response.citations}
    leaked = sorted(citation.ref for citation in forbidden if citation.ref in actual)
    if leaked:
        return f"answer cites forbidden note versions: {leaked}"
    return None


def check_expected_answer_status(
    response: AgentResponse, expected: str
) -> str | None:
    if response.status == expected:
        return None
    return f"unexpected answer status: expected {expected}, got {response.status}"

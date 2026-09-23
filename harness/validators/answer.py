"""Deterministic validation of a captured final agent response."""

from __future__ import annotations

import re
from typing import Any, Iterable

from pydantic import BaseModel, ValidationError

from harness.agent.models import AgentResponse, Citation


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
SOURCE_REFERENCE = r"[a-z][a-z0-9_-]*:[^\s,()]+"
SOURCE_ANNOTATION = r"(?: \([^()\n]+\))*"
# Graph tools return a fixed relationship name but agents render the associated
# direction/distance/path metadata in more than one equivalent order (for example
# "distance 1 from Feature/x" or "distance 2, through Team/y"). The footer
# contract deliberately validates the stable evidence boundary, not punctuation in
# those display-only qualifiers.
RELATIONSHIP_PROVENANCE = (
    r"\(via [A-Z][A-Z_]* relationship(?:,[^()\n]*)?\)(?:[ ,][^()\n]+)?"
)
SOURCE_BULLET = re.compile(
    rf"^- (?:{'|'.join(ENTITY_LABELS)})/\S+ — "
    rf"(?:{SOURCE_REFERENCE}(?:, {SOURCE_REFERENCE})*{SOURCE_ANNOTATION}"
    rf"|{RELATIONSHIP_PROVENANCE})$"
)


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


def check_required_phrases(
    response: AgentResponse, required: Iterable[str]
) -> str | None:
    answer = response.answer.casefold()
    missing = sorted(phrase for phrase in required if phrase.casefold() not in answer)
    if missing:
        return f"answer is missing required phrase(s): {missing}"
    return None


def check_forbidden_phrases(
    response: AgentResponse, forbidden: Iterable[str]
) -> str | None:
    answer = response.answer.casefold()
    present = sorted(phrase for phrase in forbidden if phrase.casefold() in answer)
    if present:
        return f"answer contains forbidden phrase(s): {present}"
    return None


def check_footer_format(response: AgentResponse) -> str | None:
    """Validate the deployed skill's exact, machine-readable answer footer."""
    lines = response.answer.rstrip().splitlines()
    coverage_indices = [
        index for index, line in enumerate(lines) if line.startswith("Coverage:")
    ]
    if len(coverage_indices) != 1:
        return (
            "answer must contain exactly one unformatted line beginning "
            "'Coverage:'"
        )
    coverage_index = coverage_indices[0]
    if not lines[coverage_index].removeprefix("Coverage:").strip():
        return "the 'Coverage:' line must describe the searched corpus or gaps"

    sources_indices = [
        index for index, line in enumerate(lines) if line == "Sources:"
    ]
    if len(sources_indices) != 1:
        return "answer must contain exactly one unformatted 'Sources:' line"
    sources_index = sources_indices[0]
    if coverage_index >= sources_index:
        return "the 'Coverage:' line must appear before the final 'Sources:' section"

    source_lines = [line for line in lines[sources_index + 1 :] if line.strip()]
    malformed = [line for line in source_lines if not SOURCE_BULLET.fullmatch(line)]
    if malformed:
        return (
            "every non-empty line after 'Sources:' must use "
            "'- Label/key — source_system:reference' with optional additional "
            "comma-separated source pairs and parenthetical annotation(s); "
            "a related entity without citation metadata may use "
            "'- Label/key — (via RELATIONSHIP relationship)'; "
            "malformed line(s): "
            f"{malformed}"
        )
    if response.citations and not source_lines:
        return "an answered response with citations must list source bullets"
    return None

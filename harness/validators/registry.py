"""Traceability metadata for deterministic deployed-answer checks."""

from __future__ import annotations

ANSWER_CHECKS: dict[str, dict[str, str]] = {
    "answer:response_contract_valid": {
        "status": "traced",
        "source": "deployed evaluator AgentResponse contract",
    },
    "answer:citations_were_retrieved": {
        "status": "traced",
        "source": "okf-knowledge evidence-only and citation rules",
    },
    "answer:required_citations": {
        "status": "traced",
        "source": "case-specific deployed answer expectation",
    },
    "answer:must_not_cite": {
        "status": "traced",
        "source": "case-specific deployed answer safety expectation",
    },
    "answer:expected_status": {
        "status": "traced",
        "source": "case-specific deployed answer status expectation",
    },
    "answer:required_phrases": {
        "status": "traced",
        "source": "case-specific deployed answer content expectation",
    },
    "answer:forbidden_phrases": {
        "status": "traced",
        "source": "case-specific deployed answer safety expectation",
    },
    "answer:footer_format": {
        "status": "traced",
        "source": "okf-knowledge stable answer format",
    },
}

CHECKS = ANSWER_CHECKS


def describe(name: str) -> dict[str, str]:
    return CHECKS.get(
        name,
        {
            "status": "UNTRACEABLE",
            "source": "missing from harness/validators/registry.py",
        },
    )

"""Traceability registry for every deterministic validator the runner can enforce.

Each check records where its requirement comes from. A check missing from this
registry is a defect: correctness rules must not become build gates merely because
someone typed them into the runner.
"""

from __future__ import annotations

CHECKS: dict[str, dict[str, str]] = {
    "contract:emitted_tool_call": {
        "declared_by": "case request fields; optional expect_tool_call override",
        "status": "traced",
        "source": "mcp-tool-contracts-reference.md §2.1, kb_search argument shape",
        "rationale": (
            "A dropped or renamed argument (domain, query, limit) breaks domain "
            "isolation or intent silently, and no ranking metric detects it. The "
            "emitted call is the only place it is visible."
        ),
    },
    "contract:server_rejects_invalid_request": {
        "declared_by": "probe_invalid_request + --transport mcp|rest",
        "status": "traced",
        "source": "mcp-tool-contracts-reference.md, extra=forbid enforcement is "
                  "server side, clients are never trusted",
        "rationale": (
            "A client-side check can be bypassed. The server must reject invalid "
            "input at the trust boundary for every caller."
        ),
    },
    "contract:response_contract_valid": {
        "declared_by": "every retrieval execution",
        "status": "traced",
        "source": "mcp-tool-contracts-reference.md §2.1, SearchHit response shape",
        "rationale": (
            "A successful protocol call is not enough: renamed, missing, or wrongly "
            "typed output fields make the response unusable to the skill."
        ),
    },
    "retrieval:must_not_return": {
        "declared_by": "expect.must_not_return",
        "status": "traced",
        "source": "mcp-tool-contracts-reference.md Gotcha 1 and 2, ranking correctness",
        "rationale": (
            "A superseded, reverted, or out-of-domain entity reaching a caller is a "
            "defect regardless of rank, not a lower score."
        ),
    },
    "retrieval:expected_first_result": {
        "declared_by": "expect.expected_first_result",
        "status": "traced",
        "source": "mcp-tool-contracts-reference.md Gotcha 2, exact identifiers can "
                  "rank below doc chunks",
        "rationale": (
            "A lexical-overlap-only system can rank a superseded or reverted entity "
            "above the authoritative one. Full precedence over lexical overlap is a "
            "kb_related concern (deferred); this check covers basic ranking "
            "correctness for kb_search alone."
        ),
    },
    "format:every_result_has_provenance": {
        "declared_by": "every retrieval execution",
        "status": "traced",
        "source": "mcp-tool-contracts-reference.md Gotcha 5, cite everything",
        "rationale": (
            "Both the entity identity and at least one citation must survive "
            "rendering so every agent-visible result can be resolved and audited."
        ),
    },
}

ANSWER_CHECKS: dict[str, dict[str, str]] = {
    "answer:response_contract_valid": {
        "declared_by": "every captured agent response",
        "status": "unratified",
        "source": "provisional contract in harness/agent/models.py; approval pending",
        "rationale": (
            "Semantic judging cannot repair a missing, extra, wrongly typed, or blank "
            "answer field."
        ),
    },
    "answer:citations_were_retrieved": {
        "declared_by": "every valid captured agent response",
        "status": "traced",
        "source": "Component Guide 4.3 and 11, provenance is pinned and carried forward",
        "rationale": (
            "A citation must resolve to the exact note version that was actually "
            "available to the agent."
        ),
    },
    "answer:required_citations": {
        "declared_by": "case answer_evaluation.expect.required_citations",
        "status": "unratified",
        "source": "case-specific answer expectation; review pending",
        "rationale": (
            "Where an authoritative citation is an exact requirement, checking its "
            "identity is more reliable than asking a model."
        ),
    },
    "answer:must_not_cite": {
        "declared_by": "case answer_evaluation.expect.must_not_cite",
        "status": "unratified",
        "source": "case-specific safety and provenance expectation; review pending",
        "rationale": (
            "Forbidden or superseded knowledge in a final answer is a deterministic "
            "defect regardless of semantic quality."
        ),
    },
    "answer:expected_status": {
        "declared_by": "case answer_evaluation.expect.status",
        "status": "unratified",
        "source": "case-specific answer status expectation; review pending",
        "rationale": (
            "An explicit structured status can be compared exactly; no model is "
            "needed to infer it from prose."
        ),
    },
}

CHECKS.update(ANSWER_CHECKS)

ALWAYS_APPLICABLE = frozenset(
    {
        "contract:emitted_tool_call",
        "contract:response_contract_valid",
        "format:every_result_has_provenance",
    }
)


def applies_to(name: str, case: dict) -> bool:
    """Whether a validator has enough independent expected data for this case."""
    if name in ANSWER_CHECKS:
        return False
    if name in ALWAYS_APPLICABLE:
        return True
    if name == "contract:server_rejects_invalid_request":
        return "probe_invalid_request" in case
    expect = case.get("expect", {}) or {}
    if name == "retrieval:must_not_return":
        return "must_not_return" in expect
    if name == "retrieval:expected_first_result":
        return "expected_first_result" in expect
    return False


def describe(name: str) -> dict[str, str]:
    """Return registry metadata; an unknown check is explicitly untraceable."""
    return CHECKS.get(
        name,
        {
            "status": "UNTRACEABLE",
            "source": "MISSING from harness/validators/registry.py",
            "rationale": "",
        },
    )


def render_inventory(markdown: bool = False) -> str:
    """Render the check contract without executing any cases."""
    mark = {"traced": "traced", "inferred": "inferred", "unratified": "UNRATIFIED"}
    rows = sorted(CHECKS.items(), key=lambda kv: (kv[1]["status"] != "unratified", kv[0]))
    if markdown:
        out = [
            "| Check | Declared by | Traceability | Source |",
            "| --- | --- | --- | --- |",
        ]
        out += [
            f"| `{n}` | `{m['declared_by']}` | {mark[m['status']]} | {m['source']} |"
            for n, m in rows
        ]
        return "\n".join(out)

    out = [f"{len(CHECKS)} checks.\n"]
    for name, meta in rows:
        out.append(name)
        out.append(f"    declared by  : {meta['declared_by']}")
        out.append(f"    traceability : {mark[meta['status']]}")
        out.append(f"    source       : {meta['source']}")
        out.append(f"    rationale    : {meta['rationale']}")
        out.append("")
    return "\n".join(out)

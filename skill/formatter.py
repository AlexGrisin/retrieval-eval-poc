"""The output contract.

Output properties this rendering currently holds. The POC gates only
provenance (item 1); the others remain implementation conventions until
requirements justify making them build gates:
  1. Every result carries its entity identity AND its citations.
  2. Field order is fixed, so a diff of two runs is readable.
  3. Snippet text is rendered as quoted data, never in a position an agent
     could read as an instruction.
  4. The empty result has an explicit rendering, not an absent section.
"""

from __future__ import annotations

from .contracts import SearchRequest, SearchResponse

EMPTY_RENDERING = "### Knowledge — no entities matched\ndomain {domain}\n"


def render(request: SearchRequest, response: SearchResponse) -> str:
    if not response.results:
        return EMPTY_RENDERING.format(domain=request.domain)

    n = len(response.results)
    header = f"### Knowledge — {n} entit{'ies' if n != 1 else 'y'} · domain {request.domain}"
    lines = [header]
    for i, hit in enumerate(response.results, 1):
        lines.append(f"{i}. {hit.title}   [{hit.entity.identity} · {hit.matched_by}]")
        # Quoted: the agent reads this as data, not as instruction.
        lines.append(f'   > "{hit.snippet}"')
        refs = ", ".join(f"{c.source_system}:{c.reference}" for c in hit.citations)
        lines.append(f"   citations: {refs or '(none)'}")
    return "\n".join(lines) + "\n"

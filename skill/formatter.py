"""The output contract.

Output properties this rendering currently holds. The POC gates only provenance
(item 1); the others remain implementation conventions until requirements justify
making them build gates:
  1. Every result carries note@version AND source@version.
  2. Field order is fixed, so a diff of two runs is readable.
  3. Note text is rendered as quoted data, never in a position an agent could
     read as an instruction.
  4. The empty result has an explicit rendering, not an absent section.
"""

from __future__ import annotations

from .contracts import RetrieveRequest, RetrieveResponse

EMPTY_RENDERING = "### Knowledge — no notes matched\nscope {scope} · filters {filters}\n"


def _filters_repr(request: RetrieveRequest) -> str:
    # Lists are rendered comma-joined, never as a Python list literal -- found by
    # eyeballing probe output, which is exactly what manual testing is for.
    def val(v: object) -> str:
        return ",".join(str(x) for x in v) if isinstance(v, list) else str(v)

    return " ".join(f"{k}={val(v)}" for k, v in sorted(request.filters.as_dict().items()))


def _scope_repr(request: RetrieveRequest) -> str:
    s = request.scope
    return f"{s.department}/{s.product}" if s.product else s.department


def render(request: RetrieveRequest, response: RetrieveResponse) -> str:
    scope, filters = _scope_repr(request), _filters_repr(request)
    if not response.results:
        return EMPTY_RENDERING.format(scope=scope, filters=filters)

    if request.format == "citations_only":
        lines = [f"### Knowledge — {len(response.results)} citations · scope {scope}"]
        lines += [
            f"{i}. {r.note_ref} · {r.source_ref}"
            for i, r in enumerate(response.results, 1)
        ]
        return "\n".join(lines) + "\n"

    n = len(response.results)
    header = (
        f"### Knowledge — {n} note{'s' if n != 1 else ''} · "
        f"scope {scope} · filters {filters}"
    )
    lines = [header]
    for i, r in enumerate(response.results, 1):
        validity = f" · valid to {r.valid_to}" if r.valid_to else ""
        lines.append(f"{i}. {r.title}   [{r.veracity}{validity}]")
        if request.format == "full":
            # Quoted: the agent reads this as data, not as instruction.
            lines.append(f'   > "{r.claim}"')
        lines.append(f"   note {r.note_ref} · source {r.source_ref}")
    facet_bits = " · ".join(
        f"{name}{{{', '.join(f'{k}:{v}' for k, v in sorted(counts.items()))}}}"
        for name, counts in sorted(response.facets.items())
        if counts
    )
    if facet_bits:
        lines.append(f"Facets: {facet_bits}")
    return "\n".join(lines) + "\n"

"""Deterministic validation of context rendered for the consuming agent."""

from __future__ import annotations

from collections.abc import Iterable


def check_every_result_has_provenance(
    rendered: str, results: Iterable
) -> str | None:
    """Require both entity identity and at least one citation for every hit."""
    results = list(results)
    missing_identity = [
        hit.entity.identity for hit in results if hit.entity.identity not in rendered
    ]
    missing_citations = [hit.entity.identity for hit in results if not hit.citations]
    failures = []
    if missing_identity:
        failures.append(f"entity identity missing from rendered output: {missing_identity}")
    if missing_citations:
        failures.append(f"no citations for {missing_citations}")
    return "; ".join(failures) or None

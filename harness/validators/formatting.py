"""Deterministic validation of context rendered for the consuming agent."""

from __future__ import annotations

from collections.abc import Iterable


def check_every_result_has_provenance(
    rendered: str, results: Iterable
) -> str | None:
    """Require both note and original-source references in rendered context."""
    results = list(results)
    missing_note = [
        r.note_id for r in results if f"note {r.note_ref}" not in rendered
    ]
    missing_source = [
        r.note_id for r in results if f"source {r.source_ref}" not in rendered
    ]
    failures = []
    if missing_note:
        failures.append(f"note ref missing for {missing_note}")
    if missing_source:
        failures.append(f"source ref missing for {missing_source}")
    return "; ".join(failures) or None

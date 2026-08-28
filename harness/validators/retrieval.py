"""Deterministic validation over the retrieved result set."""

from __future__ import annotations

from collections.abc import Iterable


def check_must_not_return(ranked: list[str], forbidden: Iterable[str]) -> str | None:
    leaked = [note for note in forbidden if note in ranked]
    return f"must_not_return violated: {leaked}" if leaked else None


def check_expected_first_result(ranked: list[str], expected: str) -> str | None:
    if not ranked:
        return f"expected {expected} first, got nothing"
    if ranked[0] != expected:
        return f"unexpected first result: expected {expected}, got {ranked[0]}"
    return None

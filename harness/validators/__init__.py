"""Deterministic, zero-tolerance validation of executed system behavior."""

from .registry import (
    ALWAYS_APPLICABLE,
    ANSWER_CHECKS,
    CHECKS,
    applies_to,
    describe,
    render_inventory,
)

__all__ = [
    "ALWAYS_APPLICABLE",
    "ANSWER_CHECKS",
    "CHECKS",
    "applies_to",
    "describe",
    "render_inventory",
]

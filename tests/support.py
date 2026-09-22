"""Collection-time test data."""

from __future__ import annotations

from pathlib import Path

from harness.definitions.cases import load_cases as load_case_directory

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "cases"


def load_cases() -> list[dict]:
    return load_case_directory(CASES_DIR)

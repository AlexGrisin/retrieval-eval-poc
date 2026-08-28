"""Collection-time test data and supported pytest ID helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.definitions.cases import load_cases as load_case_directory

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "cases"


def load_cases() -> list[dict]:
    return load_case_directory(CASES_DIR)


def framework_id(identifier: str):
    """Give an unparametrized framework test a normal, public pytest ID."""

    def decorate(function):
        function = pytest.mark.framework(function)
        function = pytest.mark.usefixtures("_framework_id")(function)
        return pytest.mark.parametrize(
            "_framework_id",
            [pytest.param(None, id=identifier)],
            indirect=True,
        )(function)

    return decorate

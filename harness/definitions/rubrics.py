"""Definition and structural validation for LLM-as-judge rubrics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

REQUIRED_KEYS = {"name", "display_name", "type", "description", "criteria", "threshold"}


class RubricSpecError(ValueError):
    pass


def validate_rubric_spec(path: Path, spec: Any) -> dict:
    if not isinstance(spec, dict):
        raise RubricSpecError(f"{path.name} must contain a mapping")
    missing = REQUIRED_KEYS - spec.keys()
    if missing:
        raise RubricSpecError(
            f"{path.name} is missing required key(s): {sorted(missing)}"
        )
    if spec["name"] != path.stem:
        raise RubricSpecError(
            f"{path.name}: name field {spec['name']!r} does not match filename"
        )
    threshold = spec["threshold"]
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise RubricSpecError(f"{path.name}: threshold must be a number")
    if not 0 <= threshold <= 1:
        raise RubricSpecError(f"{path.name}: threshold must be between 0 and 1")
    for key in ("name", "display_name", "type", "description", "criteria"):
        if not isinstance(spec[key], str) or not spec[key].strip():
            raise RubricSpecError(f"{path.name}: {key} must be a non-empty string")
    return spec

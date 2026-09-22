"""Definition, loading, and structural validation for caller personas.

Mirrors harness/definitions/rubrics.py + harness/judges/loader.py: a spec file
per persona, name-matches-filename, one module owns both shape validation and
directory loading since no subsystem (yet) consumes personas the way judges
own rubrics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PERSONAS_DIR = Path(__file__).resolve().parents[2] / "personas"

REQUIRED_KEYS = {"id", "name", "description", "traits"}


class PersonaSpecError(ValueError):
    pass


def validate_persona_spec(path: Path, spec: Any) -> dict:
    if not isinstance(spec, dict):
        raise PersonaSpecError(f"{path.name} must contain a mapping")
    missing = REQUIRED_KEYS - spec.keys()
    if missing:
        raise PersonaSpecError(
            f"{path.name} is missing required key(s): {sorted(missing)}"
        )
    if spec["id"] != path.stem:
        raise PersonaSpecError(
            f"{path.name}: id field {spec['id']!r} does not match filename"
        )
    for key in ("id", "name", "description"):
        if not isinstance(spec[key], str) or not spec[key].strip():
            raise PersonaSpecError(f"{path.name}: {key} must be a non-empty string")
    traits = spec["traits"]
    if not isinstance(traits, list) or not traits:
        raise PersonaSpecError(f"{path.name}: traits must be a non-empty list")
    if not all(isinstance(t, str) and t.strip() for t in traits):
        raise PersonaSpecError(f"{path.name}: every trait must be a non-empty string")
    return spec


def load_personas(directory: Path = PERSONAS_DIR) -> dict[str, dict]:
    personas: dict[str, dict] = {}
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        spec = validate_persona_spec(path, yaml.safe_load(path.read_text()))
        if spec["id"] in personas:
            raise PersonaSpecError(f"duplicate persona id: {spec['id']!r}")
        personas[spec["id"]] = spec
    return personas

"""Load the answer-quality rubrics used by the opt-in LLM judge.

Nothing in this module calls a model. It owns judge-facing rubric discovery and
inventory rendering; structural validity is delegated to
``harness.definitions.rubrics``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from harness.definitions.rubrics import validate_rubric_spec

RUBRICS_DIR = Path(__file__).resolve().parents[2] / "rubrics"


def load_rubrics(directory: Path = RUBRICS_DIR) -> dict[str, dict]:
    rubrics: dict[str, dict] = {}
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        spec = validate_rubric_spec(path, yaml.safe_load(path.read_text()))
        if spec["name"] in rubrics:
            raise ValueError(f"duplicate rubric name: {spec['name']!r}")
        rubrics[spec["name"]] = spec
    return rubrics


def render_inventory() -> str:
    rubrics = load_rubrics()
    relative = RUBRICS_DIR.relative_to(RUBRICS_DIR.parent)
    lines = [f"{len(rubrics)} rubric(s) in {relative}/\n"]
    for name, spec in rubrics.items():
        lines.append(f"{name}  ({spec['type']}, threshold {spec['threshold']})")
        lines.append(f"    {spec['description'].strip()}")
        trace = spec.get("traceability", {})
        if trace:
            lines.append(
                f"    traceability: {trace.get('status', '?')} -- {trace.get('source', '')}"
            )
        lines.append("")
    shared = sorted(path.name for path in RUBRICS_DIR.glob("_*.yaml"))
    if shared:
        lines.append(f"shared/cross-cutting (not scorable on their own): {shared}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_inventory())

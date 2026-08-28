# YAML Fixture Load-and-Validate at the Boundary

## Description

Every YAML-authored input — `cases/*.yaml`, `rubrics/*.yaml`,
`fixtures/agent_responses/*.yaml`, `fixtures/corpus.yaml` — is parsed with
`yaml.safe_load` and validated exactly once, immediately after parsing.
Nothing downstream re-validates or hand-builds an equivalent dict/model
later in the pipeline; the validated structure is passed through as-is.

Validation failures are raised as a dedicated `ValueError` subclass named
after the artifact (`CaseSpecError`, `RubricSpecError`,
`AgentResponseFixtureError`), and the message always names the offending
filename — never a bare `ValueError` or a pydantic trace with no file
context.

A directory-level loader (`load_cases`, `load_rubrics`, `load_agent_responses`)
`glob("*.yaml")`s its directory, silently skips underscore-prefixed files
(shared/non-scorable fragments, e.g. a future `_shared.yaml`), and then
enforces *set-level* invariants that a single-file loader cannot: contiguous
case numbering starting at 001 (`load_cases`), no duplicate rubric `name`
(`load_rubrics`), at least one fixture present (`load_agent_responses`).

**Evidence (read directly):** `harness/definitions/cases.py`
(`validate_case`, `load_case`, `load_cases`), `harness/definitions/rubrics.py`
(`validate_rubric_spec`), `harness/definitions/agent_responses.py`
(`load_agent_response`, `load_agent_responses`), and
`skill/fake_server.py.__init__` (loads `fixtures/corpus.yaml` once at
construction).

## Template / Example

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class MyFixtureError(ValueError):
    """Named after the artifact it validates — never a bare ValueError."""


def validate_my_fixture(spec: Any, source: str) -> dict:
    if not isinstance(spec, dict):
        raise MyFixtureError(f"{source} must be a mapping")
    # EXTENSION POINT: required/allowed key checks, per-field type checks,
    # and any cross-field invariants go here — all raising MyFixtureError
    # with the filename (`source`) in the message.
    return spec


def load_my_fixture(path: Path) -> dict:
    try:
        parsed = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise MyFixtureError(f"{path.name} is not valid YAML: {exc}") from exc
    return validate_my_fixture(parsed, path.name)


def load_my_fixtures(directory: Path) -> list[dict]:
    fixtures = [
        load_my_fixture(path)
        for path in sorted(directory.glob("*.yaml"))
        if not path.name.startswith("_")  # shared/non-scorable fragments
    ]
    # EXTENSION POINT: set-level invariants across the whole directory
    # (uniqueness, contiguous numbering, "at least one") go here — a
    # single-file loader cannot see these.
    return fixtures
```

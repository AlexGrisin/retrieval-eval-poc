"""Load structured agent-response fixtures used by the POC tests."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from harness.agent.models import AgentResponse


class AgentResponseFixtureError(ValueError):
    pass


def load_agent_response(path: Path) -> AgentResponse:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AgentResponseFixtureError(f"{path.name} is not valid YAML: {exc}") from exc
    try:
        return AgentResponse.model_validate(raw, strict=True)
    except ValidationError as exc:
        raise AgentResponseFixtureError(f"{path.name} is invalid: {exc}") from exc


def load_agent_responses(directory: Path) -> dict[str, AgentResponse]:
    responses = {
        path.stem: load_agent_response(path) for path in sorted(directory.glob("*.yaml"))
    }
    if not responses:
        raise AgentResponseFixtureError(
            f"no agent-response fixtures found in {directory}"
        )
    return responses

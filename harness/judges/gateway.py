"""Gateway boundary for strict structured LLM-judge calls."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from harness.judges.models import JudgeConfig


class JudgeGatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class GatewayResponse:
    result: dict[str, Any]
    actual_model: str
    response_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class JudgeGateway(Protocol):
    def evaluate(self, prompt: str, schema: dict[str, Any]) -> GatewayResponse: ...


class OpenAIResponsesGateway:
    """Call an OpenAI Responses-compatible enterprise LLM Gateway."""

    def __init__(
        self,
        config: JudgeConfig,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport

    def _endpoint(self) -> str:
        base = self.config.gateway_url.rstrip("/")
        return base if base.endswith("/responses") else f"{base}/responses"

    @staticmethod
    def _output_text(payload: dict[str, Any]) -> str:
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]
        chunks: list[str] = []
        for item in payload.get("output", []) or []:
            for block in item.get("content", []) or []:
                if block.get("type") == "output_text" and isinstance(
                    block.get("text"), str
                ):
                    chunks.append(block["text"])
        if not chunks:
            raise JudgeGatewayError("Gateway response contains no output_text")
        return "".join(chunks)

    @staticmethod
    def _safe_error_detail(response: httpx.Response) -> str:
        """Return diagnostic fields that cannot echo credentials or prompt data."""
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return ""
        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            return ""
        parts = [
            f"{name}={error[name]}"
            for name in ("type", "code", "param")
            if isinstance(error.get(name), str) and error[name]
        ]
        return f" ({', '.join(parts)})" if parts else ""

    def evaluate(self, prompt: str, schema: dict[str, Any]) -> GatewayResponse:
        headers = {"Content-Type": "application/json"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        body = {
            "model": self.config.model_id,
            "input": prompt,
            "temperature": self.config.temperature,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "judge_result",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        try:
            with httpx.Client(
                transport=self._transport, timeout=self.config.timeout_seconds
            ) as client:
                response = client.post(self._endpoint(), headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise JudgeGatewayError(f"LLM Gateway call failed: {exc}") from exc
        if response.is_error:
            detail = self._safe_error_detail(response)
            raise JudgeGatewayError(
                f"LLM Gateway call failed: HTTP {response.status_code}{detail} "
                f"for {response.request.url}"
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise JudgeGatewayError("LLM Gateway response is not valid JSON") from exc
        try:
            result = json.loads(self._output_text(payload))
        except (json.JSONDecodeError, TypeError) as exc:
            raise JudgeGatewayError("Gateway output is not valid structured JSON") from exc
        if not isinstance(result, dict):
            raise JudgeGatewayError("Gateway structured output must be an object")
        return GatewayResponse(
            result=result,
            actual_model=str(payload.get("model") or self.config.model_id),
            response_id=payload.get("id"),
            usage=payload.get("usage") or {},
        )

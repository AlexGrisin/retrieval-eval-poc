"""The judge runner is reproducible without requiring a live model by default."""

from __future__ import annotations

import json
from pathlib import Path

import allure
import httpx
import pytest

from harness.definitions.cases import get_answer_evaluation, load_cases
from harness.judges.gateway import (
    GatewayResponse,
    JudgeGatewayError,
    OpenAIResponsesGateway,
)
from harness.judges.models import JudgeConfig
from harness.judges.prompt import PROMPT_VERSION
from harness.judges.runner import (
    DEFAULT_CACHE,
    JudgeRunError,
    run_agent_judges,
)
from tests.support import framework_id

ROOT = Path(__file__).resolve().parents[1]
CASES = load_cases(ROOT / "cases")
CASES_BY_ID = {case["id"]: case for case in CASES}


class FakeGateway:
    def __init__(self, result: dict | None = None) -> None:
        self.result = result
        self.calls = 0

    def evaluate(self, prompt: str, schema: dict) -> GatewayResponse:
        self.calls += 1
        assert "untrusted data" in prompt
        assert schema["additionalProperties"] is False
        criterion = schema["properties"]["criterion"]["enum"][0]
        result = self.result or {
            "criterion": criterion,
            "score": 1.0,
            "explanation": f"The generated answer satisfies {criterion}.",
        }
        return GatewayResponse(
            result=result,
            actual_model="judge-deployment-2026-08-01",
            response_id="resp-test",
            usage={"input_tokens": 100, "output_tokens": 20},
        )


def judge_config(**overrides) -> JudgeConfig:
    values = {
        "gateway_url": "https://gateway.example.test/v1",
        "model_id": "judge-deployment",
        "model_version": "2026-08-01",
        "prompt_version": PROMPT_VERSION,
    }
    values.update(overrides)
    return JudgeConfig(**values)


@framework_id("suite:judge:project_dotenv_precedence")
def test_project_dotenv_overrides_stale_shell_config(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_GATEWAY_URL=https://api.openai.com/v1\n"
        "LLM_GATEWAY_TOKEN=file-key\n"
        "LLM_JUDGE_MODEL=file-model\n"
        "LLM_JUDGE_MODEL_VERSION=file-version\n",
        encoding="utf-8",
    )
    for name in (
        "LLM_GATEWAY_URL",
        "LLM_GATEWAY_TOKEN",
        "LLM_JUDGE_MODEL",
        "LLM_JUDGE_MODEL_VERSION",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_JUDGE_MODEL", "shell-model")
    monkeypatch.setenv("LLM_GATEWAY_TOKEN", "stale-shell-key")

    config = JudgeConfig.from_env(PROMPT_VERSION, env_file=env_file)

    assert config.gateway_url == "https://api.openai.com/v1"
    assert config.model_id == "file-model"
    assert config.model_version == "file-version"
    assert config.token == "file-key"


@pytest.mark.parametrize(
    "gateway_url",
    ["https://api.openai.com/v1", "https://gateway.example.test/v1"],
    ids=[
        "suite:judge:direct_openai_gateway_token",
        "suite:judge:enterprise_gateway_token",
    ],
)
@pytest.mark.framework
def test_gateway_token_is_used_regardless_of_gateway_url(
    tmp_path, monkeypatch, gateway_url
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"LLM_GATEWAY_URL={gateway_url}\n"
        "LLM_GATEWAY_TOKEN=gateway-key\n"
        "LLM_JUDGE_MODEL=judge-model\n"
        "LLM_JUDGE_MODEL_VERSION=judge-version\n",
        encoding="utf-8",
    )
    for name in (
        "LLM_GATEWAY_URL",
        "LLM_GATEWAY_TOKEN",
        "LLM_JUDGE_MODEL",
        "LLM_JUDGE_MODEL_VERSION",
    ):
        monkeypatch.delenv(name, raising=False)

    config = JudgeConfig.from_env(PROMPT_VERSION, env_file=env_file)

    assert config.token == "gateway-key"


@framework_id("synthetic:judge:versions_and_cache_recorded")
def test_judge_runner_records_versions_and_reuses_cache(
    tmp_path, synthetic_agent_run
):
    gateway = FakeGateway()
    cache = tmp_path / "judge-cache"
    run = synthetic_agent_run

    first = run_agent_judges(
        run=run, gateway=gateway, config=judge_config(), cache_dir=cache
    )
    second = run_agent_judges(
        run=run, gateway=gateway, config=judge_config(), cache_dir=cache
    )
    changed_version = run_agent_judges(
        run=run,
        gateway=gateway,
        config=judge_config(model_version="2026-08-02"),
        cache_dir=cache,
    )
    changed_temperature = run_agent_judges(
        run=run,
        gateway=gateway,
        config=judge_config(temperature=0.2),
        cache_dir=cache,
    )

    first_records = [outcome.record for outcome in first if outcome.record]
    second_records = [outcome.record for outcome in second if outcome.record]
    changed_records = [outcome.record for outcome in changed_version if outcome.record]
    temperature_records = [
        outcome.record for outcome in changed_temperature if outcome.record
    ]
    assert gateway.calls == 9
    assert (
        len(first_records)
        == len(second_records)
        == len(changed_records)
        == len(temperature_records)
        == 3
    )
    assert first_records[0].cached is False
    assert second_records[0].cached is True
    assert changed_records[0].cached is False
    assert changed_records[0].cache_key != first_records[0].cache_key
    assert temperature_records[0].cache_key != first_records[0].cache_key
    assert first_records[0].score == 1.0
    assert first_records[0].model_version == "2026-08-01"
    assert first_records[0].prompt_version == PROMPT_VERSION
    assert first_records[0].temperature == 0.0
    assert temperature_records[0].temperature == 0.2
    assert len(first_records[0].prompt_hash) == 64
    assert len(first_records[0].rubric_hash) == 64
    assert len(first_records[0].input_hash) == 64


@framework_id("synthetic:judge:malformed_result_rejected")
def test_judge_runner_rejects_malformed_structured_result(
    tmp_path, synthetic_agent_run
):
    gateway = FakeGateway(
        {"criterion": "faithfulness", "score": 2.0, "explanation": "invalid"}
    )

    with pytest.raises(JudgeRunError, match="invalid faithfulness result"):
        run_agent_judges(
            run=synthetic_agent_run,
            gateway=gateway,
            config=judge_config(),
            cache_dir=tmp_path / "judge-cache",
        )


@framework_id("synthetic:judge:strict_gateway_schema")
def test_responses_gateway_sends_strict_schema_and_parses_result():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp-1",
                "model": "judge-deployment-2026-08-01",
                "output_text": json.dumps(
                    {
                        "criterion": "faithfulness",
                        "score": 0.7,
                        "explanation": "One detail is unsupported.",
                    }
                ),
                "usage": {"total_tokens": 120},
            },
        )

    gateway = OpenAIResponsesGateway(
        judge_config(token="secret"), transport=httpx.MockTransport(handler)
    )
    response = gateway.evaluate(
        "prompt",
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    )

    assert captured["model"] == "judge-deployment"
    assert captured["temperature"] == 0.0
    assert captured["store"] is False
    assert captured["text"]["format"]["strict"] is True
    assert response.result["score"] == 0.7
    assert response.actual_model == "judge-deployment-2026-08-01"


@framework_id("synthetic:judge:safe_gateway_error")
def test_responses_gateway_reports_safe_api_error_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            request=request,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "code": "invalid_json_schema",
                    "param": "text.format.schema",
                    "message": "unsafe remote message containing supplied data",
                }
            },
        )

    gateway = OpenAIResponsesGateway(
        judge_config(token="secret"), transport=httpx.MockTransport(handler)
    )

    with pytest.raises(JudgeGatewayError) as caught:
        gateway.evaluate("prompt", {"type": "object"})

    message = str(caught.value)
    assert "HTTP 400" in message
    assert "code=invalid_json_schema" in message
    assert "param=text.format.schema" in message
    assert "unsafe remote message" not in message


@pytest.fixture(scope="session")
def live_judge_outcomes(request, captured_runs):
    """Run all case-declared rubrics once and share their outcomes across reports."""
    if not request.config.getoption("--judge"):
        pytest.skip("requires --judge and configured LLM Gateway")
    config = JudgeConfig.from_env(PROMPT_VERSION)
    gateway = OpenAIResponsesGateway(config)
    cache: dict[str, list] = {}

    def outcomes_for(case_id: str):
        if case_id not in cache:
            cache[case_id] = run_agent_judges(
                run=captured_runs[case_id],
                gateway=gateway,
                config=config,
                cache_dir=DEFAULT_CACHE,
            )
        return cache[case_id]

    return outcomes_for


@pytest.mark.judge
@pytest.mark.evaluation
@pytest.mark.parametrize(
    ("case_id", "rubric_name"),
    [
        pytest.param(
            case["id"],
            rubric_name,
            id=f"{case['id']}:judge:{rubric_name}",
            marks=pytest.mark.case_check(case["id"], "judge"),
        )
        for case in CASES
        if (evaluation := get_answer_evaluation(case)) is not None
        for rubric_name in evaluation.rubrics
    ],
)
def test_live_llm_judge_is_reporting_only(live_judge_outcomes, case_id, rubric_name):
    outcomes = live_judge_outcomes(case_id)
    declared = CASES_BY_ID[case_id]
    evaluation = get_answer_evaluation(declared)
    assert evaluation is not None
    assert [outcome.criterion for outcome in outcomes] == evaluation.rubrics
    outcome = next(item for item in outcomes if item.criterion == rubric_name)
    assert outcome.status == "scored"
    record = outcome.record
    assert record is not None
    allure.attach(
        json.dumps(record.model_dump(), indent=2, default=str, sort_keys=True),
        name="judge verdict",
        attachment_type=allure.attachment_type.JSON,
    )
    print(
        f"{record.case_id} {record.criterion}={record.score}: "
        f"{record.explanation}"
    )

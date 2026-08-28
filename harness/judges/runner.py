"""Run captured agent answers through rubric-based LLM judging.

Scores are reporting-only: no rubric threshold changes a deterministic test verdict.
Live calls require explicit Gateway configuration through environment variables.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]

from harness.agent.models import AgentRun
from harness.judges.cache import JudgeCache
from harness.judges.gateway import JudgeGateway
from harness.judges.loader import load_rubrics
from harness.judges.models import (
    JudgeConfig,
    JudgeInput,
    JudgeOutcome,
    JudgeRecord,
    JudgeScore,
    score_schema,
)
from harness.judges.prompt import (
    PROMPT_VERSION,
    build_prompt,
    canonical_hash,
    text_hash,
)

DEFAULT_CACHE = ROOT / "run-results" / "judge-cache"
RESULT_SCHEMA_VERSION = 1


class JudgeRunError(RuntimeError):
    pass


def _require_prompt_version(config: JudgeConfig) -> None:
    if config.prompt_version != PROMPT_VERSION:
        raise JudgeRunError(
            f"configured prompt version {config.prompt_version!r} does not match "
            f"implemented version {PROMPT_VERSION!r}"
        )


def _score_input(
    *,
    judge_input: JudgeInput,
    rubric: dict,
    retrieval_passed: bool,
    gateway: JudgeGateway,
    config: JudgeConfig,
    cache: JudgeCache,
) -> JudgeRecord:
    rubric_name = judge_input.criterion
    prompt = build_prompt(judge_input, rubric)
    rubric_hash = canonical_hash(rubric)
    input_hash = canonical_hash(judge_input.model_dump())
    prompt_hash = text_hash(prompt)
    cache_key = canonical_hash(
        {
            "model": config.model_id,
            "model_version": config.model_version,
            "prompt_version": config.prompt_version,
            "temperature": config.temperature,
            "prompt_hash": prompt_hash,
            "rubric_hash": rubric_hash,
            "input_hash": input_hash,
            "result_schema_version": RESULT_SCHEMA_VERSION,
        }
    )

    cached = cache.load(cache_key)
    if cached is not None:
        return cached.model_copy(update={"retrieval_passed": retrieval_passed})

    gateway_response = gateway.evaluate(prompt, score_schema(rubric_name))
    try:
        score = JudgeScore.model_validate(gateway_response.result, strict=True)
    except ValidationError as exc:
        raise JudgeRunError(
            f"Gateway returned an invalid {rubric_name} result: {exc}"
        ) from exc
    if score.criterion != rubric_name:
        raise JudgeRunError(
            f"Gateway scored {score.criterion!r}; expected {rubric_name!r}"
        )

    record = JudgeRecord(
        case_id=judge_input.case_id,
        criterion=rubric_name,
        score=score.score,
        explanation=score.explanation,
        requested_model=config.model_id,
        model_version=config.model_version,
        actual_model=gateway_response.actual_model,
        prompt_version=config.prompt_version,
        temperature=config.temperature,
        prompt_hash=prompt_hash,
        rubric_hash=rubric_hash,
        input_hash=input_hash,
        cache_key=cache_key,
        cached=False,
        retrieval_passed=retrieval_passed,
        gateway_response_id=gateway_response.response_id,
        usage=gateway_response.usage,
    )
    cache.save(record)
    return record


def run_agent_judges(
    *,
    run: AgentRun,
    gateway: JudgeGateway,
    config: JudgeConfig,
    cache_dir: Path | None = DEFAULT_CACHE,
    judge_failed_runs: bool = False,
) -> list[JudgeOutcome]:
    """Run exactly the rubrics declared by the case, in declaration order."""
    _require_prompt_version(config)
    rubrics = load_rubrics()
    unknown = sorted(set(run.rubrics) - rubrics.keys())
    if unknown:
        raise JudgeRunError(f"{run.case_id} references unknown rubric(s): {unknown}")

    response = run.response
    failed_checks = [
        check.name for check in run.checks if check.status == "fail"
    ]
    if not run.retrieval_result.get("passed"):
        failed_checks.insert(0, "retrieval validators")
    deterministic_reason = (
        "deterministic prerequisites failed: " + ", ".join(failed_checks)
        if failed_checks
        else ""
    )
    cache = JudgeCache(cache_dir)
    outcomes: list[JudgeOutcome] = []

    for rubric_name in run.rubrics:
        reason = ""
        if response is None:
            reason = "agent response contract is invalid"
        elif not run.retrieved_context:
            reason = "captured retrieval context is empty"
        elif not run.deterministic_passed and not judge_failed_runs:
            reason = deterministic_reason or "deterministic prerequisites failed"
        if reason:
            outcomes.append(
                JudgeOutcome(
                    criterion=rubric_name,
                    status="not_run",
                    reason=reason,
                )
            )
            continue

        judge_input = JudgeInput(
            case_id=run.case_id,
            criterion=rubric_name,
            question=run.question,
            retrieved_context=run.retrieved_context,
            generated_answer=response.answer,
            reference_answer=run.reference_answer,
        )
        record = _score_input(
            judge_input=judge_input,
            rubric=rubrics[rubric_name],
            retrieval_passed=bool(run.retrieval_result.get("passed")),
            gateway=gateway,
            config=config,
            cache=cache,
        )
        outcomes.append(
            JudgeOutcome(
                criterion=rubric_name,
                status="scored",
                record=record,
            )
        )
    return outcomes

# PATTERNS CHANGES

## [2026-08-28] Created docs/PATTERNS/ (install mode, no prior directory existed)

Ran Phase 5 pattern extraction against docs/CODEMAP.md-scoped modules
(harness/, skill/, server_mcp.py, server_rest.py, cases/, rubrics/,
fixtures/, tests/). Read source directly for every pattern before
including it; qualified only patterns recurring in 2+ places per the
reverse-engineering "would we rebuild this?" test. 12 patterns extracted,
all verified against real code (no pattern assumed from a filename alone).

## [2026-08-28] Added strict-boundary-contract.md

Pydantic `extra="forbid", strict=True` + non-blank `field_validator`
convention, shared once and imported by every consumer. Evidence:
skill/schemas.py, harness/agent/models.py, harness/judges/models.py.

## [2026-08-28] Added deterministic-validator-function.md

`check_<requirement>(...) -> str | None` convention across every file in
harness/validators/.

## [2026-08-28] Added traceability-registry.md

CHECKS/ANSWER_CHECKS registry + `describe()`/`record()`/`skip()` idiom
duplicated independently in harness/runner.py and harness/agent/runner.py.

## [2026-08-28] Added multi-transport-adapter.md

skill/client.py's KnowledgeClient Protocol (Fake/MCP/REST + SpyClient) and
server_mcp.py/server_rest.py's shared schema translation, both funneling
through one parsing/marshaling path per direction.

## [2026-08-28] Added lazy-optional-dependency-import.md

mcp/httpx/ranx/uvicorn imported inside the function that needs them across
skill/client.py, harness/validators/contract.py, harness/ranking_metrics.py,
harness/runner.py, server_rest.py.

## [2026-08-28] Added fixture-load-and-validate.md

load-then-validate-once convention with artifact-named error classes:
harness/definitions/{cases,rubrics,agent_responses}.py, skill/fake_server.py.

## [2026-08-28] Added self-documenting-inventory.md

`render_inventory(markdown=False)` implemented independently in
harness/validators/registry.py and harness/judges/loader.py, both surfaced
via CLI flags.

## [2026-08-28] Added content-hash-fingerprint.md

`hash_paths()` (harness/baselines.py) and `canonical_hash()`
(harness/judges/prompt.py): one SHA-256 hash per independent concern,
composed for cache keys and compatibility fingerprints.

## [2026-08-28] Added versioned-compatibility-manifest.md

`build_run_manifest()`/`validate_record()`/`compare_records()` in
harness/baselines.py: common vs per-family profiles vs target, with an
explicit change_under_test allow-list gating metric comparison.

## [2026-08-28] Added three-state-check-result.md

ok/fail/skip (AgentCheckResult, harness/runner.py closures) and
scored/not_run (JudgeOutcome) with model_validator-enforced pairing of
status to payload.

## [2026-08-28] Added lazy-cached-execution-view.md

CaseExecutions/CaseResults/CapturedRuns layered lazy-cache views in
harness/execution.py.

## [2026-08-28] Added pytest-case-check-marker.md

_params()-driven test generation, case_check/level markers, and
framework_id() in tests/test_02_retrieval.py, tests/conftest.py,
tests/support.py.

## [2026-08-28] Created INDEX.md

One `## Pattern Name - description` header per extracted pattern, in the
order listed above; grep-able by header, no tables, each linking to its
pattern file.

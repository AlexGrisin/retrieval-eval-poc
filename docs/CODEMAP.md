# CODEMAP

**Purpose**: a file-system map of the project, so an agent can find where something
lives without a full directory scan. **Content**: markdown headers per directory,
immediate children listed, nested sub-headers for directories 3-4 levels deep;
per-directory file counts are recursive totals (gitignored directories excluded, matching
`.gitignore`). **Style**: greppable directory headers, one bullet per child.
**Not here**: what the code does or why — see [ARCHITECTURE.md](./ARCHITECTURE.md)
and [CONTEXT.md](./CONTEXT.md).

## / (12 files)

Evaluation harness for retrieval skill. Entry points: probe.py, server_*.py. Configuration: pyproject.toml, uv.lock.

- .env.example
- .gitignore
- ARCHITECTURE.md
- CASE_TEMPLATE.md
- README.md
- TASKS.md
- gain.json
- probe.py
- pyproject.toml
- server_mcp.py
- server_rest.py
- uv.lock

## agents/ (3 files)

Rosetta workflow state and agent-facing scaffolding. `TEMP/` is gitignored working
output (raw codemap generation artifacts) and excluded here like other gitignored
directories.

- init-workspace-flow-state.md
- IMPLEMENTATION.md
- MEMORY.md

## baselines/ (3 files)

Reference baseline evaluation results for regression testing

- mock-mcp.json
- mock-rest.json
- mock.json

## cases/ (6 files)

Evaluation test cases with expected outcomes (answer key)

- case-001-retries-ranking.yaml
- case-002-superseded-knowledge.yaml
- case-003-scope-isolation.yaml
- case-004-unknown-filter-rejected.yaml
- case-005-response-contract.yaml
- case-006-blank-query-rejected.yaml

## confluence/ (2 files)

Static exported documentation from wiki (reference only)

- EVALUATION_PROCESS_FLOW.md
- STRATEGY_OVERVIEW.md

## fixtures/ (3 files)

Frozen test data: corpus, agent responses, synthetic data

- corpus.yaml
- agent_responses/

### fixtures/agent_responses/ (2 files)

Synthetic agent response fixtures for test cases

- case-001-retries-ranking.yaml
- insufficient-context.yaml

## harness/ (25 files)

Core evaluation engine: case execution, ranking, validation, LLM judging

- __init__.py
- baselines.py
- execution.py
- ranking_metrics.py
- runner.py
- agent/
- definitions/
- judges/
- validators/

### harness/agent/ (3 files)

Agent interaction and execution models

- __init__.py
- models.py
- runner.py

### harness/definitions/ (4 files)

Case, rubric, and response definitions loaders

- __init__.py
- agent_responses.py
- cases.py
- rubrics.py

### harness/judges/ (7 files)

LLM judge implementations, prompt templates, caching

- __init__.py
- cache.py
- gateway.py
- loader.py
- models.py
- prompt.py
- runner.py

### harness/validators/ (6 files)

Response validators: answer quality, contract compliance, retrieval, formatting

- __init__.py
- answer.py
- contract.py
- formatting.py
- registry.py
- retrieval.py

## rubrics/ (3 files)

LLM judge evaluation rubrics (faithfulness, relevancy, correctness)

- answer_correctness.yaml
- faithfulness.yaml
- relevancy.yaml

## skill/ (7 files)

Knowledge retrieval skill client, schema contracts, formatters

- __init__.py
- client.py
- contracts.py
- fake_server.py
- formatter.py
- schemas.py
- skill.py

## tests/ (7 files)

Pytest test suite for harness, validators, and ranking metrics

- __init__.py
- conftest.py
- support.py
- test_01_definitions.py
- test_02_retrieval.py
- test_03_answer.py
- test_04_ranking.py
- test_05_judges.py
- test_06_baselines.py

## docs/ (20 files)

Rosetta-managed technical documentation

- TECHSTACK.md
- CODEMAP.md
- DEPENDENCIES.md
- CONTEXT.md
- ARCHITECTURE.md
- ASSUMPTIONS.md
- PATTERNS/

### docs/PATTERNS/ (14 files)

Recurring code conventions, each verified against 2+ real occurrences

- INDEX.md
- CHANGES.md
- strict-boundary-contract.md
- deterministic-validator-function.md
- traceability-registry.md
- multi-transport-adapter.md
- lazy-optional-dependency-import.md
- fixture-load-and-validate.md
- self-documenting-inventory.md
- content-hash-fingerprint.md
- versioned-compatibility-manifest.md
- three-state-check-result.md
- lazy-cached-execution-view.md
- pytest-case-check-marker.md

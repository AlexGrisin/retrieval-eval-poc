# ARCHITECTURE

**Purpose**: how this workspace is built — module boundaries, dependency direction,
structural invariants, testing architecture, build and run surface, extension seams.
**Content**: structure and rules an agent must respect when changing code.
**Style**: terse, grep-friendly headers, no narrative walkthroughs, no business
reasoning. **Not here**: why the system exists, domain vocabulary, scope — see
[CONTEXT.md](./CONTEXT.md). File inventory — see [CODEMAP.md](./CODEMAP.md).
Recurring code conventions — see [PATTERNS/INDEX.md](./PATTERNS/INDEX.md).
Dependency list — see [DEPENDENCIES.md](./DEPENDENCIES.md) and
[TECHSTACK.md](./TECHSTACK.md).

**The evaluation flow itself is documented and diagrammed by the human-authored
[../ARCHITECTURE.md](../ARCHITECTURE.md)** — complete current and target flow, request
and response schemas, per-validator tables, manifest fields, ownership map. Do not
restate it here; read it. Also human-authored: [../README.md](../README.md) (install,
every run command), [../CASE_TEMPLATE.md](../CASE_TEMPLATE.md) (case fields).

## Layers and dependency direction

Dependencies point one way only. A change that reverses an arrow is a design defect.

```text
tests/            pytest orchestration + reporting  (may import everything below)
  ↓
harness/          evaluation engine: definitions, runner, execution, validators,
                  ranking_metrics, judges, agent, baselines
  ↓
skill/            the system under test's client side: contracts, schemas, skill,
                  client, formatter, fake_server
  ↓
authored assets   cases/, fixtures/, rubrics/, baselines/  (data, no imports)
```

- `skill/` never imports `harness/`. It is the target, not the instrument.
- `server_mcp.py` and `server_rest.py` sit beside `skill/`, import `skill/schemas.py`,
  and hold no contract of their own — see pattern `multi-transport-adapter`.
- `probe.py` is a developer utility; nothing imports it.
- `docs/` and `agents/` are Rosetta-managed; no code reads them.

## Module responsibilities

Full per-concern ownership table: [../ARCHITECTURE.md](../ARCHITECTURE.md) §9. Summary
of the boundary each package defends:

| Package | Answers | Must not |
| --- | --- | --- |
| `harness/definitions/` | Is authored input structurally valid? | Execute anything |
| `harness/runner.py` | One retrieval case → one captured record | Assert quality |
| `harness/execution.py` | One execution per case, cached, lazy | Re-run a case |
| `harness/validators/` | Did an exact contract hold? | Return a bare bool |
| `harness/ranking_metrics.py` | How good was the order? | Gate a verdict |
| `harness/judges/` | Semantic score for one rubric | Override determinism |
| `harness/agent/` | Is a captured answer valid and judgeable? | Re-run retrieval |
| `harness/baselines.py` | Are two runs comparable? | Compare on mismatch |
| `skill/contracts.py` | Internal request/response objects | Know a transport |
| `skill/schemas.py` | The one shared MCP/REST wire shape | Be duplicated |
| `skill/fake_server.py` | Deterministic fixture-backed retrieval | Leak into prod code |
| `skill/client.py::SpyClient` | Emitted call + per-call latency, any transport | Gate on either |

## Structural invariants

- **One contract, two representations**: internal dataclasses (`skill/contracts.py`)
  and wire pydantic models (`skill/schemas.py`). Adding a field means changing both,
  plus `skill/formatter.py` if it is agent-visible.
- **Every check is registered**: a validator name absent from
  `harness/validators/registry.py` fails framework validation rather than passing
  silently — see pattern `traceability-registry`.
- **Three-state results**: `ok`/`fail`/`skip` and `scored`/`not_run`, skip always with a
  reason — pattern `three-state-check-result`.
- **Validators are pure functions** returning `str | None` — pattern
  `deterministic-validator-function`.
- **Heavy or optional SDKs import inside the function** (`mcp`, `ranx`, `httpx`,
  `uvicorn`) — pattern `lazy-optional-dependency-import`.
- **Authored YAML is validated exactly once, at load** — pattern
  `fixture-load-and-validate`. Case IDs derive from filenames and must be a contiguous
  `case-NNN-*` sequence.
- **Determinism before semantics**: judge and metric layers consume a captured run;
  they never call the target themselves.
- **Latency is measured, not gated**: `result["latency_ms"]` is a sibling of
  `result["metrics"]`, never a key inside it — `harness/baselines.py::compare_records`
  does an exact key-set comparison on `metrics`, so anything added there breaks every
  committed baseline. See `LATENCY-MEASUREMENT-PLAN.md`.

## Testing architecture

Configuration lives in `pyproject.toml` `[tool.pytest.ini_options]`;
`--strict-config --strict-markers` means an unregistered marker is an error.

- Test files are numbered to encode evaluation order: `test_01_definitions` →
  `test_02_retrieval` → `test_03_answer` → `test_04_ranking` → `test_05_judges` →
  `test_06_baselines`.
- `tests/support.py` loads cases at **collection** time and builds `case:level:check`
  IDs; `tests/conftest.py` owns transport, corpus, and execution fixtures.
- Two disjoint marker sets carry different meanings: `framework` (the instrument works
  — local synthetic inputs only) versus `evaluation` (a declared case against the
  selected target). Traceability markers: `traced`, `inferred`, `unratified`,
  `untraceable`, `boundary`. Opt-in: `judge`.
- Parametrization is generated per applicable (case, check) pair — pattern
  `pytest-case-check-marker`. Non-applicable checks are absent, not skipped as noise.
- **Parallelism rule**: `-n` is accepted only with the exact selection `-m framework`.
  xdist would give each worker its own session cache and execute a real case twice.
- **No rerun plugins by design.** A flaky case is a finding.
- Allure is a pure reporting layer over the same IDs; `allure-pytest` is pinned to
  `2.13.5` against an assumed `allure` CLI `2.13.8` (see DEPENDENCIES.md).

## Build, run, configure

- Python ≥3.12. `pyproject.toml` is a non-package `uv` project (`tool.uv.package =
  false`); `uv.lock` pins the tree. README documents a `python3 -m venv` install path
  as the workaround for Intel-`uv`-on-arm64.
- Run surface (exact commands: [../README.md](../README.md)): `pytest` with
  `-m framework|evaluation`, `--transport inprocess|mcp|rest`, `--judge`,
  `--alluredir`. Default transport is `inprocess`.
- **Transport gate (owner-confirmed policy)**: `inprocess` passing is what counts for
  a change to be considered validated. `mcp` and `rest` are optional additional
  protocol-boundary coverage, not a merge requirement.
- CI/CD: none exists; confirmed out of scope for this POC (owner decision, 2026-08-28).
  `harness/baselines.py`'s regression gate is invoked manually only.
- MCP and REST servers are built **in-process** by the test fixtures; no port is bound
  for a test run. `uvicorn` is imported only in `server_rest.py::main()`.
- Runtime configuration comes from `.env` (gitignored, authoritative when present) —
  `LLM_GATEWAY_URL`, `LLM_GATEWAY_TOKEN`, `LLM_JUDGE_MODEL`, `LLM_JUDGE_MODEL_VERSION`.
  Template: `.env.example`. Secrets are HTTP bearer credentials only, never prompt text.
- Generated output, all gitignored: `run-results/` (incl. `judge-cache/`),
  `allure-results/`, `allure-report/`. Committed output: `baselines/*.json`, written
  deliberately via the CLI runner's `--write-baseline`.

## Extension seams

Where new work attaches, in order of likelihood:

1. **New case** — add `cases/case-NNN-*.yaml` keeping numbering contiguous; expectation
   fields activate the applicable checks automatically.
2. **New deterministic check** — a `check_*` function in `harness/validators/`, plus a
   registry entry naming its requirement source. Unregistered means failing.
3. **New rubric** — `rubrics/*.yaml` plus selection in a case's
   `answer_evaluation.rubrics`. Judges stay reporting-only.
4. **Real target** — replace the fixture-backed provider behind
   `harness/execution.py`'s provider seam and the runner's system-metadata seam; the
   manifest fields already exist for real server/index/embedding versions.
5. **New transport** — a client in `skill/client.py` plus a server adapter, both
   reusing `skill/schemas.py`. No third contract copy.

# ASSUMPTIONS

**Purpose**: the open unknowns of this workspace — everything the docs assert without
proof, and everything observed but not yet decided. **Content**: one h3 entry per
unknown, each stating the assumption or observation, a confidence level, and the file
that should absorb it once resolved. **Style**: terse, grep-friendly headers, no
speculation dressed as fact. **Rules**: an entry is removed only when its target file
carries the resolved answer; a confirmed assumption graduates into
[CONTEXT.md](./CONTEXT.md) or [ARCHITECTURE.md](./ARCHITECTURE.md), it does not stay
here as a duplicate.

Confidence scale: **high** = observed directly in the repo, only the intent is open;
**medium** = inferred from consistent evidence; **low** = plausible reading, unverified.

## Evaluation validity

### Relevance labels are synthetic and unreviewed

- `expect.relevant` grades in `cases/*.yaml` were authored alongside the fixture corpus,
  not produced by an independent reviewer. Ranking metrics therefore measure the
  instrument, not retrieval quality.
- Confidence: high. Resolve in: `cases/*.yaml` + [CONTEXT.md](./CONTEXT.md) once a
  reviewed reference set exists.

### Request/response contracts and rubrics are drafts pending approval

- `skill/schemas.py`, the answer response contract in `harness/agent/`, and
  `rubrics/*.yaml` are marked provisional/`unratified`; several checks carry the
  `unratified` or `inferred` marker rather than `traced`.
- Confidence: high. Resolve in: `docs/PATTERNS/traceability-registry.md` +
  `harness/validators/registry.py` when approved requirement sources are assigned.

### Regression tolerance 0.02 is provisional

- Versioned as `absolute-drop-v1` in `harness/baselines.py` but not backed by an
  approved release policy or a reference set.
- Confidence: high. Resolve in: [ARCHITECTURE.md](./ARCHITECTURE.md) + `../TASKS.md`.

### Rubric traceability status is inconsistent by design, not by defect

- `rubrics/faithfulness.yaml` is `unratified` (source is a task doc; "no Component
  Guide section names it") while sibling rubrics are `traced`. Read as a real gap in
  the source material, **not** a code convention to normalise.
- Confidence: medium. Resolve in: `rubrics/*.yaml` when the Component Guide names the
  criteria. Until then, do not "fix" the inconsistency in code.

## Tooling and environment

### ruff is documented but not configured in pyproject.toml

- [TECHSTACK.md](./TECHSTACK.md) lists ruff as the linter/formatter; `pyproject.toml`
  has no `[tool.ruff]` section and no ruff in `[dependency-groups]`. Either it is used
  ad hoc from the developer's environment or the reference is aspirational.
- Confidence: medium. Resolve in: [TECHSTACK.md](./TECHSTACK.md) +
  [DEPENDENCIES.md](./DEPENDENCIES.md).

### allure CLI 2.13.8 is assumed installed out-of-band

- `allure-pytest==2.13.5` is pinned in `pyproject.toml` specifically to match a
  commandline version that is not installed or version-checked by anything in the repo.
  A machine with allure 2.16+ silently produces an empty report rather than erroring.
- Confidence: high. Resolve in: [DEPENDENCIES.md](./DEPENDENCIES.md) + `../README.md`
  install section, ideally with a `allure --version` precondition check.

### No bootstrap/setup doc beyond the README install block

- `.env.example` exists; the README documents the `python3 -m venv` workaround for
  Intel-`uv`-on-arm64. There is no single scripted setup path.
- Confidence: high. Resolve in: `../README.md` (human-authored — do not edit without
  the owner's decision).

### Repository has no git remote and one contributor

- Single contributor (`agrisin@griddynamics.com`), no remote configured; SCM/CI fields
  in `gain.json` left as placeholders. IDE assumed `claude-code`. `confluence/` treated
  as static wiki export snapshots.
- Confidence: medium. Resolve in: `gain.json` when the repo gets a remote/team.

## Undocumented conventions

### Marker validation mechanism is unclear

- `--strict-markers` rejects unregistered markers, and the `untraceable` marker is
  documented as one that "must fail framework validation" — but the exact mechanism
  that enforces traceability markers against the validator registry was not traced
  end to end during discovery.
- Confidence: medium. Resolve in:
  [PATTERNS/pytest-case-check-marker.md](./PATTERNS/pytest-case-check-marker.md).

### Atomic write is used by the judge cache but not by baselines

- `harness/judges/cache.py::JudgeCache` writes to `.{key}.tmp` then `Path.replace`;
  `harness/baselines.py::write_record()` writes JSON directly, non-atomically, to a
  comparable append-only-by-convention output. Plausibly intentional (baselines are
  hand-invoked via `--write-baseline`; cache entries are written many times per run),
  but unconfirmed. Left out of the 12 patterns under the 2+ occurrences rule.
- Confidence: medium that the difference is intentional. Resolve in:
  `harness/baselines.py` (adopt the idiom) or a new pattern file (document it).

### Numbered case-ID contract has no second instance

- `harness/definitions/cases.py` enforces `CASE_ID_PATTERN` and contiguous numbering
  from `001`; rubrics and agent-response fixtures are keyed by name instead. Documented
  inline in `fixture-load-and-validate.md` rather than promoted to its own pattern.
- Confidence: medium. Resolve in:
  [PATTERNS/fixture-load-and-validate.md](./PATTERNS/fixture-load-and-validate.md) —
  promote to a standalone pattern if a second numbered-sequence fixture type appears.

### Latency numbers are real timing, but a fake backend

- `result["latency_ms"]` (see `LATENCY-MEASUREMENT-PLAN.md`) times each
  `SpyClient.search()` call for real — `inprocess` mode is near-zero (in-memory
  Python call), `mcp`/`rest` show real `asyncio`/serialization round-trip
  overhead, but none of it is a real network+server latency signal yet since
  both transports wrap in-memory servers, not a live one. No pass/fail budget
  exists — report-only until a real threshold is approved against real numbers.
- Confidence: high. Resolve in: [ARCHITECTURE.md](./ARCHITECTURE.md) +
  `../TASKS.md` once the real Knowledge Server is connected and a threshold is
  reviewed.

## kb_search migration (in progress)

### kb_fetch and kb_related are not implemented

- `mcp-tool-contracts-reference.md` specifies three tools; this workspace's harness,
  fixture, cases, and validators cover `kb_search` only (see
  `KB-SEARCH-MIGRATION-PLAN.md`). `kb_fetch`'s `found: false`-is-not-an-error
  semantics and `kb_related`'s depth/direction graph traversal have no code or cases
  yet, though `fixtures/corpus.yaml` already carries `relationships` for when that
  phase starts.
- Confidence: high (deliberately scoped out, not an oversight). Resolve in: a follow-up
  migration plan, same shape as `KB-SEARCH-MIGRATION-PLAN.md`.

### Root ARCHITECTURE.md §§4-9 still describe the retired knowledge_retrieve contract

- §§1-3 were rewritten for `kb_search` (request/response shape, entity identity).
  §§4 (deterministic validators table), 5 (ranking metrics prose), 6 (generated-answer
  JSON examples), 7 (pytest execution — mostly still accurate, some field mentions
  stale), 8 (target end-to-end flow), and 9 (ownership map) were not, and still say
  "note", "veracity", "scope.department" in places. The code (schemas, validators,
  runner, cases, tests) is fully migrated and green across all three transports;
  only this narrative's tail is stale. A migration-note banner at the top of the file
  flags exactly this.
- Confidence: high. Resolve in: `../ARCHITECTURE.md` §§4-9, a follow-up editorial pass.

### docs/PATTERNS/*.md code excerpts show the retired contract's field names

- The pattern *descriptions* (strict-boundary-contract, multi-transport-adapter, etc.)
  still apply unchanged to `kb_search` — confirmed during the migration — but their
  embedded code excerpts (e.g. `NoteResult`, `knowledge_retrieve`) were not refreshed
  to `SearchHit`/`kb_search`.
- Confidence: high. Resolve in: `docs/PATTERNS/*.md`, a follow-up editorial pass.


# Rosetta Implementation Summary

This file is a brief and durable summary of the implementation state of the Rosetta
documentation layer in this workspace.
It is intentionally concise and should not be used as a chronological work log.

For detailed change history, use git history and PRs instead of expanding this file.
For the product's own delivery plan and task status, see [../TASKS.md](../TASKS.md) —
that file, not this one, owns the retrieval-eval feature history.

**Scope of this file**: agent-facing workspace scaffolding under `docs/` and `agents/`.
**Style**: one workstream per h3 header, `[status], [date]`, brief bullets with
keywords and references. **Not here**: business context
([../docs/CONTEXT.md](../docs/CONTEXT.md)), structure
([../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)), open unknowns
([../docs/ASSUMPTIONS.md](../docs/ASSUMPTIONS.md)).

## Baseline

- Rosetta doc layer initialised on an existing, human-documented Python repository
  (`init-workspace-flow`, install mode, plugin mode, non-composite, 74 source files).
- Pre-existing human-authored docs at the repo root are cross-referenced, never
  restated: `README.md`, `ARCHITECTURE.md`, `CASE_TEMPLATE.md`, `TASKS.md`,
  `confluence/*.md`. `EVALUATION_FLOW.md` was merged into `ARCHITECTURE.md` and
  removed during Phase 8 (owner decision) — see below.
- Present after this run: `docs/{CONTEXT,ARCHITECTURE,TECHSTACK,CODEMAP,DEPENDENCIES,
  ASSUMPTIONS}.md`, `docs/PATTERNS/` (INDEX + CHANGES + 12 patterns),
  `agents/{IMPLEMENTATION,MEMORY}.md`, `agents/init-workspace-flow-state.md`.
- Not present by decision: `docs/TODO.md` (no large actionable improvement found),
  `docs/REQUIREMENTS/` (out of scope), `refsrc/` (no modernization source), external
  code-graph backend (user chose CODEMAP.md only — `docs/CODEMAP.md` is the file map).
- No product source code was changed by this run. `.gitignore` gained a Rosetta section.

## Major Implemented Workstreams

### Discovery baseline: done, 2026-08-28

- `docs/TECHSTACK.md`, `docs/CODEMAP.md`, `docs/DEPENDENCIES.md` generated from source.
- Recorded the load-bearing dependency facts: `allure-pytest==2.13.5` pinned against
  allure CLI `2.13.8`; `mcp`/`ranx`/`httpx`/`uvicorn` lazily imported; `uvicorn` used
  only by `server_rest.py::main()` and deliberately absent from `pyproject.toml`.
- Confirmed no CI/CD present — logged as a gap, not invented.

### Pattern extraction: done, 2026-08-28

- `docs/PATTERNS/` created fresh; 12 patterns, each verified against 2+ real
  occurrences before inclusion. Index: [../docs/PATTERNS/INDEX.md](../docs/PATTERNS/INDEX.md).
- Scope read: `harness/` (all subpackages), `skill/`, `server_mcp.py`,
  `server_rest.py`, `cases/`, `rubrics/`, `fixtures/`, `tests/`.
- Single-instance candidates were deliberately not promoted to patterns (atomic cache
  write, numbered case-ID contract) and are carried as open items in ASSUMPTIONS.md.

### Documentation layer: done, 2026-08-28

- `docs/CONTEXT.md` (business/domain, stakeholder view), `docs/ARCHITECTURE.md`
  (layers, invariants, testing, build, extension seams), `docs/ASSUMPTIONS.md`
  (open unknowns with confidence and resolution target), `agents/MEMORY.md`
  (operational lessons template, seeded with this run's discoveries).
- Split enforced: CONTEXT.md carries no technical detail, ARCHITECTURE.md carries no
  business reasoning, and both defer the evaluation flow itself to the human-authored
  root `ARCHITECTURE.md`.

### Phase 8 owner decisions applied: done, 2026-08-28

- Root `EVALUATION_FLOW.md` merged into root `ARCHITECTURE.md` (§5 ranking-metric and
  relevance-grade tables, §6 rubric-selection-guidance table) and removed; all
  references to it fixed in `docs/CONTEXT.md`, `docs/ARCHITECTURE.md`,
  `docs/CODEMAP.md`. Two `confluence/*.md` prose mentions of the removed filename were
  left untouched (external wiki-export snapshots, not edited without the owner).
- `.gitignore`'s stale `SKILL.md` "committed on purpose" line removed (owner confirmed:
  stale reference, no such file was ever meant to exist here).
- Transport-gate policy recorded in `docs/ARCHITECTURE.md`: `inprocess` is the pass/fail
  gate; `mcp`/`rest` are optional extra coverage, not a merge requirement.
- CI/CD confirmed out of scope for this POC; noted in `docs/ARCHITECTURE.md`, no
  pipeline added.
- Resolved `docs/ASSUMPTIONS.md` entries removed accordingly: CI/CD-unenforced,
  SKILL.md-missing, MCP/REST/inprocess-undocumented, EVALUATION_FLOW.md-redundancy.

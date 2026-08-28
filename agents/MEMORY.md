# AGENT MEMORY

Generalized reusable lessons from agent sessions.
Root causes converted into preventive rules, not incident-specific notes.
Entries are h3 headers with [ACTIVE|RETIRED] status.
Content: brief, grep-friendly, MECE across sections.
Style: one-liner per entry, optional sub-bullets for context.
Keep template entries so that AI knows how to fill them in later on.

Operational notes only. Domain and structure live in
[../docs/CONTEXT.md](../docs/CONTEXT.md) and
[../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md); unresolved unknowns live in
[../docs/ASSUMPTIONS.md](../docs/ASSUMPTIONS.md). Do not duplicate them here.

## Preventive Rules

### <Generalized Preventive Rule> [ACTIVE|RETIRED]
[Root cause, Reasons, Problems]

## What Worked

### <Generalized What Worked> [ACTIVE|RETIRED]
[Root cause, Reasons, Problems]

## What Failed

### <Generalized What Failed> [ACTIVE|RETIRED]
[Hypothesis, Root cause, Reasons, Problems]

## Discoveries

### <Generalized Discovery> [ACTIVE|RETIRED]
[Usage, Reasons, Problems]

### A version pin can encode an external CLI version nothing in the repo checks [ACTIVE]
[Usage: `allure-pytest==2.13.5` in `pyproject.toml` is pinned to an assumed local
`allure` commandline `2.13.8`; Reasons: 2.16+ emits a `titlePath` field the 2.13
report-model parser rejects; Problems: the failure is silent — every result is dropped
from the generated report rather than erroring, so verify `allure --version` before
touching the pin or debugging an empty report.]

### Sibling writers of comparable on-disk output do not share a durability idiom [ACTIVE]
[Usage: `harness/judges/cache.py` writes tmp-then-`Path.replace`, while
`harness/baselines.py::write_record()` writes JSON directly; Reasons: possibly
intentional (hand-invoked `--write-baseline` versus many writes per run); Problems:
do not assume atomic write when editing baseline output, and do not "unify" the two
without the owner's answer — tracked in ASSUMPTIONS.md.]

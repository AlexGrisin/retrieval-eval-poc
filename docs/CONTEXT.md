# CONTEXT

**Purpose**: business context, purpose, and domain vocabulary, from a stakeholder's
point of view. Read first in every session. **Content**: why the system exists, who
cares, what the words mean, what is in and out of scope. **Style**: terse bullets,
grep-friendly headers, no code, no file layout, no technology names unless the
technology *is* the product decision. **Not here**: modules, structure, testing,
build — see [ARCHITECTURE.md](./ARCHITECTURE.md).

Human-authored authoritative sources — do not restate them here, read them:

- [../README.md](../README.md) — how to run everything, full option reference.
- [../ARCHITECTURE.md](../ARCHITECTURE.md) — complete evaluation flow, ownership map.
- [../CASE_TEMPLATE.md](../CASE_TEMPLATE.md) — every case field and what it activates.
- [../TASKS.md](../TASKS.md) — delivery plan, acceptance criteria, task status.
- [../confluence/STRATEGY_OVERVIEW.md](../confluence/STRATEGY_OVERVIEW.md) — platform strategy;
  [../confluence/EVALUATION_PROCESS_FLOW.md](../confluence/EVALUATION_PROCESS_FLOW.md) — the component process this repo implements.

## Why this exists

- Agents answer from retrieved knowledge. If retrieval silently degrades, the agent's
  answers degrade and nobody notices until a user is misled.
- This workspace is the measuring instrument: a repeatable, case-driven evaluation that
  detects broken retrieval contracts, unsafe results, and quality regressions **before**
  they reach an agent.
- Principle 1: **deterministic where possible, AI where necessary.** Exact contracts
  validated first; semantic judgment only where meaning cannot be an exact rule.
- Principle 2: **separate result types.** Definition errors, deterministic failures,
  quality measurements, and AI judgments are reported apart, never averaged.
- First reference implementation of a wider Context Engineering evaluation strategy,
  intended to extend later to authoring, ingestion, indexing, semantic assets,
  reconciliation, security, and production operation.
- Covers the **read path** only: consumer → retrieval skill → knowledge server →
  assembled context → generated answer.
- Proof of concept: proves the instrument works against a controlled fake backend. It
  does **not** yet measure production retrieval quality.

## Stakeholders and what each one wants from a run

| Stakeholder | Question a run must answer |
| --- | --- |
| Agent / platform engineer | Did I break a retrieval contract or a safety invariant? |
| Quality owner | Did ranking quality drop against a comparable reference run? |
| Knowledge governance | Are superseded, out-of-scope, or forbidden notes returned? |
| Release decision maker | Are these two scoreboards comparable, and what changed? |
| Product owner | Is the generated answer grounded, relevant, and correct enough? |

## Domain vocabulary

- **Case** — a reviewed, version-controlled evaluation input: a question, caller scope,
  and the expectations that activate checks. The answer key; reviewed like knowledge.
- **Corpus** — the controlled, frozen knowledge fixture a run is evaluated against.
  Keeps failures attributable to code or contract change, not to shifting live data.
- **Note** — one atomic unit of knowledge, versioned; retrieval returns notes ranked.
- **Relevance label / grade** — a human judgment per question and note: `2` directly
  answers, `1` materially useful but insufficient, `0` not relevant.
- **Check** — one exact, zero-tolerance rule with a named requirement source. Passes,
  fails, or is explicitly skipped with a reason; never silently absent.
- **Validator** — the deterministic evaluation of a check over a captured run.
- **Measurement** — a numeric retrieval-quality score (recall, precision, first-useful-
  result rank, ranking gain). Informative, not a pass/fail on its own.
- **Rubric** — a named semantic criterion (faithfulness, relevancy, answer correctness)
  a judge scores an answer against.
- **Judge** — an approved model, reached through a governed gateway, that scores a
  rubric. Reporting-only; it can never override a deterministic failure.
- **Run manifest** — the versioned record of what was evaluated, against what, with
  which controlled inputs — the basis for deciding comparability.
- **Baseline** — a reviewed reference scoreboard a later run may be compared to, and
  only if the manifests are compatible.
- **Change under test** — the one target field a run is explicitly allowed to differ
  on. Undeclared target changes, and any change to controlled evaluation inputs,
  invalidate comparison rather than being waived.
- **Framework vs evaluation** — framework results prove the instrument works;
  evaluation results describe the target's behaviour. Never interchangeable.

## Business rules that outrank convenience

- Structural validity of evaluation inputs is checked before any target is called.
- An unregistered or untraceable check is a failure, not a pass.
- Semantic judgment runs only after its deterministic prerequisites pass.
- Judge scores and ranking measurements do not gate a build; deterministic failures do.
- Incompatible runs are rejected before any regression is computed — no
  intersection-only comparison, no quiet waiver.
- A flaky case is the finding. There is no retry-until-green.
- Production incidents and observed failures become new cases.

## Out of scope

- Enterprise-wide model-safety programme; approval of the knowledge corpus and of
  reference labels — treated as controlled inputs supplied from elsewhere.
- Write path (source change → authoring → ingestion → index).
- Production monitoring, alerting, scheduled execution, release gating policy —
  separate deliveries per [../TASKS.md](../TASKS.md).
- Proving production retrieval quality — blocked on the real knowledge server and
  approved contracts.

## Known-provisional areas

Recorded with confidence and a resolution target in
[ASSUMPTIONS.md](./ASSUMPTIONS.md). Notably: contracts and rubrics are drafts pending
approval, relevance labels are synthetic and unreviewed, the regression tolerance is
provisional.

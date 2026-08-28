# Retrieval skill evaluation

## What this is

This is a pytest-based proof of concept for evaluating a knowledge-retrieval skill.
It sends versioned test cases through the skill, captures the request sent to the
knowledge server, validates deterministic contracts and safety invariants, and scores
the ordered results with standard information-retrieval metrics.

The same cases can run directly in process or across MCP and REST boundaries. A
controlled fixture corpus keeps runs repeatable and makes failures attributable to
code or contract changes rather than changing production data.

The current backend is a deterministic token-overlap fake, so its scores do not prove
production retrieval quality. The POC proves that request construction, protocol
schemas, response formatting, result invariants, and ranking measurements can be
tested consistently. Generated-answer rubrics and an opt-in LLM Gateway judge runner
are also present. Normal pytest runs use a fake Gateway and never call a live model.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete test flow, including the
request and response schemas, deterministic validators, ranking metrics, generated-
answer judging, and target end-to-end agent flow.

See [CASE_TEMPLATE.md](CASE_TEMPLATE.md) for the complete case template, every
supported field and value, defaults, and the evaluation activated by each declaration.

## Project structure

```text
retrieval-eval-poc/
├── ARCHITECTURE.md         # Detailed current and target evaluation flows
├── CASE_TEMPLATE.md        # Complete case template and field reference
├── cases/                  # Case inputs, expectations, and selected judge rubrics
│   └── case-NNN-*.yaml     # One ordered sequence; fields activate applicable checks
├── fixtures/
│   ├── agent_responses/    # Case-keyed synthetic responses used before agent integration
│   └── corpus.yaml         # Controlled knowledge corpus used by the fake backend
├── rubrics/                # LLM-judge criteria used by the opt-in judge runner
├── harness/
│   ├── agent/              # Provisional final-response contract and captured-run evaluator
│   ├── definitions/        # Validates retrieval, answer, and rubric definitions
│   ├── validators/         # Deterministic pass/fail checks over executed behaviour
│   ├── judges/             # Prompts, Gateway calls, caching, and judge reporting
│   ├── baselines.py        # Run manifests and strict compatibility comparison
│   ├── execution.py        # Lazy one-execution-per-case store and captured views
│   ├── ranking_metrics.py  # Recall, precision, MRR, and NDCG through ranx
│   └── runner.py           # Shared retrieval case-execution engine
├── skill/
│   ├── contracts.py        # Transport-independent request and response objects
│   ├── schemas.py          # Shared Pydantic wire schemas for MCP and REST
│   ├── client.py           # MCP, REST, and request-recording clients
│   ├── skill.py            # Builds requests, calls retrieval, and formats responses
│   ├── formatter.py        # Converts structured results into agent-visible context
│   └── fake_server.py      # Deterministic fixture-backed retrieval implementation
├── tests/
│   ├── conftest.py         # Pytest transport, corpus, and case-execution fixtures
│   ├── support.py          # Collection-time case loading and readable test IDs
│   ├── test_01_definitions.py # Case and rubric definition checks
│   ├── test_02_retrieval.py # One test per applicable retrieval validator
│   ├── test_03_answer.py    # Exact answer checks and judge prerequisites
│   ├── test_04_ranking.py   # Case measurements and ranking-adapter tests
│   ├── test_05_judges.py    # Fake-Gateway pipeline and opt-in live judge
│   └── test_06_baselines.py  # Manifest, compatibility, and regression policy tests
├── server_mcp.py           # MCP boundary around the fake backend
├── server_rest.py          # REST boundary around the same fake backend
├── baselines/              # Saved CLI-runner snapshots; not used by pytest
└── probe.py                # Developer exploration utility; not part of pytest
```

The responsibility boundaries are intentional:

| Area | Question it answers |
| --- | --- |
| `definitions/` | Is the evaluation input structurally well formed? |
| `validators/` | Did an exact runtime contract or invariant pass? |
| `ranking_metrics.py` | How good was the ordered retrieval result? |
| `agent/` and case `answer_evaluation` | Is a captured final response structurally valid and safe to judge? |
| `judges/` and `rubrics/` | How is a generated answer evaluated semantically? |

## Install

The deterministic suite uses `ranx` for TREC-tested ranking metrics. Create a
virtual environment:

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install "ranx>=0.3.21,<0.4" "mcp>=1.2" fastapi httpx pydantic python-dotenv pyyaml pytest pytest-xdist "allure-pytest==2.13.5"
```

Then run the suite with `.venv/bin/pytest`. MCP and REST use the same environment
and add their protocol-boundary checks.

Use `python3 -m venv` rather than `uv sync` on an Apple Silicon Mac with the Intel
`uv` on PATH. That `uv` selects an x86_64 interpreter on an arm64 host and then tries
to cross-compile `cryptography` from source, which fails.

## Run the tests

One test per applicable case and validator, so a red build names the rule rather than
showing a Cartesian matrix of meaningless skips. Run from the repository root and use
the virtual environment:

```bash
.venv/bin/pytest
```

That command runs both categories. Run only the evaluation framework's own unit and
contract tests with:

```bash
.venv/bin/pytest -m framework
```

Run only case-driven evaluation checks with:

```bash
.venv/bin/pytest -m evaluation
```

Select the protocol seam independently, for example:

```bash
.venv/bin/pytest -m evaluation --transport mcp
```

Add live answer judging only to an evaluation execution:

```bash
.venv/bin/pytest -m evaluation --transport mcp --judge -s
```

`framework` results show that the measuring instrument works. `evaluation` results
describe the selected target's behavior for declared cases. The current target is
still fixture-backed until the real server and agent adapters are connected.

Framework tests use only local synthetic fixtures and never invoke the target chosen
by `--transport`. They may run in parallel when pytest-xdist is installed:

```bash
.venv/bin/pytest -m framework -n auto
```

Evaluation and live-judge runs are deliberately single-process. Parallel workers
would split one case's checks across processes and execute the real case more than
once, so pytest rejects `-n` unless the exact selection is `-m framework`.

The default uses the in-process fake backend. The two invalid-request tests are
skipped because there is no protocol boundary in that mode.

Run the same six cases across MCP or REST. You do **not** start a server yourself;
pytest builds it in-process and uses an in-memory transport:

```bash
.venv/bin/pytest --transport mcp
```

```bash
.venv/bin/pytest --transport rest
```

Both transports use the shared schema in `skill/schemas.py`, so request or response
contract drift appears as a failed test.

Run only validators traced to an agreed requirement:

```bash
.venv/bin/pytest -m traced
```

Run one validator while iterating:

```bash
.venv/bin/pytest -k every_result_has_provenance
```

Every case is structurally validated before execution. Missing required fields,
unknown expectation keys, invalid case filenames, noncontiguous numbering, and
malformed relevance labels fail before the retrieval skill is called.

Case-driven checks are reported in evaluation-flow order using
`case:level:check`, for example
`case-001-retries-ranking:answer:required_citations`. `suite` identifies a repository-wide
definition or configuration check; `synthetic` identifies a focused harness test
rather than a retrieval scenario.

Evaluation reporting is case-first. Each case executes lazily at its first runtime
check, its captured retrieval and answer are reused for the remaining levels, and the
case finishes before reporting starts for the next case. Selecting one case therefore
executes only that case:

```bash
.venv/bin/pytest -m evaluation -k case-001-retries-ranking --transport mcp
```

## See what the suite checks

Use pytest collection to list tests without executing them:

```bash
.venv/bin/pytest --collect-only -q
```

## Allure report

Any run can also produce an [Allure](https://allurereport.org/) report. The
`case:level:check` hierarchy is mapped onto Allure directly, with no separate
taxonomy to maintain: `suite` is the case ID, `sub-suite` is the evaluation level
(`request`, `response`, `expectation`, `answer`, `ranking`, `judge`), and `story`
is the check or metric name. Every case-driven test also gets the captured
retrieval trace, ranking metrics, or captured agent run attached as JSON, and a
live judge test attaches the actual judge verdict.

```bash
.venv/bin/pytest --alluredir=allure-results
allure serve allure-results
```

`allure serve` starts a local server and opens the report in a browser; use
`allure generate allure-results -o allure-report --clean` instead for a static
folder to publish from CI. `allure-results/` and `allure-report/` are gitignored
per-run output, same as `run-results/`.

Allure reporting is additive: it never adds assertions and never gates a run,
same as the LLM judge scores below.

`allure-pytest` is pinned to the `2.13` line to match this repository's assumed
Allure commandline version (`2.13.8`). A newer `allure-pytest` writes result
fields an older commandline's report-model parser rejects, which silently drops
every result from the generated report rather than erroring loudly -- check
`allure --version` before bumping the pin.

## LLM judge

An optional `answer_evaluation` section in a case declares deterministic final-answer
expectations, selected semantic rubrics, and an optional reference answer. It does not
contain the generated answer. `harness/agent/` combines a captured response with the
retrieval trace from that same case. It validates the response contract—including a
nonblank answer—plus structured status and exact citations before
`run_agent_judges()` is allowed to call a model.

The current repository does not yet contain a real answer-generating agent connector.
Tests load synthetic structured responses from `fixtures/agent_responses/` and feed
them through the same captured-agent path. The routine POC response uses the same
filename stem as its case, for example `case-001-retries-ranking.yaml`. A failed retrieval or
answer validator produces a `not_run` outcome for every rubric declared by the case;
`judge_failed_runs=True` is an explicit diagnostic override. The runner executes
exactly `answer_evaluation.rubrics` in declaration order. It does not infer rubrics
from answer status or reference data.

Normal pytest runs exercise this pipeline with a fake Gateway. They never need
credentials and never call a model. A live judge test is collected only with
`--judge` and requires an OpenAI Responses-compatible LLM Gateway.

For direct OpenAI access, copy `.env.example` to `.env`, put the API key in
`LLM_GATEWAY_TOKEN`, and run:

```bash
.venv/bin/pytest --judge -s
```

`.env` is ignored by Git and is authoritative for local judge configuration when it
exists, so stale exported values cannot silently change a run. CI normally has no
`.env` file and uses its environment variables instead. `LLM_GATEWAY_TOKEN` supplies
the bearer credential for both direct OpenAI and enterprise Gateway calls.

If a project exposes only the `gpt-4o-mini` alias and rejects the dated snapshot,
use `LLM_JUDGE_MODEL=gpt-4o-mini` with
`LLM_JUDGE_MODEL_VERSION=unversioned-alias` for POC runs. This is not a reproducible
production pin; the judge record still captures the concrete model ID returned by
OpenAI under `actual_model`.

For an enterprise LLM Gateway, `.env` can contain the equivalent settings:

```bash
LLM_GATEWAY_URL=https://gateway.example/v1 \
LLM_JUDGE_MODEL=approved-judge-deployment \
LLM_JUDGE_MODEL_VERSION=2026-08-01 \
.venv/bin/pytest --judge -s
```

Include `LLM_GATEWAY_TOKEN` when the Gateway uses bearer authentication; omit it when
the runtime supplies workload identity. Model IDs or versions ending in `latest` are
rejected. Live judgments are cached under `run-results/judge-cache/` from the model,
prompt, rubric, schema, temperature, and evaluation-input hashes.

The judge uses a fixed default temperature of `0`. Temperature is recorded in every
judge result and participates in its cache identity. Cases cannot override it. A
different temperature is a different judge configuration and its scores are not
directly comparable.

Judge scores are reporting-only. They do not change deterministic validator results or
ranking-metric values, and no score threshold gates pytest.

## Ranking metrics

Metrics compare the ordered note IDs returned by retrieval with the reference labels
under `expect.relevant` in each case.

| Metric (full name + acronym) | Business meaning | Current calculation |
| --- | --- | --- |
| Recall at k (`Recall@k`) | Did retrieval find all known useful knowledge needed by the agent? | Number of notes graded `1` or `2` found in the first `k` results, divided by all notes graded `1` or `2`. `k` comes from the case. |
| Precision at 5 (`Precision@5`) | How much of the first five context positions is useful rather than noise? | Number of notes graded `1` or `2` in the first five positions, divided by `5`. Missing positions and unlisted notes count as not relevant. |
| Mean Reciprocal Rank (`MRR`) | How quickly does the agent encounter its first useful result? | `1 / rank` of the first note graded `1` or `2`; `0` when none is returned. |
| Normalized Discounted Cumulative Gain at k (`NDCG@k`) | Are the best notes presented before weaker and irrelevant notes? | Actual `sum(grade / log2(rank + 1))` through `k`, divided by the best possible value for the same labels. Grade `2` therefore contributes more than grade `1`, and lower positions contribute less. |

### Grades

Grades are assigned per query and note under `expect.relevant`:

| Grade | Meaning | Metric treatment |
| --- | --- | --- |
| `2` | Directly answers the question | Relevant for all metrics; higher gain for NDCG. |
| `1` | Materially useful but insufficient alone | Relevant for all metrics; lower gain for NDCG. |
| `0` | Not relevant | Not relevant for all metrics. |
| Unlisted | No relevance label in the case | Currently treated as not relevant. |

Grade `0` means harmless but irrelevant. `must_not_return` is separate and means the
note's presence is a defect regardless of rank.

The adapter returns explicit zero scores when relevant notes exist but retrieval
returns nothing. Labels include a note version, but the current metric comparison uses
only the note ID; version mismatches must therefore be caught separately until ranking
identities change to `note@version`.

## Evaluation versions and baseline comparison

Every CLI run produces a versioned manifest with three distinct sections:

- `compatibility`: controlled evaluation inputs that must match, including corpus and
  case content, contracts, evaluation code, dependencies, transport, retrieval/index
  configuration, and the result-family measurement definition;
- `target`: the Knowledge Server, Retrieval Skill, store, index build, and retrieval
  configuration being evaluated;
- `run`: traceability metadata such as execution time, which does not make otherwise
  equivalent functional runs incompatible.

A target version may differ only when the run explicitly declares that field as the
`change_under_test`. Changes to the corpus, cases, relevance labels, contracts,
measurement code, dependencies, or ranking policy cannot be waived as target changes.

Compatibility is evaluated per result family. The current CLI baseline compares
ranking measurements and therefore requires the ranking profile to match. It also
requires exactly the same case IDs and metric names. Added, removed, renamed, or newly
applicable cases and metrics require a reviewed new baseline rather than an
intersection-only comparison.

Real-system metadata is supplied through the runner's system-metadata seam and records
the server build, skill version, store version, index build, embedding configuration,
schema, vocabulary, ontology, and permission-policy versions. The first approved real
baseline is a separate delivery task; it uses this same manifest and comparison
contract.

The current absolute metric-drop tolerance of `0.02` is versioned as
`absolute-drop-v1` but remains provisional until the reference set and release policy
are approved. Metric regressions never override or merge with deterministic validator
outcomes.

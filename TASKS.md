# Retrieval skill evaluation: delivery plan

## Goal

Build a repeatable evaluation suite that detects regressions in retrieval quality and
hard retrieval contracts before they reach an agent.

The current project is a proof of concept. It proves the evaluation mechanism against
a controlled fake backend; it does not yet measure the production knowledge server.

## Acceptance criteria

1. A reviewed reference set scores ordered retrieval results using Recall, Precision,
   MRR, and NDCG.
2. Deterministic validators fail exact request, response, safety, and provenance
   contract violations.
3. Runs record enough information to decide whether two scoreboards are comparable,
   and incompatible runs are rejected before regression calculation.
4. The same cases run against the real knowledge server and produce the first real
   baseline.
5. If generated-answer evaluation remains in scope, an LLM judge reports answer
   quality using reviewed rubrics. Judge results report separately and do not gate the
   deterministic build.

Continuous or scheduled execution is required to satisfy the broader goal that quality
"does not silently degrade." CI scheduling, tripwire data, alerting, and sabotage
drills remain a separate delivery story.

## Task status

| # | Task | Status | Depends on |
| --- | --- | --- | --- |
| 1 | Create the GitHub repository and configure ownership | Todo; local Git repository exists, but no remote is configured | — |
| 2 | Create and approve the evaluation approach document | Todo; material exists across the current documentation but is not consolidated | — |
| 3 | Define and approve the retrieval request, caller identity, and response contracts | Approved contract landed (`mcp-tool-contracts-reference.md`): `kb_search`/`kb_fetch`/`kb_related` over a property-graph knowledge base. Harness migrated for `kb_search` only (see `KB-SEARCH-MIGRATION-PLAN.md`); `kb_fetch`/`kb_related` are a follow-up task | 2 |
| 3b | Migrate the harness to `kb_fetch` and `kb_related` | Todo; needs `found:false`-is-not-an-error semantics (kb_fetch) and depth/direction graph traversal + the "Five Canonical Questions" end-to-end recipes (kb_related). Fixture already carries `relationships` for this | 3 |
| 4 | Create and review an exploratory retrieval reference set | POC shape proven; six synthetic cases exist (now against the `kb_search`/paastry domain), labels are not reviewed | 2, 3 |
| 5 | Build the runner, deterministic validators, and ranking metrics | Done for POC | 2, 3, 4 |
| 6 | Set up evaluation version tracking and compatible baseline comparison | Done; versioned manifests, declared target changes, strict compatibility, and synthetic proof are implemented | 5 |
| 7 | Connect to the real knowledge server and record the first real baseline | Waiting on the server and approved contracts | 3, 6 |
| 8 | Define criteria for evaluating generated answers with an LLM judge | Draft exists; unratified | 2 |
| 9 | Build the judge runner through the LLM Gateway with pinned versions | Done for POC; live Gateway configuration is environment-specific | 8 |

## What exists today

### Test data

- `fixtures/corpus.yaml` contains nine synthetic, versioned notes used by the fake
  knowledge server.
- `cases/` contains six scenarios in one ordered sequence. Declared fields determine
  which request, response, retrieval, ranking, and answer checks apply. A case can
  also declare end-to-end answer expectations, a reference answer, and selected
  rubrics under `answer_evaluation` without embedding a generated response.
- `fixtures/agent_responses/` contains synthetic structured responses used until a
  real agent connector supplies the response and retrieval trace.
- Relevance labels use grades `0`, `1`, and `2`; the metric meaning of each grade is
  documented in `README.md`.
- `expect.must_not_return` is a zero-tolerance invariant, separate from relevance grade
  `0`, which means irrelevant but not necessarily harmful.

The case schema requires a note version in every relevance label. Ranking currently
compares note IDs only, however, so version mismatches are not yet detected by metrics
or a dedicated validator.

### Execution

- `harness/runner.py` loads a case, invokes `RetrievalSkill`, captures the emitted
  request, records the response and rendered context, runs validators, and calculates
  ranking metrics.
- Pytest reuses `run_case`, so command-line and pytest execution share the same case
  path.
- The same cases run through three seams:
  - `inprocess`: calls `FakeKnowledgeServer` directly;
  - `mcp`: crosses the MCP schema using an in-memory server transport;
  - `rest`: crosses the FastAPI schema using HTTPX ASGI transport.
- MCP and REST use the shared Pydantic wire definitions in `skill/schemas.py`.

The supported test commands live in `README.md`; pytest is the normal way to run and
inspect the suite.

### Deterministic validators

Six retrieval validators and five captured-answer validators are registered in
`harness/validators/registry.py`.

| Validator | Applies when | Purpose |
| --- | --- | --- |
| `contract:emitted_tool_call` | Every case | The skill emitted the expected query, scope, filters, limit, and format |
| `contract:response_contract_valid` | Every case | The decoded response matches the published schema |
| `contract:server_rejects_invalid_request` | A case declares `probe_invalid_request`; MCP or REST only | Invalid input is rejected at the server trust boundary |
| `retrieval:must_not_return` | A case declares `expect.must_not_return` | Known forbidden results do not leak |
| `retrieval:expected_first_result` | A case declares `expect.expected_first_result` | The explicitly authoritative result ranks first |
| `format:every_result_has_provenance` | Every valid response | Every rendered result contains note-version and source provenance |

The invalid-request validator is skipped in the default in-process mode because that
mode has no protocol boundary. It runs under MCP and REST.

Captured-answer validation is implemented over a response and retrieval trace supplied
from the same execution:

| Validator | Applies when | Purpose |
| --- | --- | --- |
| `answer:response_contract_valid` | Every captured answer | The answer matches the provisional structured response contract and contains nonblank user-visible text |
| `answer:citations_were_retrieved` | Every valid answer | Every citation matches an exact `note@version` actually retrieved |
| `answer:required_citations` | A case declares required citations | Declared authoritative citations are present |
| `answer:must_not_cite` | A case declares forbidden citations | Forbidden or superseded note versions do not reach the final answer |
| `answer:expected_status` | A case declares a status | `answered` or `insufficient_context` matches the exact expectation |

The provisional agent response contract and case-specific answer expectations remain
unratified. The provenance rule is traced to the existing pinned-provenance
requirement.

### Ranking metrics

`harness/ranking_metrics.py` uses `ranx` to calculate Recall at k, Precision at 5,
MRR, and NDCG at k. Metrics are calculated measurements, not pass/fail validators.

The runner currently uses a provisional absolute tolerance of `0.02` when comparing a
run with a baseline. The reference set is too small for a meaningful paired
significance test.

### Reporting

The CLI runner records a versioned run manifest, writes separate synthetic baselines
for each transport, repeats cases with `-n`, and reports `PASS`, `FAIL`, or `FLAKY`
validator verdicts. The manifest separates controlled compatibility inputs, target
versions, and traceability-only run metadata.

Compatibility covers corpus and case content, contracts, orchestration and
result-family code, dependencies, transport, execution configuration, and declared
index, embedding, semantic-asset, and permission-policy versions. Target versions may
differ only through an explicit `change_under_test`. The ranking comparison rejects
changed case or metric inventories before calculating deltas. Framework tests cover
compatible runs, controlled-input changes, declared and undeclared target changes,
case and metric changes, manifest versions, and the tolerance boundary.

The absolute `0.02` regression tolerance remains provisional pending a reviewed
reference set and release policy. Metric regressions affect the CLI exit code but do
not change a case's deterministic validator verdict. Recording the first approved
real baseline remains Task 7.

### LLM judge

`rubrics/faithfulness.yaml`, `rubrics/relevancy.yaml`, and
`rubrics/answer_correctness.yaml` are unratified drafts. The loader, structural
definition checks, prompt builder, strict result schema, Gateway adapter, version
recording, cache, and reporting-only runner exist. No live model is called during a
normal pytest run.

The three criteria concern generated answers, not retrieval rankings:

- faithfulness: is the answer supported by retrieved context;
- relevancy: does the answer address the question;
- answer correctness: does the answer agree with a reference answer, where one exists.

The runner records the configured model and version, actual returned model, prompt and
rubric hashes, evaluation-input hash, fixed temperature, Gateway response ID, and
token usage. Temperature participates in the cache identity. Identical judgments are
cached and scores remain reporting-only.

The captured-agent path evaluates deterministic prerequisites first. Routine judge
calls receive the exact context and final response from the captured execution and are
recorded as `not_run` if retrieval or answer validation failed. It never reruns
retrieval. A diagnostic override can judge a structurally usable failed run.

### LLM judge process

The captured-agent judge path implements this process:

1. Accept one case, captured final response, and retrieval trace. The POC loads
   the response from `fixtures/agent_responses/`; real integration will supply it from
   the agent execution.
2. Validate the structured response, status, and exact citations deterministically.
3. Skip routine LLM calls when retrieval or answer prerequisites failed.
4. Build a judge input containing the question, captured retrieval context, generated
   answer, applicable rubric, and optional reference answer.
5. Apply rubric eligibility: relevancy applies to every valid response, faithfulness
   requires an answered response, and answer correctness requires a reference answer.
6. Require a structured result containing the criterion, score, and explanation.
7. Record the judge model ID, prompt hash, rubric version, and input hash; reuse a
   cached result when those inputs and versions are unchanged.
8. Report judge scores separately from retrieval metrics and deterministic validators.
   Judge scores do not change the deterministic test verdict.

## Remaining work

### 1. Create and approve the evaluation approach document

Create a dedicated approach document that consolidates and receives review for:

- evaluation goals, scope, and explicit non-goals;
- the flow from a case through the skill, transport, server, validators, and metrics;
- the roles of definitions, deterministic validators, ranking metrics, and an optional
  LLM judge;
- reference-set construction and review;
- execution modes and real-server integration;
- version recording, baseline compatibility, and regression policy;
- reporting, ownership, and the boundary with CI and operational monitoring;
- known POC limitations and the criteria for moving beyond the fake backend.

The document should become the reviewed source of truth for the approach. `README.md`
should remain the usage guide, while `TASKS.md` remains the delivery plan.

### 2. Define and approve the retrieval request, caller identity, and response contracts

Resolve and document:

1. Whether the scope field is `product` or `service`.
2. Where `department` belongs in the scope taxonomy.
3. Whether `filters.domain` duplicates `scope.product`.
4. Whether callers may request `derived` knowledge or may only narrow a server-side
   veracity ceiling.
5. Who chooses the output format and which callers may receive dereferenceable source
   pointers.
6. How authenticated caller identity reaches the server. Identity is not currently
   represented in either the case or `RetrieveRequest`.

### 3. Complete the exploratory retrieval reference set

- Name an owner for relevance and forbidden-result labels.
- Decide whether committed fixtures must be synthetic or may contain approved real
  knowledge.
- Agree the target number and distribution of cases; the earlier planning target was
  roughly thirty.
- Review every relevance grade and `must_not_return` label.
- Define how labels are re-reviewed when notes or note versions change.
- Either rank by `note@version` or add a deterministic version validator.

### 4. Connect the real server

- Replace the fake transport target with the real MCP or REST endpoint without
  changing case meaning.
- Confirm authentication and caller identity propagation.
- Run contract cases first, then review whether the retrieval cases remain valid for
  real data.
- Record the first non-mock baseline only after the reference labels are reviewed.

### 5. Complete generated-answer evaluation

The POC runner is implemented. Before expanding it, decide whether answer evaluation
belongs in this retrieval project or in an agent-level evaluation project. If it
remains here:

- define how live answers are generated and captured;
- add reviewed reference answers where answer correctness is required;
- ratify scoring bands and refusal behavior;
- approve the Gateway endpoint, authentication method, pinned model deployment, and
  data-handling policy;
- run and review the first live judgment through the Gateway;
- keep judge results separate from deterministic validators and ranking metrics.

## Decisions retained

- Exact facts and contracts use deterministic validators.
- Retrieval quality uses ranking metrics against reviewed labels.
- Semantic generated-answer quality, if implemented, uses an LLM judge with reviewed
  criteria.
- Validators and metrics are reported separately and are never averaged.
- A judge never replaces exact relevance labels or hard safety checks.
- Mock, MCP, REST, and future real-server baselines are different measurement modes.
- No retry-on-failure behavior hides flakiness.
- CI scheduling and operational alerting are delivered separately from the POC
  harness.

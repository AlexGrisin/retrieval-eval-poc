# Evaluation architecture

> **Migration note**: this document was rewritten for the `kb_search` contract
> (see `KB-SEARCH-MIGRATION-PLAN.md` and `mcp-tool-contracts-reference.md`) through
> §3 "Retrieval output". §§4-9 below still describe the retired `knowledge_retrieve`
> contract (notes, veracity, scope) pending a follow-up documentation pass — tracked
> in `docs/ASSUMPTIONS.md`. The code itself (schemas, validators, runner, cases) is
> fully migrated and verified; only this narrative's tail sections are stale.

## Scope of the current POC

The current system evaluates a **retrieval skill**, not a complete answer-generating
agent. A `kb_search` execution returns ranked entities (property-graph nodes
addressed by `label/key`) and agent-visible rendered context. It does not return a
natural-language answer to the user's question, and it does not yet implement
`kb_fetch` or `kb_related` (see `KB-SEARCH-MIGRATION-PLAN.md`).

Generated-answer expectations and selected judge rubrics live in the same case under
`answer_evaluation`. The POC loads the captured response from
`fixtures/agent_responses/`; the repository does not yet contain the connector that
runs a real answer-generating agent.

## High-level flow

```mermaid
flowchart LR
    Case["test case<br/>question + scope + expectations"]
    Retrieval["run retrieval<br/>real knowledge server over MCP"]
    Output["capture retrieval output<br/>request + ranked notes + context"]
    Validators["validators<br/>exact pass/fail rules"]
    Metrics["ranking metrics<br/>retrieval-quality scores"]
    Answer["captured agent response<br/>fixture or real execution"]
    AnswerValidators["answer validators<br/>exact pass/fail rules"]
    JudgeGate["deterministic prerequisites"]
    Judge["optional LLM judge<br/>answer-quality scores"]
    Report["evaluation report"]

    Case --> Retrieval --> Output
    Output --> Validators --> Report
    Output --> Metrics --> Report
    Output --> AnswerValidators
    Answer --> AnswerValidators
    Validators --> JudgeGate
    AnswerValidators --> JudgeGate
    JudgeGate -->|pass| Judge --> Report
```

In plain language:

1. Load a well-formed test case containing the question, retrieval scope, and expected
   behaviour.
2. Run retrieval against the real knowledge server over MCP and capture what was
   requested and what came back.
3. Use deterministic validators for exact rules and ranking metrics for retrieval
   quality.
4. Optionally combine the retrieved context with a generated answer and ask an LLM
   judge to score semantic answer quality.
5. Report validator outcomes, ranking measurements, and judge scores separately.

The retrieval test itself still produces notes and context only. Synthetic captured
responses exercise deterministic answer checks and judge routing. In the target flow,
the capture comes from the real agent.

## Complete test flow

```mermaid
flowchart TD
    Case["evaluation case<br/>input + expected outcomes + judge selection"]
    Definition["definition validation<br/>harness/definitions/"]
    Runner["shared execution<br/>harness/runner.py"]
    Skill["RetrievalSkill<br/>build request"]
    Spy["recording client<br/>capture emitted call"]
    MCP["MCPKnowledgeClient<br/>real MCP boundary"]

    ResponseSchema["published response schema<br/>skill/schemas.py"]
    Server["real knowledge server<br/>MCP streamable HTTP"]
    Decode["decode + render<br/>skill/"]
    Captured["captured retrieval result<br/>ranked notes + facets + rendered context"]

    Expectations["evaluation-only expectations<br/>expect.*"]
    Validators["deterministic validators<br/>pass / fail / skip"]
    Metrics["ranking metrics<br/>numeric measurements"]
    Verdict["retrieval verdict<br/>PASS / FAIL / FLAKY"]
    Baseline["optional compatible<br/>baseline comparison"]

    CapturedAnswer["captured structured answer<br/>fixture or agent adapter"]
    AnswerValidators["deterministic answer validators<br/>schema + status + citations"]
    JudgeGate["deterministic judge prerequisites"]
    Rubric["semantic criterion<br/>rubrics/*.yaml"]
    JudgeInput["versioned judge input<br/>question + context + answer + rubric"]
    Gateway["LLM Gateway<br/>strict JSON result"]
    JudgeReport["judge score + explanation<br/>reporting-only"]

    Case --> Definition --> Runner --> Skill --> Spy
    Spy --> MCP --> Server
    Server -->|kb_search response| ResponseSchema --> Decode
    Decode --> Captured

    Case -.-> Expectations
    Expectations --> Validators
    Expectations --> Metrics
    Captured --> Validators --> Verdict
    Captured --> Metrics --> Baseline

    Captured --> AnswerValidators
    Case --> AnswerValidators
    CapturedAnswer --> AnswerValidators
    Verdict --> JudgeGate
    AnswerValidators --> JudgeGate
    JudgeGate -->|valid routine run| JudgeInput
    Rubric --> JudgeInput
    JudgeInput --> Gateway --> JudgeReport
```

The branches answer different questions and are deliberately not averaged together:

| Branch | Question | Result | Can currently fail deterministic evaluation? |
| --- | --- | --- | --- |
| Definition validation | Is the test data well formed? | Valid definition or error | Yes, before execution |
| Deterministic validators | Did an exact contract or invariant hold? | Pass, fail, or skip | Yes |
| Ranking metrics | How good was the ordered result set? | Recall, precision, MRR, NDCG | Only through the CLI baseline comparison |
| LLM judge | Is a generated answer semantically good? | Score and explanation | No; reporting-only |

## 1. Retrieval test input

A file in `cases/` contains both execution input and evaluation-only expectations.
`harness/definitions/cases.py` rejects missing required fields, unknown keys, malformed
case filenames, invalid grades, and duplicate relevance labels before the retrieval
skill is called. The filename stem becomes the internal case ID.

[CASE_TEMPLATE.md](CASE_TEMPLATE.md) is the canonical authoring reference for every
supported case field, value, default, and applicability rule.

| Case data | Purpose | Sent to the retrieval skill or server? |
| --- | --- | --- |
| `query` | User's retrieval question | Yes |
| `domain` | The one domain the call is scoped to | Yes |
| `limit` | Maximum number of results | Yes |
| `expect_tool_call` | Optional exact request override | No; validator input only |
| `expect.relevant` | Graded retrieval reference labels (`Label/key` entity identities) | No; metric input only |
| `expect.must_not_return` | Forbidden entity identities | No; validator input only |
| `expect.expected_first_result` | Required first entity | No; validator input only |
| `answer_evaluation.expect` | Exact status and citation expectations for the final answer | No; answer-validator input only |
| `answer_evaluation.rubrics` | Semantic criteria selected for this case | No; judge routing only |
| `answer_evaluation.reference_answer` | Optional reviewed comparison answer | No; judge input only |
| `probe_invalid_request` | Deliberately malformed boundary request | Sent separately, directly to the MCP boundary |
| `persona` | ID of a `personas/<id>.yaml` entry (`id`, `name`, `description`, `traits`) | No; recorded in the run trace and Allure evidence only |
| Case filename, `title`, `why` | Evaluation identity and purpose | No |

Every case declares a `persona` -- who the case represents, resolved against the
`personas/*.yaml` registry (`harness/definitions/personas.py`, cross-checked the same way
`answer_evaluation.rubrics` is checked against `rubrics/*.yaml`) -- but that declaration
is reporting-only: it is not sent as a request argument, and no validator or scoping
check consumes it yet. A persona's `description`/`traits` exist for future consumers
(persona-specific phrasing, persona-aware judging) that do not exist yet. Authenticated
caller identity is not represented in the request itself. Caller identity propagation
and server-side authorization cannot be claimed as tested until the approved request
schema defines that representation and the knowledge server implements caller-aware
scoping; see `docs/ASSUMPTIONS.md`.

## 2. Request construction and schema enforcement

`SearchSkill` turns case input into this MCP tool call:

```json
{
  "tool": "kb_search",
  "args": {
    "domain": "paastry",
    "query": "why was the pricing rounding bug fixed?",
    "limit": 10
  }
}
```

The recording client (`SpyClient`) captures this call before forwarding it over MCP.
That captured call is what `contract:emitted_tool_call` validates; the harness does not
infer what was sent from the response.

Two representations of the retrieval contract, deliberately kept independent:

| Layer | Contract | Responsibility |
| --- | --- | --- |
| Skill internals | Dataclasses in `skill/contracts.py` | Validate nonblank domain/query, positive `limit`; build the exact tool call |
| Published response | Pydantic models in `skill/schemas.py` | Reject a renamed, missing, or wrongly typed output field once the response has been decoded |

`MCPKnowledgeClient` is the only `KnowledgeClient` implementation; there is no
in-process or REST seam. A case with `probe_invalid_request` bypasses the skill and
sends its malformed request directly to the real server's MCP endpoint. This proves
rejection by the server-facing contract rather than only by trusted client code.
`kb_search` has no nested request object (unlike the retired `filters`), so the
enforceable probe surface is per-argument type checking, not unknown-key rejection --
see `harness/validators/contract.py::check_server_rejects_invalid_request`.

## 3. Retrieval output and captured execution record

The knowledge server's `kb_search` response wraps its hits under `result` (singular) --
confirmed against a live call, not merely documented:

```json
{
  "result": [
    {
      "entity": {"label": "Story", "key": "PAAS-201"},
      "title": "Fix pricing rounding error for tiered discounts",
      "snippet": "Customers on tiered discount plans were undercharged...",
      "score": 0.24,
      "matched_by": "vector",
      "citations": [{"source_system": "jira", "reference": "PAAS-201"}]
    }
  ]
}
```

`skill/client.py::_response_from_payload` is the one place this wire dict becomes a
`SearchResponse`, keyed strictly on `result` -- accepting an alternate spelling would
let the server rename the envelope without any test noticing. `SearchResponseOut`
(`skill/schemas.py`) then validates the *decoded* shape (`response.as_dict()`, which is
always `results`, plural -- the skill's own internal contract, not the wire spelling):
entity identity (`label` + `key`), title, snippet, score, `matched_by`, and citations,
with `extra="forbid"` rejecting anything else.

The skill decodes the response into the transport-independent objects in
`skill/contracts.py`, then `skill/formatter.py` derives human-readable `rendered`
context. The rendered value is what a future answer-generating agent would consume:

```text
### Knowledge — 1 entity · domain paastry
1. Fix pricing rounding error for tiered discounts   [Story/PAAS-201 · fulltext]
   > "Customers on tiered discount plans were undercharged..."
   citations: jira:PAAS-201
```

It is **retrieved context, not the final answer**.

The runner captures an evaluation record containing:

- ranked entity identities (`Label/key`);
- the structured results;
- the rendered context;
- the original query and domain;
- the exact emitted tool call and call count;
- every validator outcome and its traceability source;
- ranking metrics where relevance labels exist;
- the final deterministic verdict.

## 4. Deterministic validators

Definitions answer “is the test itself valid?” Validators answer “did the executed
system behave correctly?” Each runtime validator is registered with a requirement
source and records `ok`, `fail`, or `skip`.

| Validator | Input inspected | Applicability | What failure means |
| --- | --- | --- | --- |
| `contract:emitted_tool_call` | Captured request and case input | Every case | Query, scope, filters, limit, format, or tool name changed or was dropped |
| `contract:server_rejects_invalid_request` | Direct malformed probe and server response | Cases with `probe_invalid_request` | The server trust boundary accepted invalid input or rejected it for the wrong reason |
| `contract:response_contract_valid` | Decoded response or retrieval error | Every case | No valid response was decoded, or required output is missing, renamed, extra, or wrongly typed |
| `retrieval:must_not_return` | Ranked note IDs and `expect.must_not_return` | When declared | Forbidden, superseded, unverified, or out-of-scope knowledge leaked |
| `retrieval:expected_first_result` | First ranked note and the declared expectation | When declared | The explicitly authoritative result did not rank first |
| `format:every_result_has_provenance` | Rendered context and structured results | Every execution with a response | A note-version or original-source reference was lost during formatting |

Any failed validator adds an invariant failure and makes the case fail. When the CLI
repeats a case, all passes produce `PASS`, all failures produce `FAIL`, and mixed
results produce `FLAKY`. A skipped check is visible but is not treated as a pass.

## 5. Ranking metrics

Ranking metrics compare the returned note order with `expect.relevant`. These labels
are test oracle data and are never sent to the retrieval system.

```text
returned ranked note IDs + per-query relevance grades
                         ↓
       Recall@k, Precision@5, MRR, NDCG@k
```

Grades `1` and `2` count as relevant. NDCG additionally gives grade `2` more gain than
grade `1`. Unlisted notes are currently treated as irrelevant. `must_not_return` is
not a grade: it is a zero-tolerance deterministic invariant.

| Metric | Business meaning | Current calculation |
| --- | --- | --- |
| Recall@k | Did retrieval find all known useful knowledge needed by the agent? | Notes graded `1` or `2` found in the first `k` results, divided by all notes graded `1` or `2`. `k` comes from the case. |
| Precision@5 | How much of the first five context positions is useful rather than noise? | Notes graded `1` or `2` in the first five positions, divided by `5`. Missing positions and unlisted notes count as not relevant. |
| MRR | How quickly does the agent encounter its first useful result? | `1 / rank` of the first note graded `1` or `2`; `0` when no relevant note is returned. |
| NDCG@k | Are the best notes presented before weaker and irrelevant notes? | Discounted gain of the returned ranking through `k`, divided by the best possible ranking for the same labels. |

| Grade | Meaning | How metrics use it |
| --- | --- | --- |
| `2` | Directly answers the question | Relevant for every metric; higher gain in NDCG |
| `1` | Materially useful but insufficient on its own | Relevant for every metric; lower gain in NDCG |
| `0` | Not relevant | Not relevant for every metric |
| Unlisted | No relevance label exists for the note in that case | Currently treated as not relevant |

`run_case()` calculates the metrics whenever a case declares `expect.relevant`.
Pytest currently verifies
the `ranx` adapter with explicit known examples; it does not apply a per-case metric
threshold. The CLI can compare calculated metrics with a compatible baseline, and a
regression beyond tolerance can affect the CLI exit status without changing the
deterministic validator verdict.

### Run manifest and compatible baseline comparison

Each CLI run records a versioned manifest rather than treating every recorded version
as one undifferentiated fingerprint:

```text
compatibility inputs     target under evaluation       run metadata
must match               may differ when declared      traceability only
        \                       |                         /
         +---------------- baseline comparison --------+
```

The compatibility section records the evaluation profile and level, case and
relevance-label content, request/response contracts, orchestration code, dependency
lock, transport, and execution count as instrument-computed facts; corpus snapshot,
environment class, index and embedding configuration, vocabulary, ontology, and
permission policy are operator-supplied, since the live server reports none of them
itself (confirmed: `/healthz` returns only `{"status": "ok"}`, `/version` 404s). The
target section records the Retrieval Skill version (hashed, ours) plus the Knowledge
Server, graph/vector store, index build, and retrieval configuration versions
(operator-supplied). The run section records values such as execution time that
support attribution but do not invalidate a functional comparison.

Target differences are rejected unless the current run declares the exact
`target.<field>` as its `change_under_test`. Controlled inputs cannot be waived this
way. This allows a server upgrade to be evaluated while preventing an unnoticed
corpus, case, contract, dependency, or measurement change from being attributed to
that upgrade.

Compatibility is result-specific. The implemented CLI comparison uses the ranking
profile and additionally requires identical case IDs and per-case metric names.
Added, removed, renamed, or newly applicable cases or metrics require a new reviewed
baseline; the runner never compares only their intersection. Unknown manifest
versions, missing required fields, undeclared target changes, and malformed baseline
files are rejected before metric deltas are calculated.

`--write-baseline`/`--baseline` refuse to run without this metadata --
`harness/baselines.py::missing_required_system_metadata` names every missing dotted
path -- since the harness has no way to verify what the operator states. A plain
evaluation run (no baseline flags) needs none of this. Recording the first approved
real baseline is a reviewed decision separate from this mechanism enforcing it.

The required `--system-metadata` shape:

```json
{
  "compatibility": {
    "evaluation_level": "integration",
    "environment_class": "production-read-only",
    "corpus_snapshot": "knowledge-repo@8f31c2a",
    "index_schema_version": "graph-v4",
    "chunking_version": "chunks-v2",
    "embedding_model": "approved-embedding-deployment",
    "embedding_model_version": "2026-08-01",
    "embedding_dimensions": 1536,
    "vocabulary_version": "vocabulary@17",
    "ontology_version": "ontology@9",
    "permission_policy_version": "retrieval-policy@12"
  },
  "target": {
    "knowledge_server_version": "2.4.0",
    "retrieval_skill_version": "1.8.0",
    "graph_vector_store": "selected-store",
    "graph_vector_store_version": "reported-version",
    "index_build_id": "index-2026-08-28-01",
    "retrieval_configuration_version": "hybrid-retrieval-v3"
  },
  "run": {
    "environment": "production",
    "region": "reported-region",
    "trace_id": "evaluation-trace-id"
  }
}
```

## 6. Generated-answer evaluation

The judge evaluates answer quality, not retrieval ranking. A case's optional
`answer_evaluation` section declares exact answer expectations, applicable semantic
rubrics, and an optional reference answer. It does not contain a generated answer.
The POC pairs the case with a structured response from `fixtures/agent_responses/`.
A real integration supplies the response and retrieval trace from the agent execution
instead. `evaluate_agent_response()` never reruns retrieval.

The provisional response contract contains:

```json
{
  "status": "answered",
  "answer": "Only retryable payment failures may be retried...",
  "citations": [
    {"note_id": "n-0002", "version": 1}
  ]
}
```

Five deterministic answer validators check the response contract (including nonblank
text), structured status, citations actually retrieved, required citations, and
forbidden citations. Their outcomes join the retrieval verdict in one `AgentRun`.

`run_agent_judges()` uses the question, context, and answer already present in that
captured run. Routine judging produces explicit `not_run` outcomes when retrieval or
answer prerequisites failed. `judge_failed_runs=True` is a deliberate diagnostic
override for structurally usable failures. Otherwise it runs exactly the rubrics
listed in the case's `answer_evaluation.rubrics`, in declaration order. No rubric is
inferred or suppressed from response status or reference data.

| Criterion | Case-author selection guidance | Question it answers |
| --- | --- | --- |
| Faithfulness | Select when the expected answer status is `answered`. | Is every answer claim supported by the retrieved context? |
| Answer correctness | Select when the case supplies a reviewed reference answer. | Does the generated answer agree with the reviewed reference answer? |
| Relevancy | Select when answer-to-question relevance should be scored. | Does the generated answer directly and sufficiently address the user's question? |

For each rubric, the runner builds this `JudgeInput`:

```json
{
  "case_id": "case-001-retries-ranking",
  "criterion": "faithfulness",
  "question": "how do we handle retries on payment failures?",
  "retrieved_context": "<rendered notes and provenance>",
  "generated_answer": "Only retryable payment failures may be retried...",
  "reference_answer": "<reviewed comparison answer>"
}
```

The versioned prompt adds the selected rubric's description and anchored scoring
criteria. Evaluation data is labelled as untrusted so instructions inside retrieved
content or an answer are not followed. Relevance labels, deterministic validator
outcomes, ranking metrics, forbidden-note expectations, and baseline results are not
sent to the LLM judge.

### Gateway request and result schema

The Gateway receives the model ID, complete prompt, `temperature: 0`, `store: false`,
and a strict JSON Schema. `LLM_GATEWAY_TOKEN` is sent only as the HTTP Bearer
credential, never inside the prompt.

The model must return exactly:

```json
{
  "criterion": "faithfulness",
  "score": 1.0,
  "explanation": "Every answer claim is supported by the retrieved notes."
}
```

The output schema forbids additional fields, restricts `criterion` to the requested
rubric, constrains `score` to `0..1`, and requires a nonblank explanation. Malformed
structured output fails the judge execution.

The saved judge record also contains requested and actual model IDs, model version,
prompt version, temperature, hashes of the prompt, rubric and input, cache key,
Gateway response ID, usage, cache status, and whether the underlying retrieval
execution passed.
Identical inputs and versions reuse the content-addressed cache.

Rubric thresholds are present in rubric definitions but do not currently gate pytest,
the retrieval verdict, metrics, baseline comparison, or process exit status. A normal
pytest run exercises none of the judge machinery at all -- `judge`-marked tests are
deselected unless `--judge` explicitly enables the live call.

## 7. How pytest executes the architecture

Every test in `tests/` is `evaluation`-marked and runs against the real knowledge
server (and, for judge tests, the real LLM Gateway). There is no offline harness
self-test layer: pytest here is an orchestration and reporting layer over the same
`run_case()` function used by the harness runner, always against a live target.

1. `test_01_definitions.py::test_committed_case_is_valid` validates every committed
   case's shape before anything runs.
2. The session-scoped `case_executions` store in `harness/execution.py` executes
   lazily by case and caches each capture, running retrieval against the real
   knowledge server and loading a saved answer fixture when needed; a real agent
   provider will invoke the agent and capture both outputs instead.
   `test_02_retrieval.py` reports retrieval validators over the captured result.
3. `captured_runs` converts each answer-enabled execution into the shared input for
   `test_03_answer.py`, which applies exact answer validators and judge prerequisites.
4. `test_04_ranking.py` reports each metric calculated for a case with relevance
   labels. Metrics have no per-case pytest quality threshold yet.
5. `test_05_judges.py` consumes the same captured runs to call the live LLM Gateway.
   Its one test is `judge`-marked and deselected unless `--judge` is supplied.

Evaluation items are collected case-first. Within each case, verbose pytest output
follows definition, request, response, expectation, answer, ranking, and judge order.
Case-driven parameter IDs use `case:level:check`; `suite` identifies repository-wide
checks. Selecting one case with `-k` does not execute the others.

`--server-url` (default `http://127.0.0.1:8000/mcp`, overridable via `KS_SERVER_URL`
in `.env` or the environment) and `--judge` can be combined without changing case
definitions.

Every run is single-process: pytest-xdist is not a dependency, and
`tests/conftest.py::pytest_sessionstart` refuses `-n` unconditionally. Parallel
workers would give each worker its own session cache and could execute the same real
case against the real server more than once.

## 8. Target end-to-end flow with the real agent

The captured-run evaluator and judge routing now exist. When the answer-generating
agent is connected, an adapter must supply both its retrieval trace and final answer:

```mermaid
flowchart LR
    Input["test question + caller context"]
    Agent["real answer-generating agent"]
    Retrieval["retrieval tool / MCP server"]
    Trace["captured request + ranked notes<br/>facets + rendered context"]
    Final["captured final answer"]
    DV["deterministic validators"]
    RM["ranking metrics"]
    LJ["LLM judge"]

    Input --> Agent
    Agent --> Retrieval --> Trace
    Trace --> Agent --> Final
    Trace --> DV
    Final --> DV
    Trace --> RM
    Input --> LJ
    Trace --> LJ
    Final --> LJ
    DV -->|pass| LJ
```

In that architecture:

1. The retrieval trace remains the input to deterministic validators and ranking
   metrics.
2. The actual final answer replaces the structured response fixture for live runs.
3. The judge receives the original question, the context actually available to the
   agent, and the answer actually returned by the agent.
4. Judge scores remain separate from exact contract failures unless an explicit,
   reviewed gating policy is introduced.

## 9. Ownership map

| Concern | Current owner |
| --- | --- |
| Case shape, reference labels, answer expectations, and rubric selection | `cases/*.yaml`, `harness/definitions/cases.py` |
| Synthetic agent-response fixtures | `fixtures/agent_responses/*.yaml`, `harness/definitions/agent_responses.py` |
| Rubric shape and content | `rubrics/*.yaml`, `harness/definitions/rubrics.py` |
| Persona shape and content (reporting only; not yet enforced) | `personas/*.yaml`, `harness/definitions/personas.py` |
| Internal request/response objects | `skill/contracts.py` |
| Published response wire schema | `skill/schemas.py` |
| Request construction and response rendering | `skill/skill.py`, `skill/formatter.py` |
| MCP client and emitted-call capture | `skill/client.py` |
| Shared execution and retrieval record | `harness/runner.py` |
| Lazy one-execution-per-case storage and captured views | `harness/execution.py` |
| Provisional agent response and captured-run evaluation | `harness/agent/*.py` |
| Deterministic validators and traceability | `harness/validators/*.py` |
| Ranking measurements | `harness/ranking_metrics.py` |
| Judge prompt, schema, Gateway, cache, and record | `harness/judges/*.py` |
| Pytest orchestration and reporting | `tests/*.py` |

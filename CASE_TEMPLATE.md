# Evaluation case template

Each file in `cases/` defines one evaluation scenario: runtime input, exact expected
outcomes, optional relevance labels, and optional generated-answer judging criteria.
The case is the source of truth; expectations are evaluation-only data and are never
sent to the retrieval system or agent.

## Complete template

This template shows the fields used by routine cases. Remove optional fields that do
not apply. The filename is the case ID, for example
`cases/case-004-unknown-filter-rejected.yaml`.
Advanced request overrides are documented separately below.

```yaml
# Required purpose
title: Short scenario name        # nonblank human-readable text
why: >-                           # nonblank business reason for keeping this case
  Explain the failure or regression this case is intended to detect.

# Required runtime input
query: What should the agent retrieve?  # nonblank string
caller:
  department: commerce           # required nonblank scope value
  product: shop                  # optional nonblank string or null

# Optional runtime input; defaults are shown
filters:
  veracity: [verified]           # optional list: verified and/or derived
  validity: current              # optional string; default: current
k: 10                            # optional positive integer; default: 10
format: full                     # optional: brief | full | citations_only; default: full

# Optional retrieval expectations; include only applicable checks/labels
expect:
  relevant:                      # nonempty graded reference set; enables ranking metrics
    - note: n-0001               # nonblank note ID; unique within relevant
      version: 3                 # positive integer
      grade: 2                   # 0 | 1 | 2
  must_not_return: [n-0004]      # note IDs that must be absent at every rank
  expected_first_result: n-0001  # exact note ID required at rank 1

# Optional deliberately malformed server probe; runs only over MCP or REST
probe_invalid_request:
  filters:
    unknown_filter: rejected-value

# Optional deterministic final-answer expectations and LLM-judge selection
answer_evaluation:
  expect:
    status: answered              # optional: answered | insufficient_context
    required_citations:           # optional unique exact note-version references
      - note_id: n-0001
        version: 3
    must_not_cite:                # optional unique exact note-version references
      - note_id: n-0004
        version: 1
  rubrics:                        # required nonempty unique list when section exists
    - faithfulness
    - relevancy
    - answer_correctness
  reference_answer: >-            # optional nonblank text; required by answer_correctness
    State the reviewed answer against which semantic correctness is judged.
```

## File and identity rules

| Rule | Requirement |
| --- | --- |
| Filename and ID | `case-NNN-description.yaml`, with a three-digit number and lowercase kebab-case description. The filename stem becomes the case ID. |
| Numbering | One sequence starts at `001` and remains contiguous: `case-001-...`, `case-002-...`, and so on. |
| Unknown fields | Rejected at the top level, under `expect`, and in answer-evaluation models. |

### Naming convention

Use `case-NNN-observable-behavior.yaml`:

- `NNN` is the case's position in the single contiguous sequence.
- The description uses lowercase kebab case and names the scenario or expected
  observable outcome.
- Prefer specific behavior such as `unknown-filter-rejected`,
  `superseded-knowledge-excluded`, or `current-guidance-ranked-first` over a broad
  implementation area such as `skill`, `retrieval`, or `request-contract`.
- Use outcome words for negative and boundary cases: `rejected`, `excluded`,
  `required`, or `ranked-first`.
- Keep one primary scenario per case. Always-on request, response, and provenance
  validators do not need to be repeated in the filename.

The YAML `title` should express the same behavior in readable prose, while `why`
describes the business risk that makes the case worth retaining.

## Top-level fields

| Field | Required | Allowed values and default | Meaning | Sent at runtime? |
| --- | --- | --- | --- | --- |
| `title` | Yes | Nonblank string | Short scenario name used by people reviewing the suite. | No |
| `why` | Yes | Nonblank string | Business risk or regression the case exists to detect. | No |
| `query` | Yes | Nonblank string | User question supplied to retrieval; later also supplied to the answer judge. | Yes |
| `caller` | Yes | Mapping described below | Retrieval scope. | Yes |
| `filters` | No | Mapping; omitted means default filters | Retrieval constraints. Only the closed keys below are accepted by the retrieval contract. | Yes |
| `k` | No | Positive integer; default `10` | Maximum number of retrieval results requested and cutoff for Recall/NDCG. | Yes |
| `format` | No | `brief`, `full`, or `citations_only`; default `full` | Agent-visible retrieval rendering format. | Yes |
| `expect` | No | Mapping; default `{}` | Retrieval invariants and human relevance labels. | No |
| `expect_tool_call` | No | Exact tool-call mapping | Overrides the automatically derived emitted-call expectation. | No |
| `probe_invalid_request` | No | Deliberately malformed request fields | Bypasses the skill and checks that the MCP/REST server rejects invalid input. | Sent only as the separate probe |
| `answer_evaluation` | No | Mapping described below | Exact answer expectations, selected judge rubrics, and optional reference answer. | No; its selected inputs are used by validators/judges |

## Caller fields

| Field | Required | Allowed values | Meaning |
| --- | --- | --- | --- |
| `department` | Yes | Nonblank string | Retrieval scope sent as `scope.department`. |
| `product` | No | Nonblank string or `null`; default `null` | More specific retrieval scope sent as `scope.product`. |

## Filter fields

The filter vocabulary is closed. An unknown key in a normal request is an error, not
something the server may silently ignore.

| Field | Required | Allowed values and default | Meaning |
| --- | --- | --- | --- |
| `veracity` | No | List containing `verified`, `derived`, or both; omitted means no explicit veracity filter | Restricts results by verification state. |
| `validity` | No | String; default `current` | Selects the requested validity view. The current contract does not yet define a closed enum beyond the conventional `current` value. |

## Retrieval expectations

| Field | Required | Allowed values | Effect |
| --- | --- | --- | --- |
| `expect.relevant` | No | Nonempty list of unique note labels containing `note`, positive `version`, and `grade` `0`, `1`, or `2` | Enables Recall, Precision, MRR, and NDCG. Grades are query-specific. The version is stored and shape-validated, but current ranking calculations compare note ID only. |
| `expect.must_not_return` | No | List of note IDs | Adds a zero-tolerance validator: any listed note in the results fails the case. |
| `expect.expected_first_result` | No | One nonblank note ID | Requires that note to occupy rank 1. An empty result also fails. |

Relevance grades have these meanings:

| Grade | Meaning | Metric treatment |
| --- | --- | --- |
| `2` | Directly answers the question | Relevant to all metrics and receives greater NDCG gain. |
| `1` | Materially useful but insufficient alone | Relevant to all metrics and receives lower NDCG gain. |
| `0` | Not relevant | Not relevant to any metric. |
| Unlisted | No label for this query-note pair | Currently treated as not relevant. |

`must_not_return` is not grade `0`. Grade `0` means irrelevant; a forbidden note is a
defect regardless of its rank.

## Exact emitted-call expectation

Normally, the harness derives the expected call from `query`, `caller`, `filters`,
`k`, and `format`. Use `expect_tool_call` only when the scenario needs to state the
entire exact request explicitly. Its currently supported tool is
`knowledge_retrieve`; `args` should contain the complete expected request rather than
only the field being emphasized.

```yaml
expect_tool_call:
  tool: knowledge_retrieve
  args:
    query: What should the agent retrieve?
    scope:
      department: commerce
      product: shop
    filters:
      veracity: [verified]
      validity: current
    k: 10
    format: full
```

## Invalid-request probe

`probe_invalid_request` intentionally has no closed value set: its purpose is to
contain a malformed field or value such as a blank `query`, an unknown filter, an
invalid `k`, or an unsupported `format`. The harness combines it with the case's
otherwise valid request and sends it directly to the server, bypassing the skill.
The rejection validator runs only with `--transport mcp` or `--transport rest`; it is
not applicable to `inprocess` execution.

## Generated-answer evaluation

| Field | Required | Allowed values and default | Effect |
| --- | --- | --- | --- |
| `answer_evaluation.expect` | No | Mapping; default `{}` | Groups exact deterministic answer expectations. |
| `answer_evaluation.expect.status` | No | `answered` or `insufficient_context` | Requires the captured structured response to have exactly this status. |
| `answer_evaluation.expect.required_citations` | No | Unique list of `{note_id: <nonblank string>, version: <positive integer>}`; default `[]` | Requires every exact note-version citation. |
| `answer_evaluation.expect.must_not_cite` | No | Same citation shape; default `[]` | Forbids every exact note-version citation. A citation cannot be both required and forbidden. |
| `answer_evaluation.rubrics` | Yes when `answer_evaluation` exists | Nonempty unique list. Current rubric names: `faithfulness`, `relevancy`, `answer_correctness` | Selects the LLM-judge criteria for this case. |
| `answer_evaluation.reference_answer` | No | Nonblank string or omitted | Reviewed semantic comparison target. Required when `answer_correctness` is selected. |

The rubric list is authoritative. The runner executes exactly the declared rubrics,
in declaration order; it does not infer additional criteria or suppress declared
ones. Case authors should select `faithfulness` for answered responses, select
`answer_correctness` only with a reviewed reference answer, and select `relevancy`
when answer-to-question relevance should be scored.

The generated answer itself does not belong in the case. During the POC it comes from
`fixtures/agent_responses/<case-id>.yaml`; real integration replaces that fixture
with the final answer and retrieval trace captured from the same agent execution.

## What each declaration activates

| Declaration | Evaluation activated |
| --- | --- |
| Every valid case | Definition validation, emitted-call validation, response-contract validation, and result-provenance validation |
| `probe_invalid_request` | Server-rejection validation over MCP/REST |
| `expect.must_not_return` | Forbidden-result validation |
| `expect.expected_first_result` | First-result validation |
| `expect.relevant` | Recall, Precision, MRR, and NDCG calculation |
| `answer_evaluation` | Deterministic final-answer validation and the selected optional LLM-judge rubrics |

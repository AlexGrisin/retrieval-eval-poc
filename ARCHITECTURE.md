# Architecture

## Evaluation boundary

The system under evaluation is the complete deployed read path:

```text
question
  -> Claude Code `/okf-knowledge`
  -> packaged `sdp-context:librarian`
  -> real Knowledge Server MCP tools
  -> ingested PostgreSQL graph and notes
  -> final user-visible answer
```

There is no in-repository retrieval implementation. The plugin directory and MCP
configuration are runtime inputs, so the evidence comes from the same artifacts used
by the application.

## One execution per case

`tests/conftest.py` owns a session cache keyed by case ID. The first check for a case
starts a fresh Claude process; all deterministic checks and optional judges consume
that captured execution. This prevents retrieval, answer checking, and judging from
observing different model runs.

`harness/agent/claude_target.py`:

1. invokes `/okf-knowledge` with the authored question and domain;
2. loads the real plugin and strict MCP configuration;
3. permits only the skill and read-only Knowledge Server tools;
4. parses Claude's stream-JSON tool calls, results, answer, model and usage;
5. evaluates tool policy, retrieved entities, citations and answer requirements.

## Test levels

- `framework`: offline parser and validator self-tests. These prove that the
  measuring instrument recognizes the evidence shapes it claims to check.
- `agent_target`: live application cases. These require the real server and Claude.
- `judge`: optional semantic scoring over the already captured live answer.

The default run includes `framework` and `agent_target`; judge tests are deselected
unless `--judge` is supplied.

## Failure attribution

- Server health fails before Claude starts: environment or corpus service problem.
- Required tool call missing/wrong: deployed skill planning problem.
- Required entity absent despite correct call: Knowledge Server or corpus problem.
- Entity retrieved but answer/citation missing: deployed answer synthesis problem.
- Framework self-test failure: evaluator problem; live findings are not trustworthy
  until it is repaired.

## Source layout

```text
cases/                        deployed behavioral scenarios
harness/agent/               Claude execution capture and answer evaluation
harness/definitions/         case, persona and rubric validation
harness/judges/              optional semantic judges and cache
harness/validators/answer.py deterministic answer checks
tests/test_framework.py       offline evaluator self-tests
tests/test_deployed_skill.py  live deployed-skill cases
tests/test_live_judges.py     optional semantic judges
rubrics/                      semantic judge definitions
personas/                     case persona definitions
```

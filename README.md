# Deployed knowledge-skill evaluation

This repository evaluates the real `/okf-knowledge` skill against the real Knowledge
Server and its ingested PostgreSQL corpus. It does not contain a surrogate retrieval
skill, fake corpus, or fake server.

```text
cases/*.yaml
        |
fresh Claude Code process + real sdp-context plugin
        |
read-only kb_search / kb_fetch / kb_related calls over MCP
        |
Knowledge Server at the URL in plugins/sdp-context/.mcp.json
        |
captured tool trace + final answer -> deterministic checks -> optional LLM judges
```

## What is tested

Eight deployed scenarios cover canonical and typo-tolerant SDP ownership, dependency
impact, change rationale, test coverage, honest refusal, plus Paastry ownership and
on-call facts. Each case can assert:

- exact or partial MCP tool arguments;
- required and forbidden tools;
- a maximum retrieval-call budget;
- required or forbidden retrieved entities;
- answer status, citations, required and forbidden phrases, and the stable
  `Coverage:`/`Sources:` footer format;
- optional semantic rubrics through the configured LLM Gateway.

The target denies filesystem, shell, and web tools. Retrieval and the final answer are
captured from the same Claude execution. It loads only project-level Claude settings,
not user or local hooks, so workstation customizations cannot alter an evaluation
answer.

## Prerequisites

1. The workspace Knowledge Server must be running with the `sdp` and `paastry`
   domains ingested.
2. Claude Code must be installed and authenticated. An Anthropic API key is not
   required when the CLI is signed in interactively.
3. Python 3.12+ and the project development dependencies must be installed.

Start and verify the real server:

```bash
cd /Users/agrisin/projects/sysco/ai-sdlc/context-engineering/sysco-context-layer
make pg-up
make server-start
curl -sf http://127.0.0.1:8000/healthz
```

The evaluator performs the same health check before launching Claude. It reads the
server URL from the selected plugin's `.mcp.json`.

## Run

From this repository:

```bash
env -u ANTHROPIC_API_KEY .venv/bin/pytest -q
```

That selects seven offline framework self-tests and eight live deployed-skill cases.
The environment prefix is only needed when a stale `ANTHROPIC_API_KEY` would override
an authenticated Claude login.

Run one live case while iterating:

```bash
env -u ANTHROPIC_API_KEY .venv/bin/pytest \
  -m agent_target \
  -k case-001-sdp-ownership \
  -vv -s
```

Run only the fast evaluator self-tests; these do not need Claude or the server:

```bash
.venv/bin/pytest -m framework -q
```

List tests without running them:

```bash
.venv/bin/pytest --collect-only -q
```

Live cases run sequentially and normally take several minutes. Parallel workers are
rejected for live cases so one case/trial is never executed more than once. Use
`--agent-timeout 90` to shorten the default 300-second per-case timeout.

## Reproducibility options

The evaluator defaults to the plugin in the sibling workspace. Override inputs when
needed:

```bash
env -u ANTHROPIC_API_KEY .venv/bin/pytest \
  --agent-model '<pinned-model>' \
  --agent-effort high \
  --plugin-dir /path/to/plugins/sdp-context \
  --mcp-config /path/to/plugins/sdp-context/.mcp.json
```

For an important regression run, repeat every selected case in fresh Claude
processes. Each attempt is an independent result, not a retry: a `2/3` outcome means
one trial failed.

```bash
env -u ANTHROPIC_API_KEY .venv/bin/pytest -m agent_target --trials 3
```

## Optional semantic judges

Deterministic checks are always the release gate. To additionally score captured
answers with the rubric files under `rubrics/`, configure `.env` from `.env.example`
and run:

```bash
env -u ANTHROPIC_API_KEY .venv/bin/pytest --judge -s
```

Judge calls reuse the already captured execution; they do not rerun retrieval.

## Results and reports

Failure output includes the deterministic reason, observed tool names and arguments,
and the final answer. Every live run also writes `run-results/<run-id>/manifest.json`
and `case-id/trial-N.json`. The manifest records the case hashes, evaluator and plugin
revisions, plugin content hash, Claude and judge version/settings, and the source-registry hash
for each tested domain before and after the run. `comparable: false` means the ingested
data changed during the run and it must not be compared with another result. Its
`trial_summary` gives each selected case a result such as `2/3`.

Full tool results are also attached to Allure:

```bash
env -u ANTHROPIC_API_KEY .venv/bin/pytest --alluredir=allure-results
allure serve allure-results
```

Stop the background server when finished:

```bash
cd /Users/agrisin/projects/sysco/ai-sdlc/context-engineering/sysco-context-layer
make server-stop
```

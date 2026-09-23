# Deployed-agent case format

Cases live in `cases/` and are numbered contiguously from `case-001-*.yaml`.
Every case launches the real `/okf-knowledge` skill against the configured Knowledge
Server.

```yaml
title: Short behavior-oriented title
why: Why this scenario protects the application
query: the user's question
domain: sdp
persona: platform-engineer

expect_tool_calls:
  required:
    - tool: kb_search
      args:
        domain: sdp
        query_contains: user spelling
        limit_at_least: 20
    - tool: kb_related
      args:
        domain: sdp
        label: Service
        key: scoreboard
        relationships_contains: [OWNS]
        direction: both
        depth_at_least: 2
  forbidden_tools: [Bash, Read, Write, Edit, Grep, Glob, WebFetch, WebSearch]
  max_calls: 8

expect:
  required_entities:
    - Service/scoreboard
    - Team/dim-platin
  must_not_return: []

answer_evaluation:
  expect:
    status: answered
    required_citations:
      - {label: Service, key: scoreboard}
      - {label: Team, key: dim-platin}
    must_not_cite: []
    required_phrases: [dim-platin]
    requires_coverage_line: true
  rubrics: [faithfulness, relevancy, answer_correctness]
  reference_answer: Team dim-platin owns scoreboard.
```

## Tool argument matching

Argument names without a suffix require exact equality. Two suffix operators are
available:

- `_contains`: case-insensitive substring matching for strings or subset matching
  for lists;
- `_at_least`: numeric minimum matching.

Required calls are matched to distinct observed calls. `max_calls` counts only
`kb_*` retrieval calls, not Claude's skill/delegation events.

## Retrieved entities

Entity identities use `Label/key`, for example `Story/DE-1141`. The evaluator walks
the actual MCP results from every captured call. `required_entities` must be present;
`must_not_return` must be absent.

## Answer checks

`status` is `answered` or `insufficient_context`. An answer is classified as
insufficient only when it declares missing knowledge and cites no answering entity,
so a limitation such as "line coverage is not recorded" does not turn a useful
answer into a refusal.

`required_phrases` are case-insensitive semantic anchors. Prefer short factual atoms
over one exact sentence so harmless wording changes do not fail the case.

`answer_correctness` requires `reference_answer`. Judge rubrics are used only with
`--judge`; all other expectations are deterministic.

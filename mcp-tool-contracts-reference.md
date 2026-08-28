# MCP tool contracts — for the retrieval-skill author

Everything a skill needs to drive the Knowledge Server well. Schemas below
match what the live server advertises over tools/list (they are generated
from the same pydantic models — src/knowledge_server/retrieval.py is the
source of truth). Server: make up && make ingest && make run →
http://127.0.0.1:8000/mcp (streamable HTTP), or
claude mcp add --transport http ks http://127.0.0.1:8000/mcp.

## The mental model

The KB is a *property graph* over one engineering domain at a time:
`Service, Team, Person, Repository, Commit, PullRequest, Story, Feature,
TestSuite, DocChunk`, connected by
`OWNS, MEMBER_OF, BELONGS_TO, IN_REPOSITORY, AUTHORED, PART_OF, IMPLEMENTS,
DELIVERS, COVERS, DEPENDS_ON, DESCRIBES` (full definitions:
docs/schema.md §3.1). Entities are addressed by *label + business key*
(e.g. Service / pricing-api; Commit /
github.com/paastry/svc-pricing-api@a1f9c2d; Story / PAAS-201).

Three tools, one strategy: **search to land on an entity, fetch to read it,
related to walk from it.** Answers should carry the returned citations.

## Tool contracts

### kb_search — find entities by free text

| arg | type | required | notes |
|---|---|---|---|
| domain | string | yes | e.g. "paastry" — every call is domain-scoped |
| query | string | yes | free text; *typos are fine* (fuzzy + semantic) |
| limit | int (1–200) | no, default 10 | raise it when hunting identifiers, see gotcha 2 |

Returns list[SearchHit]:
`{entity: {label, key}, title, snippet, score (0–1), matched_by:
"vector"|"fulltext"|"both", citations: [{source_system, reference}]}`.
Ranked best-first, deduplicated by entity.

### kb_fetch — read one entity

| arg | type | required |
|---|---|---|
| domain | string | yes |
| label | string | yes — must be a vocabulary label, else a tool error listing valid ones |
| key | string | yes — exact business key |

Returns {found: bool, detail: {entity, properties, citations} | null}.
*found=false is data, not an error* — the key doesn't exist *in this
domain* (wrong domain looks identical to absent, by design). Recover by
searching for the name instead.

### kb_related — walk the graph from one entity

| arg | type | required | notes |
|---|---|---|---|
| domain, label, key | | yes | start entity |
| relationships | list[string] \| null | no | null = all types; unknown names → tool error listing valid ones |
| direction | outgoing \| incoming \| both | no, default both | see direction table below |
| depth | int 1–10 | no, *default 1* | hops; see gotcha 1 |
| limit | int 1–200 | no, default 50 | |

Returns list[RelatedEntity]:
{entity, title, relationship, direction, distance (hops ≥1)},
deterministic order.

*Direction cheat sheet* (edges point as written; you often want
incoming):

| you want | start from | relationships | direction |
|---|---|---|---|
| owner of a service | Service | ["OWNS"] | incoming |
| what a service depends on | Service | ["DEPENDS_ON"] | outgoing |
| *what depends on it (impact)* | Service | ["DEPENDS_ON"] | *incoming, depth ≥5* |
| commits in a repo | Repository | ["IN_REPOSITORY"] | incoming |
| story behind a commit | Commit | ["PART_OF","IMPLEMENTS"] | outgoing, depth 2 |
| team members | Team | ["MEMBER_OF"] | incoming |
| suites covering a feature | Feature | ["COVERS"] | incoming |

## Recipes for the five canonical questions

(Executable ground truth: scripts/demo.py and evals/golden.yaml implement
exactly these.)

1. *Why was this code changed?* — kb_search the commit sha/repo → kb_related
   from the Commit outgoing PART_OF, IMPLEMENTS depth 2 → kb_fetch the
   Story (its description is the why) → optionally kb_search the story's
   topic words to pull design rationale from DocChunks.
2. *Which story drove this repo?* — kb_related from Repository incoming
   IN_REPOSITORY (the commits) → outgoing PART_OF, IMPLEMENTS depth 2 →
   collect distinct Story refs → kb_fetch each.
3. *Who owns this application?* — kb_search the (possibly misspelled) name →
   take the best Service (see gotcha 2) → kb_related incoming OWNS; for
   humans, kb_related the Team incoming MEMBER_OF.
4. *What services are impacted by this change?* — resolve commit → Service
   (kb_related outgoing IN_REPOSITORY, BELONGS_TO, depth 2) → kb_related
   from that Service, ["DEPENDS_ON"], *incoming, depth 5+*. Report each
   hit with its distance.
5. *What coverage exists for this feature?* — kb_search the feature name →
   kb_fetch the Feature → kb_related incoming COVERS; suite properties
   carry line_coverage.

## Gotchas the skill must encode

1. *Never impact-analyse at default depth.* depth defaults to 1; the
   dependency chain in even the synthetic corpus is 4 deep. Use 5+ for any
   "what breaks / what's affected" question and quote distance per hit.
2. *Exact identifiers can rank below doc chunks* in small result sets
   (known limitation, ADR-0008): when hunting a Service/Story by name,
   use limit 10+ and pick the best hit with the wanted label, not the
   top hit overall.
3. *Trust fuzzy, don't pre-correct.* "tier confg servce" resolves; skill
   should pass user spellings through rather than guessing corrections.
4. *Always thread domain.* There is no cross-domain call; ask the user
   (or config) which domain applies. Wrong domain = clean empty results.
5. *Cite.* Every result carries citations (jira: PAAS-201,
   github: …, docs: chunk#id); answers that drop them are treated as
   ungrounded.
6. *Vocabulary errors teach.* Unknown label/relationship errors list the
   valid names — the skill can self-correct from the message.
7. Read-only: no tool mutates anything; retries are always safe.

"""A fake knowledge graph: fixture entities in, deterministic ranking out.

Deliberate limits, so nobody mistakes green tests for good retrieval:
  * Ranking is token overlap, NOT embeddings/fulltext. Scores here say nothing
    about real retrieval quality. They exist so the harness has non-degenerate
    numbers to compute and compare. `matched_by` is always reported as
    "fulltext" -- there is no vector index in this fake.
  * Domain scoping IS enforced faithfully, because that is the one contract
    behaviour the skill must not undo downstream.

Every run stamped by this backend records mode="mock" so a mock baseline can
never be compared against a real one.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .contracts import Citation, Entity, SearchHit, SearchRequest, SearchResponse

_TOKEN = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    "a an the how do we does is are of to for on in and or with our i it that this "
    "what when where which who why be been can could should would".split()
)


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS}


class FakeKnowledgeGraph:
    mode = "mock"

    def __init__(self, corpus_path: str | Path) -> None:
        self.corpus_path = Path(corpus_path)
        raw = yaml.safe_load(self.corpus_path.read_text())
        self.domain: str = raw["domain"]
        self.entities: list[dict] = raw["entities"]
        self.corpus_version: str = str(raw.get("version", "unversioned"))

    # --- scoping -----------------------------------------------------------

    def _permitted(self, request: SearchRequest) -> bool:
        """Domain isolation: wrong domain returns clean empty results.

        Real enforcement is server-side against the domain's own graph
        partition. Here it is a stand-in whose only job is to be faithful
        enough that a skill-layer regression (dropping the domain) shows up
        as a behaviour change.
        """
        return request.domain == self.domain

    # --- ranking -------------------------------------------------------

    @staticmethod
    def _score(entity: dict, query_tokens: set[str]) -> float:
        haystack = _tokens(" ".join([entity["title"], entity["snippet"]]))
        if not haystack:
            return 0.0
        overlap = len(query_tokens & haystack)
        return round(overlap / (len(query_tokens) ** 0.5 * len(haystack) ** 0.5), 6)

    def search(self, request: SearchRequest) -> SearchResponse:
        if not self._permitted(request):
            return SearchResponse(results=[])

        qt = _tokens(request.query)
        scored: list[tuple[float, dict]] = []
        for entity in self.entities:
            score = self._score(entity, qt)
            if score > 0:
                scored.append((score, entity))

        # Deterministic tie-break by (label, key) so runs are byte-identical.
        scored.sort(key=lambda pair: (-pair[0], pair[1]["label"], pair[1]["key"]))
        top = scored[: request.limit]

        results = [
            SearchHit(
                entity=Entity(label=e["label"], key=e["key"]),
                title=e["title"],
                snippet=e["snippet"],
                score=score,
                matched_by="fulltext",
                citations=[
                    Citation(source_system=c["source_system"], reference=c["reference"])
                    for c in e.get("citations", [])
                ],
            )
            for score, e in top
        ]
        return SearchResponse(results=results)

"""A fake knowledge server: fixture corpus in, deterministic ranking out.

Deliberate limits, so nobody mistakes green tests for good retrieval:
  * Ranking is token overlap, NOT embeddings. Scores here say nothing about
    real retrieval quality. They exist so the harness has non-degenerate
    numbers to compute and compare.
  * Filtering, scope isolation, veracity and supersedes ARE enforced faithfully,
    because those are contract behaviours the skill must not undo downstream.

Every run stamped by this backend records mode="mock" so a mock baseline can
never be compared against a real one.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .contracts import NoteResult, RetrieveRequest, RetrieveResponse

_TOKEN = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    "a an the how do we does is are of to for on in and or with our i it that this "
    "what when where which who why be been can could should would".split()
)


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS}


class FakeKnowledgeServer:
    mode = "mock"

    def __init__(self, corpus_path: str | Path) -> None:
        self.corpus_path = Path(corpus_path)
        raw = yaml.safe_load(self.corpus_path.read_text())
        self.notes: list[dict] = raw["notes"]
        self.corpus_version: str = str(raw.get("version", "unversioned"))
        self._superseded: set[str] = {
            sid for n in self.notes for sid in (n.get("supersedes") or [])
        }

    # --- filtering -------------------------------------------------------

    def _permitted(self, note: dict, request: RetrieveRequest) -> bool:
        """Scope isolation: a caller only sees its own department.

        Real enforcement is server-side against Okta claims. Here it is a stand-in
        whose only job is to be faithful enough that a skill-layer regression
        (dropping the scope) shows up as a behaviour change.
        """
        return note["department"] == request.scope.department

    def _passes_filters(self, note: dict, request: RetrieveRequest) -> bool:
        f = request.filters
        if f.veracity is not None and note["veracity"] not in f.veracity:
            return False
        if f.domain is not None and note.get("product") not in f.domain:
            return False
        if f.memory_type is not None and note.get("memory_type") not in f.memory_type:
            return False
        if f.validity == "current" and note["note_id"] in self._superseded:
            return False  # superseded notes are never current
        return True

    # --- ranking ---------------------------------------------------------

    @staticmethod
    def _score(note: dict, query_tokens: set[str]) -> float:
        haystack = _tokens(
            " ".join([note["title"], note["claim"], " ".join(note.get("aliases") or [])])
        )
        if not haystack:
            return 0.0
        overlap = len(query_tokens & haystack)
        return round(overlap / (len(query_tokens) ** 0.5 * len(haystack) ** 0.5), 6)

    def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        qt = _tokens(request.query)
        scored: list[tuple[float, dict]] = []
        for note in self.notes:
            if not self._permitted(note, request):
                continue
            if not self._passes_filters(note, request):
                continue
            score = self._score(note, qt)
            if score > 0:
                scored.append((score, note))

        # Deterministic tie-break by note_id so runs are byte-identical.
        scored.sort(key=lambda pair: (-pair[0], pair[1]["note_id"]))
        top = scored[: request.k]

        results = [
            NoteResult(
                note_id=n["note_id"],
                version=int(n["version"]),
                title=n["title"],
                claim=n["claim"],
                veracity=n["veracity"],
                valid_to=n.get("valid_to"),
                source_system=n["source"]["system"],
                source_locator=n["source"]["locator"],
                source_version=n["source"]["version"],
                score=score,
            )
            for score, n in top
        ]

        facets: dict[str, dict[str, int]] = {"product": {}, "veracity": {}}
        for _, n in scored:
            facets["product"][n.get("product") or "-"] = (
                facets["product"].get(n.get("product") or "-", 0) + 1
            )
            facets["veracity"][n["veracity"]] = facets["veracity"].get(n["veracity"], 0) + 1
        return RetrieveResponse(results=results, facets=facets)

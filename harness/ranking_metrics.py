"""Deterministic information-retrieval ranking metrics, computed by ``ranx``.

These functions measure ranking quality from an already graded reference set.
They return numbers, never pass/fail verdicts. Exact requirements belong under
``harness.validators``; structural test specifications belong under
``harness.definitions``.

``ranx`` uses metric implementations tested against TREC Eval and provides paired
statistical comparisons for the point at which the reference set is large enough
to replace the runner's provisional per-metric tolerance gate.
"""

from __future__ import annotations

import os
import statistics
import tempfile
from pathlib import Path


def _ranx_api():
    """Import ranx lazily and keep optional library caches out of the user home.

    Importing ranx also imports ir_datasets and matplotlib even though this harness
    uses neither directly. Both try to create cache directories on import; a stable
    temporary location keeps read-only CI and sandbox runs free of home-directory
    side effects. Disable Numba JIT for this small POC reference set: compiling the
    metric functions costs more than evaluating a handful of queries. ``setdefault``
    still lets a larger deployment opt back into JIT explicitly.
    """
    cache_root = Path(tempfile.gettempdir()) / "retrieval-eval-ranx"
    os.environ.setdefault("IR_DATASETS_HOME", str(cache_root / "ir_datasets"))
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root / "cache"))
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

    from ranx import Qrels, Run, evaluate

    return Qrels, Run, evaluate


def summarize(values: list[float]) -> dict[str, float]:
    """Return the observed distribution for one metric over repeated runs."""
    return {
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "std_dev": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "n": len(values),
    }


def score_case(ranked: list[str], grades: dict[str, int], k: int) -> dict[str, float]:
    metric_names = [f"recall@{k}", "precision@5", "mrr", f"ndcg@{k}"]

    # ranx cannot construct an entirely empty Run. Preserve the mathematically
    # defined values without manufacturing a fake retrieved document.
    if not ranked:
        no_relevant = not any(grade > 0 for grade in grades.values())
        return {
            f"recall@{k}": 1.0 if no_relevant else 0.0,
            "precision@5": 0.0,
            "mrr": 0.0,
            f"ndcg@{k}": 1.0 if no_relevant else 0.0,
        }

    # A reference set containing no relevant documents has no useful ranking
    # signal. Retain the harness's explicit edge-case semantics.
    if not any(grade > 0 for grade in grades.values()):
        return {
            f"recall@{k}": 1.0,
            "precision@5": 0.0,
            "mrr": 0.0,
            f"ndcg@{k}": 1.0,
        }

    Qrels, Run, evaluate = _ranx_api()
    query_id = "case"
    qrels = Qrels({query_id: grades})
    # ranx orders a run by descending score. Rank-derived scores preserve the
    # observed order without interpreting the fake backend's similarity values.
    run = Run(
        {
            query_id: {
                note_id: float(len(ranked) - index)
                for index, note_id in enumerate(ranked)
            }
        }
    )
    measured = evaluate(qrels, run, metric_names)
    return {name: round(float(measured[name]), 4) for name in metric_names}

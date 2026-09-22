"""Case runner: loads cases, drives the skill against the real knowledge server,
scores, emits a run record.

Usage:
    python3 -m harness.runner
    python3 -m harness.runner --write-baseline baselines/live.json --system-metadata metadata.json
    python3 -m harness.runner --baseline baselines/live.json

Exit code is non-zero if any invariant fails, or if a metric regressed against
the baseline beyond tolerance. Invariants and metrics are reported separately and
never averaged together.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.definitions.cases import load_cases  # noqa: E402
from harness.baselines import (  # noqa: E402
    BaselineFormatError,
    build_run_manifest,
    compare_records,
    load_record,
    missing_required_system_metadata,
    write_record,
)
from harness.validators import describe, render_inventory  # noqa: E402
from harness.validators.contract import (  # noqa: E402
    check_emitted_tool_call,
    check_response_contract,
    check_server_rejects_invalid_request,
)
from harness.validators.formatting import (  # noqa: E402
    check_every_result_has_provenance,
)
from harness.validators.retrieval import (  # noqa: E402
    check_expected_first_result,
    check_must_not_return,
)
from harness.ranking_metrics import score_case, summarize  # noqa: E402
from skill.client import MCPKnowledgeClient, SpyClient  # noqa: E402
from skill.skill import SearchSkill  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
DEFAULT_SERVER_URL = "http://127.0.0.1:8000/mcp"


def resolve_server_url(cli_value: str | None) -> str:
    """CLI flag > .env's KS_SERVER_URL > process env > the documented local default.

    Same precedence as JudgeConfig.from_env (harness/judges/models.py): a
    project-local .env is authoritative when present, CI normally has none and
    falls back to its process environment.
    """
    if cli_value:
        return cli_value
    file_value = dotenv_values(ENV_FILE).get("KS_SERVER_URL")
    if isinstance(file_value, str) and file_value.strip():
        return file_value
    return os.getenv("KS_SERVER_URL", DEFAULT_SERVER_URL)


def make_skill(server_url: str) -> tuple[SearchSkill, SpyClient]:
    """Same skill, always the same seam: a real MCP boundary to the knowledge server."""
    spy = SpyClient(MCPKnowledgeClient(server_url))
    return SearchSkill(spy), spy


def run_case(case: dict, server_url: str) -> dict:
    skill, spy = make_skill(server_url)
    domain, expect = case["domain"], case.get("expect", {}) or {}
    invariant_failures: list[str] = []
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        """Every check records itself, pass or fail.

        Recording passes matters as much as recording failures: without it you
        cannot tell a check that succeeded from a check that never ran, and a
        typo in a case file silently reduces coverage.
        """
        meta = describe(name)
        checks.append({
            "name": name, "status": "ok" if ok else "fail", "detail": detail,
            "traceability": meta["status"], "source": meta["source"],
        })
        if meta["status"] == "UNTRACEABLE":
            invariant_failures.append(
                f"check {name!r} has no entry in harness/validators/registry.py; every check "
                "must record where its requirement comes from"
            )
        if not ok:
            invariant_failures.append(detail or name)

    def skip(name: str, why: str) -> None:
        meta = describe(name)
        checks.append({
            "name": name, "status": "skip", "detail": why,
            "traceability": meta["status"], "source": meta["source"],
        })
        if meta["status"] == "UNTRACEABLE":
            invariant_failures.append(
                f"check {name!r} has no entry in harness/validators/registry.py; every check "
                "must record where its requirement comes from"
            )

    result = None
    retrieval_error = ""
    try:
        result = skill.search(
            domain=domain,
            query=case["query"],
            limit=case.get("limit"),
        )
    except Exception as exc:
        retrieval_error = f"search failed before a valid response was decoded: {exc}"
    ranked = [hit.entity.identity for hit in result.response.results] if result else []

    # --- contract: the emitted tool call ---------------------------------
    detail = check_emitted_tool_call(spy.last_call, case)
    record("contract:emitted_tool_call", detail is None, detail or "")

    if result is not None:
        detail = check_response_contract(result.response)
        record("contract:response_contract_valid", detail is None, detail or "")
    else:
        record("contract:response_contract_valid", False, retrieval_error)

    if "probe_invalid_request" in case:
        # Send invalid input straight to the server, bypassing the skill. This proves
        # enforcement exists at the trust boundary rather than only in client code.
        detail = check_server_rejects_invalid_request(
            spy, case["query"], domain, case["probe_invalid_request"]
        )
        record(
            "contract:server_rejects_invalid_request",
            detail is None,
            detail or "",
        )

    # --- invariants on the result set ------------------------------------
    if result is None:
        if "must_not_return" in expect:
            skip("retrieval:must_not_return", "requires a valid response")
        if "expected_first_result" in expect:
            skip("retrieval:expected_first_result", "requires a valid response")
    elif (forbidden := expect.get("must_not_return")) is not None:
        detail = check_must_not_return(ranked, forbidden)
        record("retrieval:must_not_return", detail is None, detail or "")

    if result is not None:
        if (expected_first := expect.get("expected_first_result")) is not None:
            detail = check_expected_first_result(ranked, expected_first)
            record("retrieval:expected_first_result", detail is None, detail or "")

    # --- format ----------------------------------------------------------
    if result is not None:
        detail = check_every_result_has_provenance(
            result.rendered, result.response.results
        )
        record("format:every_result_has_provenance", detail is None, detail or "")
    else:
        skip("format:every_result_has_provenance", "requires a valid response")

    # --- metrics ---------------------------------------------------------
    metrics = {}
    if result is not None and (relevant := expect.get("relevant")):
        grades = {r["entity"]: r["grade"] for r in relevant}
        metrics = score_case(ranked, grades, case.get("limit", 10))

    return {
        "id": case["id"],
        "ranked": ranked,
        "metrics": metrics,
        # Sibling to "metrics", never inside it: harness/baselines.py's
        # compare_records() does an exact key-set comparison on "metrics" --
        # adding a key there would make every committed baseline incompatible.
        # Report-only until a real threshold is approved.
        "latency_ms": spy.last_duration_ms,
        "checks": checks,
        "invariant_failures": invariant_failures,
        "passed": not invariant_failures,
        "trace": {
            "query": case["query"],
            "domain": domain,
            "persona": case["persona"],
            "tool_call": spy.last_call,
            "calls": len(spy.calls),
            "results": (
                [
                    {
                        "entity": hit.entity.identity,
                        "title": hit.title,
                        "score": hit.score,
                        "matched_by": hit.matched_by,
                    }
                    for hit in result.response.results
                ]
                if result else []
            ),
            "rendered": result.rendered if result else "",
        },
    }


def run_case_repeated(case: dict, server_url: str, n: int) -> dict:
    """Run one case n times and collapse the executions into one verdict.

    Three verdicts rather than two. A case that passes sometimes and fails
    sometimes is FLAKY, which is worse than a clean FAIL: it means the suite
    cannot tell you anything reliable until the flakiness is explained.
    """
    runs = [run_case(case, server_url) for _ in range(n)]
    passes = [r["passed"] for r in runs]

    if all(passes):
        verdict = "PASS"
    elif not any(passes):
        verdict = "FAIL"
    else:
        verdict = "FLAKY"

    # Metric means stay under "metrics" so baselines written at n=1 remain
    # comparable; the spread goes alongside it.
    distribution: dict[str, dict[str, float]] = {}
    metrics: dict[str, float] = {}
    for key in runs[0]["metrics"]:
        values = [r["metrics"][key] for r in runs]
        stats = summarize(values)
        distribution[key] = stats
        metrics[key] = stats["mean"]

    latency_stats = summarize([r["latency_ms"] for r in runs])

    failures = sorted({f for r in runs for f in r["invariant_failures"]})

    return {
        "id": case["id"],
        "executions": n,
        "verdict": verdict,
        "ranked": runs[0]["ranked"],
        "checks": runs[0]["checks"],
        "trace": runs[0]["trace"],
        "metrics": metrics,
        "distribution": distribution,
        "latency_ms": latency_stats["mean"],
        "latency_distribution_ms": latency_stats,
        "invariant_failures": failures,
        "passed": verdict == "PASS",
    }


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(ROOT / "cases"))
    ap.add_argument(
        "--server-url",
        help=f"MCP streamable-HTTP URL of the knowledge server; falls back to "
             f"the KS_SERVER_URL env var / .env, then {DEFAULT_SERVER_URL}",
    )
    ap.add_argument(
        "--trace", action="store_true",
        help="print the full execution trace for each case: emitted call, raw "
             "results, rendered output, and every check with its outcome",
    )
    ap.add_argument("--baseline")
    ap.add_argument("--write-baseline")
    ap.add_argument(
        "--system-metadata",
        help="JSON metadata reported by the selected Knowledge Server and environment",
    )
    ap.add_argument(
        "--change-under-test",
        action="append",
        default=[],
        metavar="TARGET_FIELD",
        help="target manifest field allowed to differ from the baseline; repeatable",
    )
    ap.add_argument(
        "-n", "--executions", type=int, default=1,
        help="run each case N times to separate consistent failures from stochastic ones",
    )
    ap.add_argument("--list-checks", action="store_true",
                    help="print the check contract and exit, running nothing")
    ap.add_argument("--markdown", action="store_true",
                    help="with --list-checks, emit a markdown table")
    args = ap.parse_args()

    if args.list_checks:
        print(render_inventory(markdown=args.markdown))
        return 0

    server_url = resolve_server_url(args.server_url)
    cases_path = Path(args.cases)
    cases = load_cases(cases_path)
    system_metadata = None
    if args.system_metadata:
        try:
            system_metadata = json.loads(
                Path(args.system_metadata).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            print(f"invalid --system-metadata: {exc}", file=sys.stderr)
            return 2
    if args.write_baseline or args.baseline:
        # The live server reports no version/snapshot of its own, so a manifest
        # that will be persisted or compared must have the operator state what
        # it cannot self-report. A plain run (no baseline flags) does not need
        # this -- see build_run_manifest's docstring.
        missing = missing_required_system_metadata(system_metadata)
        if missing:
            print(
                "--write-baseline/--baseline require --system-metadata to state "
                f"what the plain run above cannot self-report; missing: {missing}",
                file=sys.stderr,
            )
            return 2
    try:
        manifest = build_run_manifest(
            root=ROOT,
            cases=cases_path,
            executions=args.executions,
            system_metadata=system_metadata,
            change_under_test=args.change_under_test,
        )
    except BaselineFormatError as exc:
        print(f"cannot build run manifest: {exc}", file=sys.stderr)
        return 2
    results = [
        run_case_repeated(c, server_url, args.executions)
        for c in cases
    ]
    record = {"manifest": manifest, "cases": results}

    # ---- trace ----
    if args.trace:
        for r in results:
            tr = r["trace"]
            print("\n" + "=" * 78)
            print(f"{r['id']}  -> {r['verdict']}")
            print("=" * 78)
            print(f"query   : {tr['query']}")
            print(f"domain  : {tr['domain']}")
            print(f"persona : {tr['persona']}")
            print(f"\nemitted tool call ({tr['calls']} call(s) total):")
            print(json.dumps(tr["tool_call"], indent=2))
            print("\nbackend returned:")
            if not tr["results"]:
                print("  (nothing)")
            for i, row in enumerate(tr["results"], 1):
                print(f"  {i}. {row['entity']}  score={row['score']}  "
                      f"{row['matched_by']:<9} {row['title']}")
            print("\nrendered for the agent:")
            for line in tr["rendered"].rstrip().splitlines():
                print(f"  | {line}")
            print("\nchecks:  (glyph = traceability: blank traced, "
                  "~ inferred, ? unratified, ! missing from registry)")
            for c in r["checks"]:
                mark = {"ok": "PASS", "fail": "FAIL", "skip": "skip"}[c["status"]]
                trace_mark = {"traced": " ", "inferred": "~", "unratified": "?",
                              "UNTRACEABLE": "!"}.get(c.get("traceability"), " ")
                line = f"  [{mark}]{trace_mark} {c['name']}"
                if c["detail"] and c["status"] != "ok":
                    line += f"  -- {c['detail']}"
                print(line)
                if c["status"] != "skip":
                    print(f"          source: {c['source']}")
            ran = sum(1 for c in r["checks"] if c["status"] != "skip")
            print(f"  {ran} check(s) ran, "
                  f"{sum(1 for c in r['checks'] if c['status'] == 'skip')} skipped")
            if r["metrics"]:
                print("\nmetrics:")
                for k, v in r["metrics"].items():
                    print(f"  {k} = {v}")
            print(f"\nlatency: {r['latency_ms']:.2f} ms")
        print("\n" + "=" * 78)

    # ---- report ----
    show_spread = args.executions > 1
    print(f"\n{'case':<15} {'result':<8} metrics")
    print("-" * 78)
    for r in results:
        if show_spread:
            m = " ".join(
                f"{k}={s['mean']}~{s['std_dev']}" for k, s in r["distribution"].items()
            )
            m += f"  latency_ms={r['latency_ms']:.2f}~{r['latency_distribution_ms']['std_dev']:.2f}"
        else:
            m = " ".join(f"{k}={v}" for k, v in r["metrics"].items())
            m += f"  latency_ms={r['latency_ms']:.2f}"
        print(f"{r['id']:<15} {r['verdict']:<8} {m}")
        for f in r["invariant_failures"]:
            print(f"    ! {f}")
    if show_spread:
        print(f"\n  metrics shown as mean~std_dev over {args.executions} executions")

    failed = [r["id"] for r in results if not r["passed"]]
    exit_code = 1 if failed else 0

    # ---- baseline ----
    if args.baseline:
        try:
            base = load_record(Path(args.baseline))
            comparison = compare_records(base, record)
        except BaselineFormatError as exc:
            print(f"\n  REFUSING to compare: {exc}")
            return 1
        if not comparison.compatible:
            print("\n  REFUSING to compare incompatible runs:")
            for difference in comparison.differences:
                print(f"  - {difference.path}")
                print(f"      baseline: {difference.baseline!r}")
                print(f"      current : {difference.current!r}")
            return 1
        print("\nvs baseline:")
        for delta in comparison.metric_deltas:
            if delta.delta:
                flag = "  REGRESSION" if delta.regression else ""
                print(
                    f"  {delta.case_id} {delta.metric}: {delta.baseline} -> "
                    f"{delta.current} ({delta.delta:+}){flag}"
                )
        tolerance = manifest["compatibility"]["profiles"]["ranking"][
            "absolute_drop_tolerance"
        ]
        print(
            f"  {len(comparison.regressions)} regression(s) beyond tolerance "
            f"{tolerance}"
        )
        exit_code = exit_code or (1 if comparison.regressions else 0)

    if args.write_baseline:
        out = Path(args.write_baseline)
        write_record(out, record)
        print(f"\nbaseline written: {out}")

    print(f"\n{len(results) - len(failed)}/{len(results)} cases passed")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

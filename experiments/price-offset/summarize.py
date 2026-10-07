"""Summarize offset timings and diagnostic counters from saved candidate runs.

Executive summary: compare the offset candidate only with the currently adopted
numeric-vector engine; keep historical timing limits and every slower sample.
"""

from pathlib import Path
import argparse
import hashlib
import json
import re
import statistics

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent


def metric(before, after):
    a = statistics.median(before)
    b = statistics.median(after)
    return {
        "baseline_samples": before,
        "candidate_samples": after,
        "baseline_median": a,
        "candidate_median": b,
        "baseline_mean": statistics.mean(before),
        "candidate_mean": statistics.mean(after),
        "baseline_range": [min(before), max(before)],
        "candidate_range": [min(after), max(after)],
        "time_change_percent": 100 * (b / a - 1),
        "baseline_over_candidate": a / b,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "out/price-offset-20261007")
    out = parser.parse_args().out.resolve()
    policy = json.loads((EXP / "policy.json").read_text())
    state = json.loads((out / "state.json").read_text())
    assert state["complete"] and "error" not in state
    summary_path = out / "simulations/summary.json"
    s = json.loads(summary_path.read_text())
    baseline_path = ROOT / policy["baseline_simulator_evidence"]
    old = json.loads(baseline_path.read_text())
    assert s["complete"] and s["accepted"] and old["accepted"]
    assert old["candidate_image"]["digest"] == policy["baseline_id"]
    assert (
        hashlib.sha256((EXP / "state.py").read_bytes()).hexdigest()
        == policy["candidate_state_sha256"]
    )
    rows = []
    for unit in policy["units"]:
        a = [r for r in old["runs"] if r["unit"] == unit and r["kind"] == "timing"]
        b = [r for r in s["runs"] if r["unit"] == unit and r["kind"] == "timing"]
        assert len(a) == len(b) == 5 and all(r["accepted"] for r in a + b)
        rows.append(
            {
                "unit": unit,
                "metrics": {
                    "container_seconds": metric(
                        [r["container_sec"] for r in a], [r["container_sec"] for r in b]
                    ),
                    "simulation_seconds": metric(
                        [r["events"]["simulation_wall_clock_sec"] for r in a],
                        [r["events"]["simulation_wall_clock_sec"] for r in b],
                    ),
                },
            }
        )
    micro = []
    for size in policy["micro_levels"]:
        for phase in policy["micro_phases"]:
            a = []
            b = []
            for i in range(7):
                x = json.loads(
                    (
                        ROOT / f"out/price-vector-20261007/micro/vector-{i:02d}.json"
                    ).read_text()
                )["results"]
                y = json.loads((out / f"micro/vector-{i:02d}.json").read_text())[
                    "results"
                ]
                x = next(r for r in x if r["levels"] == size and r["phase"] == phase)
                y = next(r for r in y if r["levels"] == size and r["phase"] == phase)
                assert (
                    x["domain_sha256"] == y["domain_sha256"]
                    and x["operations"] == y["operations"] == 2000
                )
                a.append(x["ns_per_operation"])
                b.append(y["ns_per_operation"])
            micro.append(
                {
                    "levels": size,
                    "phase": phase,
                    "nanoseconds_per_operation": metric(a, b),
                }
            )
    diagnostics = {}
    for unit in policy["diagnostic_units"]:
        folder = out / "diagnostics" / unit
        valid = json.loads((folder / "validation.json").read_text())
        assert valid["check"]["accepted"] and valid["excluded_from_timings"]
        diagnostics[unit] = json.loads((folder / "counts.json").read_text())
    passed = int(
        re.search(r"(\d+) passed in ", (out / "runtime-tests.log").read_text()).group(1)
    )
    labels = {
        "t3-mp02-stp-oldest-baseline": "STP oldest",
        "t3-mr-deep-book-state-size": "Deep-book",
        "t3-mp05-cancel-churn-newest": "Cancel churn",
    }
    executive = (
        "Historical median simulation-time changes: "
        + ", ".join(
            f"{labels[r['unit']]} {r['metrics']['simulation_seconds']['time_change_percent']:+.1f}%"
            for r in rows
        )
        + ". Negative means less time. Only the new candidate was launched; separate schedules do not establish a causal speedup. At measurement time, the offset implementation remained experimental."
    )
    slower_micro_cases = sum(
        r["nanoseconds_per_operation"]["time_change_percent"] > 0 for r in micro
    )
    assessment = [
        "The head-offset mechanism operates as intended, with prefix reuse and bounded storage verified.",
        f"{slower_micro_cases} of {len(micro)} comparable synthetic medians are slower; component timings do not corroborate the large full-run reductions.",
        "Cancel-churn head removal is a minority of level-removing cancellations; the price search mostly sees five or six live levels on a side.",
        "Full-run differences remain observations against saved schedules. No concurrent load, VM scheduling or host frequency attribution was measured.",
        "At measurement time the candidate was kept experimental: these results do not establish a repeatable net gain from the offset alone.",
    ]
    result = {
        "executive_summary": executive,
        "complete": True,
        "rankable": False,
        "adopted": False,
        "baseline_image": policy["baseline_id"],
        "candidate_image": state["candidate_image"],
        "candidate_state_sha256": policy["candidate_state_sha256"],
        "installed_changed_files": state["installed_changed_files"],
        "validation": {
            "order_book_tests_passed": passed,
            "simulator_runs": len(s["runs"]),
            "public_units": 3,
            "exact_comparisons": len(s["comparisons"]),
            "synthetic_domain_comparisons": state["micro_domain_comparisons"],
            "untimed_diagnostic_runs": state["diagnostic_runs"],
            "old_timing_containers_launched": 0,
            "full_public_regression": "not run by user scope",
        },
        "policy_sha256": hashlib.sha256((EXP / "policy.json").read_bytes()).hexdigest(),
        "evidence_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                summary_path,
                baseline_path,
                out / "installed-source.json",
                out / "runtime-tests.log",
                out / "diagnostics/t3-mp05-cancel-churn-newest/counts.json",
            ]
        },
        "units": rows,
        "microbench": micro,
        "diagnostics": diagnostics,
        "assessment": assessment,
        "limits": [
            "Historical, unpaired timings on local macOS VM/emulation; not official Final timing.",
            "Only auxiliary key storage uses an offset; the level list still shifts.",
            "Middle changes still shift keys; extra offset arithmetic can slow searches.",
            "Slices invalidate the vector for a one-time rebuild; explicit base-list and vars(level) bypass limitations persist.",
        ],
    }
    (EXP / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# Active start offset for numeric price keys",
        "",
        "## Executive summary",
        "",
        executive,
        "",
        "## Subsequent develop integration",
        "",
        "The user subsequently selected this measured implementation for `codex/develop`.",
        "See [the integration record](integration.json) for the adopted source identity",
        "and fresh-installation checks. `policy.json` and `result.json` retain the",
        "experiment's historical `adopted: false`; the integration record describes",
        "the later decision. Existing correctness and timing evidence is reused.",
        "",
        f"The candidate passed {passed} order-book tests, 18 warmup/measured runs on the",
        "three requested units, 33 exact journal/stability comparisons and 210 synthetic",
        "domain comparisons. One separate cancellation diagnostic run also passed actual",
        "developer gates and exact journal comparison. No old timing container was run.",
        "",
        "## Implementation and frozen policy",
        "",
        "The candidate inherits the measured numeric-vector image adopted in develop.",
        "Its only changed installed Python file is `matching/state.py`. Head key removal",
        "advances a private active-start offset; head insertion reuses an unused prefix",
        "slot. Binary search is limited to active keys and returns a logical level index.",
        "Middle/tail changes maintain active keys; public slices/reorderings rebuild once.",
        "Empty books reset storage. Compaction occurs when the discarded prefix reaches",
        "64 keys and is at least as large as the live key count. Certified storage is",
        "bounded by twice the live level count plus 63 integer slots. Removed keys do not",
        "retain PriceLevel objects. The actual level list continues to shift.",
        "",
        "Tests cover both sides, head reuse without key-array shifts, compaction boundaries,",
        "middle/tail/slice changes with nonzero offsets, sustained memory bounds, removed",
        "level reclamation, deepcopy/pickle and price edits. Existing semantic book tests",
        "remain unchanged. The vector invariant tests compare the active slice.",
        "",
        "## Measurement scope",
        "",
        "Only the offset candidate is launched under colima-agenthon, linux/amd64, four",
        "CPUs, 16 GiB and no network, strictly serially. Each requested public unit has",
        "one excluded warmup and five measured repetitions. Full developer gates and",
        "exact event/message journals are checked for every run. Current numeric-vector",
        "timings are reused from `out/price-vector-20261007/`; the earlier direct-key bisect",
        "image is not the timing baseline. No full corpus regression is launched.",
        "",
        "The unchanged synthetic benchmark retains seven repetitions at six depths, with",
        "200 warmup and 2,000 measured operations for each case. Index mutation is timed.",
        "Existing-level operations and middle/new-level churn reuse saved comparable cases.",
        "Head-offset usage is proved by structural tests and measured separately through",
        "an untimed cancellation diagnostic; it has no invented historical timing ratio.",
        "",
        "## Requested simulator measurements",
        "",
        "Medians in seconds. Positive time change means slower. Every sample, mean and",
        "range is retained in `result.json`.",
        "",
        "| Unit | Container: vector | Container: offset | Change | Simulation: vector | Simulation: offset | Change |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        c = r["metrics"]["container_seconds"]
        t = r["metrics"]["simulation_seconds"]
        lines.append(
            f"| {labels[r['unit']]} | {c['baseline_median']:.3f} | {c['candidate_median']:.3f} | {c['time_change_percent']:+.1f}% | {t['baseline_median']:.3f} | {t['candidate_median']:.3f} | {t['time_change_percent']:+.1f}% |"
        )
    lines.extend(
        [
            "",
            "Simulation-time ranges across all five measured repetitions:",
            "",
            "| Unit | Vector min–max, s | Offset min–max, s |",
            "| --- | ---: | ---: |",
        ]
    )
    for r in rows:
        t = r["metrics"]["simulation_seconds"]
        a = t["baseline_range"]
        b = t["candidate_range"]
        lines.append(
            f"| {labels[r['unit']]} | {a[0]:.3f}–{a[1]:.3f} | {b[0]:.3f}–{b[1]:.3f} |"
        )
    lines.extend(["", "## Untimed cancellation diagnostics", ""])
    for unit, d in diagnostics.items():
        c = d["counts"]
        head = c.get("cancel_remove_head", 0)
        removed = c.get("cancel_removed_level", 0)
        lines.extend(
            [
                f"The instrumented run records {c.get('cancel_requests',0)} cancellation requests,",
                f"{c.get('cancel_successes',0)} successful cancellations and {removed} cancellations",
                f"removing a price level. Of these, {head} remove its first level",
                f"({100*head/max(1,removed):.1f}% of successful level-removing cancels).",
                f"Across fills and cancels combined, {c.get('removed_levels',0)} keys are removed,",
                f"{c.get('head_offset_advances',0)} head removals advance the offset,",
                f"{c.get('prefix_slot_reuses',0)} insertions reuse a prefix slot, and",
                f"{c.get('compactions',0)} compactions occur. The vector is rebuilt",
                f"{c.get('rebuilds',0)} times. Full counters and search-depth distribution are",
                "in `result.json`. Instrumented operation times include profiling overhead and",
                "are not comparable benchmark samples.",
                f"Middle cancellations account for {100*c.get('cancel_remove_middle',0)/max(1,removed):.1f}%",
                "of level-removing cancellations. At search time, the live price count on",
                "one side is most often five or six; see the complete histogram in `result.json`.",
            ]
        )
    lines.extend(
        [
            "",
            "## Comparable synthetic operations",
            "",
            "Medians in microseconds per operation. Positive means slower. These component",
            "timings cannot substitute for whole-simulator results.",
            "",
            "| Levels | Operation | Vector, µs | Offset, µs | Change |",
            "| ---: | --- | ---: | ---: | ---: |",
        ]
    )
    for r in micro:
        m = r["nanoseconds_per_operation"]
        lines.append(
            f"| {r['levels']} | {r['phase']} | {m['baseline_median']/1000:.3f} | {m['candidate_median']/1000:.3f} | {m['time_change_percent']:+.1f}% |"
        )
    lines.extend(["", "## Assessment", ""])
    for item in assessment:
        lines.extend([item, ""])
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "Build the isolated image using",
            "`docker --context colima-agenthon build --platform=linux/amd64 --network=none",
            "-t python-book-price-offset:20261007 experiments/price-offset`.",
            "Run `.venv/bin/python experiments/price-offset/run_experiment.py --out",
            "out/price-offset-new` with a fresh directory. Source guards reject changed",
            "baseline modules. Regenerate the report with `.venv/bin/python",
            "experiments/price-offset/summarize.py --out out/price-offset-new`.",
            "",
            "The measurement run did not include main-engine adoption, submission repacking or registry publication.",
            "Stored baseline and candidate measurements are unpaired and local/non-rankable.",
        ]
    )
    (EXP / "README.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "complete": True,
                "validation": result["validation"],
                "units": [
                    {
                        "unit": r["unit"],
                        "simulation_change_percent": r["metrics"]["simulation_seconds"][
                            "time_change_percent"
                        ],
                        "container_change_percent": r["metrics"]["container_seconds"][
                            "time_change_percent"
                        ],
                    }
                    for r in rows
                ],
                "diagnostic_counts": {k: d["counts"] for k, d in diagnostics.items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

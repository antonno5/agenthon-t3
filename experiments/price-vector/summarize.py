"""Summarize candidate-only timings against frozen bisect measurements.

Executive summary: retain every repeat and distinguish historical estimates from
paired speedups. The engine is not adopted automatically by this experiment.
"""

from pathlib import Path
import argparse
import hashlib
import json
import re
import statistics

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
OUT = ROOT / "out/price-vector-20261007"


def metric(before, after):
    old = statistics.median(before)
    new = statistics.median(after)
    return {
        "baseline_samples": before,
        "candidate_samples": after,
        "baseline_median": old,
        "candidate_median": new,
        "baseline_mean": statistics.mean(before),
        "candidate_mean": statistics.mean(after),
        "baseline_range": [min(before), max(before)],
        "candidate_range": [min(after), max(after)],
        "time_reduction_percent": 100 * (1 - new / old),
        "ratio_baseline_over_candidate": old / new,
    }


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    OUT = parser.parse_args().out.resolve()
    policy = json.loads((EXP / "policy.json").read_text())
    state = json.loads((OUT / "state.json").read_text())
    assert state["complete"] and "error" not in state
    summary_path = OUT / "simulations/summary.json"
    summary = json.loads(summary_path.read_text())
    baseline_path = ROOT / policy["baseline_simulator_evidence"]
    baseline = json.loads(baseline_path.read_text())
    assert summary["complete"] and summary["accepted"] and baseline["accepted"]
    assert baseline["images"]["baseline"]["digest"] == policy["baseline_id"]
    assert (
        hashlib.sha256((EXP / "state.py").read_bytes()).hexdigest()
        == policy["candidate_state_sha256"]
    )
    rows = []
    for unit in policy["units"]:
        old = [
            r
            for r in baseline["runs"]
            if r["unit"] == unit and r["side"] == "baseline" and r["kind"] == "timing"
        ]
        new = [
            r for r in summary["runs"] if r["unit"] == unit and r["kind"] == "timing"
        ]
        assert len(old) == len(new) == policy["repeats"]
        assert all(r["accepted"] for r in old + new)
        rows.append(
            {
                "unit": unit,
                "metrics": {
                    "container_seconds": metric(
                        [r["container_sec"] for r in old],
                        [r["container_sec"] for r in new],
                    ),
                    "simulation_seconds": metric(
                        [r["events"]["simulation_wall_clock_sec"] for r in old],
                        [r["events"]["simulation_wall_clock_sec"] for r in new],
                    ),
                },
            }
        )
    micro = []
    for size in policy["micro_levels"]:
        for phase in policy["micro_phases"]:
            samples = {"baseline": [], "candidate": []}
            for i in range(policy["micro_repeats"]):
                a = json.loads(
                    (
                        ROOT / f"out/price-search-comparison/micro/bisect-{i:02d}.json"
                    ).read_text()
                )
                b = json.loads((OUT / f"micro/vector-{i:02d}.json").read_text())
                old = next(
                    x
                    for x in a["results"]
                    if x["levels"] == size and x["phase"] == phase
                )
                new = next(
                    x
                    for x in b["results"]
                    if x["levels"] == size and x["phase"] == phase
                )
                assert (
                    old["operations"] == new["operations"] == policy["micro_operations"]
                )
                assert old["domain_sha256"] == new["domain_sha256"]
                samples["baseline"].append(old["ns_per_operation"])
                samples["candidate"].append(new["ns_per_operation"])
            micro.append(
                {
                    "levels": size,
                    "phase": phase,
                    "nanoseconds_per_operation": metric(
                        samples["baseline"], samples["candidate"]
                    ),
                }
            )
    log = (OUT / "runtime-tests.log").read_text()
    passed = int(re.search(r"(\d+) passed in ", log).group(1))
    integration_path = EXP / "integration.json"
    integration = (
        json.loads(integration_path.read_text()) if integration_path.exists() else None
    )
    result = {
        "executive_summary": (
            "Results are mixed: historical median container-time changes are "
            + ", ".join(
                f"{row['unit']}: {-row['metrics']['container_seconds']['time_reduction_percent']:+.1f}%"
                for row in rows
            )
            + ". Negative means less time. Only the new candidate was run; separate measurement schedules prevent a causal speedup claim. "
            + (
                "The user selected the measured implementation for codex/develop."
                if integration
                else "The candidate remains an experiment."
            )
        ),
        "complete": True,
        "rankable": False,
        "adopted": integration is not None,
        "integration": integration,
        "baseline_image": policy["baseline_id"],
        "candidate_image": state["candidate_image"],
        "candidate_source_sha256": policy["candidate_state_sha256"],
        "installed_changed_files": state["installed_changed_files"],
        "validation": {
            "order_book_tests_passed": passed,
            "simulator_runs": len(summary["runs"]),
            "selected_public_units": len(policy["units"]),
            "exact_comparisons": len(summary["comparisons"]),
            "synthetic_domain_comparisons": state["micro_domain_comparisons"],
            "baseline_timing_containers_launched": 0,
            "full_public_regression": "not_run_by_user_instruction",
            "first_attempt": "One deepcopy key-duplication failure was fixed before any candidate timings; logs retained under out/price-vector-20261007/attempt-1.",
        },
        "policy_sha256": hashlib.sha256((EXP / "policy.json").read_bytes()).hexdigest(),
        "evidence_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                summary_path,
                baseline_path,
                OUT / "installed-source.json",
                OUT / "runtime-tests.log",
            ]
        },
        "units": rows,
        "microbench": micro,
        "limits": [
            "Historical comparison, not paired: every baseline timing was reused.",
            "Local macOS VM/emulation measurements; not official Final timing.",
            "Only three selected public units were executed.",
            "Price insertion/deletion still shifts lists; numeric keys add memory and another list shift.",
            "Explicit same-length base-list mutations and vars(level) writes retain the existing bypass limitation.",
        ],
    }
    (EXP / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    labels = {
        "t3-mp02-stp-oldest-baseline": "STP oldest",
        "t3-mr-deep-book-state-size": "Deep-book state size",
        "t3-mp05-cancel-churn-newest": "Cancel churn",
    }
    lines = [
        "# Best-price path and maintained numeric price vector",
        "",
        "## Executive summary",
        "",
        result["executive_summary"],
        "",
        f"The candidate passed {passed} order-book checks, all 18 selected simulator runs,",
        "33 exact journal/stability comparisons and 210 synthetic domain comparisons.",
        "The measured implementation was adopted in codex/develop at the user's request."
        if integration
        else "The existing develop engine and published submission image are unchanged.",
        "The existing submission archive still refers to the previous bisect image."
        if integration
        else "The experiment is not adopted automatically.",
        "",
        "## Implementation",
        "",
        "Only the installed `matching/state.py` differs from the measured bisect image.",
        "A private numeric key vector stores ascending asks and negated bids. Search",
        "returns position zero immediately when the target is at or ahead of the best",
        "price; otherwise `bisect_left` reads integers without a Python key callback.",
        "Normal insert/delete/pop operations update the vector with the level list.",
        "Public reorderings and price edits rebuild once before reuse; unsupported",
        "levels and plain replacement lists retain the original traversal.",
        "Pickle/deepcopy reconstruction detects incomplete list restoration before",
        "incremental updates. FIFO queues, matching rules and callbacks are unchanged.",
        "",
        "The Docker overlay inherits the measured bisect runtime, checks the original",
        "module SHA-256 before replacing it, verifies the replacement and precompiles",
        "its bytecode. Installed-source auditing verifies that only that module changed.",
        "",
        "## Measurement scope",
        "",
        "Only the candidate is run. Baseline times come from the prior frozen",
        "bisect/hybrid comparison. Each selected public unit has one excluded warmup",
        "and five measured candidate repetitions. The unchanged synthetic benchmark",
        "runs seven candidate repetitions, at six depths and five operation workloads,",
        "with 200 excluded warmup operations and 2,000 measured operations per case.",
        "Existing-level cases retain levels; new-level churn creates and deletes one",
        "level per operation. These exercise different mutation intensities.",
        "",
        "All containers use colima-agenthon, linux/amd64, four CPUs, 16 GiB and no",
        "network, sequentially. No baseline timing container or full corpus regression",
        "is launched. Only the targeted order-book suite and three public units run.",
        "",
        "## Full simulator results",
        "",
        "Medians in seconds. Positive reduction means less time. These are historical",
        "estimates, not paired causal speedups. Every sample, mean and range is in",
        "`result.json`.",
        "",
        "| Unit | Container: bisect | Container: vector | Reduction | Simulation: bisect | Simulation: vector | Reduction |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        c = row["metrics"]["container_seconds"]
        s = row["metrics"]["simulation_seconds"]
        lines.append(
            f"| {labels[row['unit']]} | {c['baseline_median']:.3f} | {c['candidate_median']:.3f} | {c['time_reduction_percent']:+.1f}% | {s['baseline_median']:.3f} | {s['candidate_median']:.3f} | {s['time_reduction_percent']:+.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Synthetic operation results",
            "",
            "Medians in microseconds per operation. Initialization and warmup are",
            "excluded; mutation and key-vector maintenance are timed. Operation timings",
            "are not full simulator speedups.",
            "",
            "| Levels | Operation | Bisect, µs | Vector, µs | Reduction |",
            "| ---: | --- | ---: | ---: | ---: |",
        ]
    )
    for row in micro:
        m = row["nanoseconds_per_operation"]
        lines.append(
            f"| {row['levels']} | {row['phase']} | {m['baseline_median']/1000:.3f} | {m['candidate_median']/1000:.3f} | {m['time_reduction_percent']:+.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Reproduction and limitations",
            "",
            "Build with `docker --context colima-agenthon build --platform=linux/amd64",
            "--network=none -t python-book-price-vector:20261007 experiments/price-vector`.",
            "Run the candidate-only coordinator with `.venv/bin/python",
            "experiments/price-vector/run_experiment.py --out out/price-vector-new`.",
            "It requires a fresh output directory and checks source/evidence hashes.",
            "Regenerate this report using `.venv/bin/python experiments/price-vector/summarize.py`.",
            "Pass `--out out/price-vector-new` when summarizing a new local run.",
            "",
            "The first runtime attempt caught one deepcopy key duplication error. The",
            "fix was tested before any timings; the failed source and log are retained",
            "under `out/price-vector-20261007/attempt-1/`. Final results use only the fixed",
            "candidate image.",
            "",
            "Separate schedules, local VM/emulation and prior VM recovery prevent a",
            "statistical or causal performance claim. Stored key vectors consume extra",
            "memory and require a second list shift on new-level changes. Arbitrary",
            "explicit base-list mutation and writes through vars(level) retain the",
            "existing compatibility limits. No submission is rebuilt or published.",
        ]
    )
    (EXP / "README.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {"complete": True, "validation": result["validation"], "units": rows},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

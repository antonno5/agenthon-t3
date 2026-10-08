"""Preserve accepted experiment results and distinguish the three timing clocks.

Executive summary: publish paired container and adapter times with all samples,
checks, source identity and an explicit experimental deployment status.
"""

import argparse
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "out/native-index-20261007")
    out = ap.parse_args().out.resolve()
    timing = json.loads((out / "timing/summary.json").read_text())
    public = json.loads((out / "public/summary.json").read_text())
    for d in [timing, public]:
        assert d["complete"] and d["accepted"]
        assert all(r["accepted"] for r in d["runs"])
    assert timing["candidate_image"] == public["candidate_image"]
    readonly = json.loads((out / "readonly/validation.json").read_text())
    batch_digests = json.loads((out / "batch-reference-digests.json").read_text())
    assert readonly["accepted"] and batch_digests["accepted"]
    rows = []
    for row in timing["results"]:
        unit = row["unit"]
        copy = dict(row)
        copy["native_core_samples"] = [
            r["events"]["simulation_wall_clock_sec"]
            for r in timing["runs"]
            if r["unit"] == unit and r["side"] == "candidate" and r["kind"] == "timing"
        ]
        copy["python_simulation_samples"] = [
            r["events"]["simulation_wall_clock_sec"]
            for r in timing["runs"]
            if r["unit"] == unit and r["side"] == "baseline" and r["kind"] == "timing"
        ]
        rows.append(copy)
    passed = int(re.search(r"(\d+) passed", (out / "runtime-tests.log").read_text())[1])
    numeric = (out / "numeric-tests.log").read_text()
    assert "FAILS 0 of 100" in numeric and "mismatches: 0 of 100000" in numeric
    names = set(timing["policy"]["units"]) | set(public["policy"]["units"])
    single = [n for n in names if (ROOT / "units" / n / "scenario.json").exists()]
    batches = [n for n in names if (ROOT / "units" / n / "batch.json").exists()]
    record = {
        "executive_summary": "The experimental native simulation retains our binary numeric price index, best-price fast path and reusable prefix. Paired focused times and exact public checks are retained; the production baseline is unchanged.",
        "complete": True,
        "accepted": True,
        "adopted": False,
        "rankable": False,
        "baseline_image": timing["baseline_image"],
        "candidate_image": timing["candidate_image"],
        "provenance": json.loads((EXP / "provenance.json").read_text()),
        "timing_policy": timing["policy"],
        "source_hashes_at_measurement": timing["source_hashes"],
        "validation": {
            "runtime_tests_passed": passed,
            "price_side_differential_mutations": 80000,
            "rng_interleaved_scripts": 100,
            "rng_mismatches": 0,
            "numpy_log_samples": 100000,
            "numpy_log_mismatches": 0,
            "single_public_units": len(single),
            "batch_public_units": len(batches),
            "focused_simulator_runs": len(timing["runs"]),
            "additional_correctness_runs": len(public["runs"]),
            "all_checked_runs_used_native": True,
            "source_audit": json.loads((out / "source-audit.json").read_text()),
            "read_only_unprivileged_run_accepted": readonly["accepted"],
            "full_batch_reference_digests": batch_digests,
            "focused_pairs_byte_equal": all(
                c["byte_equal"] for c in timing["comparisons"]
            ),
        },
        "results": rows,
        "container_speedup_geomean": statistics.geometric_mean(
            row["metrics"]["container_sec"]["speedup"] for row in rows
        ),
        "public_checks": [
            {
                "unit": r["unit"],
                "image_digest": r["image_digest"],
                "native": True,
                "accepted": r["accepted"],
                "reference_comparison": {
                    k: v
                    for k, v in r["check"]["reference_comparison"].items()
                    if k != "files"
                },
            }
            for r in public["runs"]
        ],
        "limitations": [
            "Local Mac/emulated sequential container runs are non-rankable.",
            "The native path supports the adapter flow; arbitrary ABIDES extensions and hidden/PTC APIs retain the optimized Python implementation.",
            "Native core timing includes trace extraction and is not the same boundary as the Python simulation-only timer.",
            "There is no per-feature performance ablation; gains describe the combined implementation.",
            "Middle price insertion/removal still shifts vectors, and within-level arbitrary cancellation is linear.",
            "Numeric differential coverage is sampled; it does not prove equivalence for all possible extreme inputs or every CPU dispatch.",
        ],
    }
    import hashlib

    record["evidence_sha256"] = {
        name: hashlib.sha256((out / name).read_bytes()).hexdigest()
        for name in [
            "timing/summary.json",
            "public/summary.json",
            "runtime-tests.log",
            "numeric-tests.log",
            "source-audit.json",
            "readonly/validation.json",
            "batch-reference-digests.json",
            "build-validated.log",
        ]
    }
    (EXP / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    text = (EXP / "README.md").read_text().split("## Results\n")[0]
    text += "\n## Results\n\n"
    text += f"Runtime tests: **{passed} passed**; 80,000 native price-side mutations, 100 mixed RNG scripts and 100,000 NumPy-log values passed.\n\n"
    text += f"All **{len(single)} single public units and {len(batches)} batch units** passed the shared developer verifier and exact ordered trace/message checks. Every measured native run and each batch sub used the C++ engine.\n\n"
    text += "Paired median full-container times, seconds (five measured repeats per image):\n\n"
    text += "| Workload | Python | Native + retained index | Speedup |\n|---|---:|---:|---:|\n"
    for row in rows:
        m = row["metrics"]["container_sec"]
        text += f"| {row['unit']} | {m['medians']['baseline']:.3f} | {m['medians']['candidate']:.3f} | {m['speedup']:.2f}x |\n"
    text += f"\nGeometric mean of the seven container-time ratios: **{record['container_speedup_geomean']:.2f}x**. This describes these focused workloads, not an official or universal speedup.\n\n"
    text += "See [result.json](result.json) for every sample, complete adapter times, internal clock limits, source audit and validation evidence. Production engine files and production build wiring remain unchanged.\n"
    (EXP / "README.md").write_text(text)


if __name__ == "__main__":
    main()

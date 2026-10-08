"""Executive summary: compare the combined ledger/arena implementation with previous develop.

This wrapper imports the existing differential checker and scoring gates. It
adds strict native provenance and byte/digest checks, retains every timed pair,
and refuses cases outside the experiment's predeclared scenario list.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

AREA = Path(__file__).resolve().parent


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def source_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root / "baselines/native").rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--candidate-image", required=True)
    ap.add_argument("--candidate-commit", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--controls-only", action="store_true")
    args = ap.parse_args()
    plan = json.loads((AREA / "plan.json").read_text())
    exp = next(x for x in plan["experiments"] if x["slug"] == args.slug)
    root = Path(exp["worktree"])
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if head != args.candidate_commit:
        raise RuntimeError("candidate commit differs from the declared checkout")
    if subprocess.check_output(["git", "diff", "HEAD", "--", "baselines"], cwd=root):
        raise RuntimeError("uncommitted production sources cannot be measured")
    initial_hashes = source_hashes(root)
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("focused_differential", root / "scripts/run_differential_experiment.py")
    d = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = d
    spec.loader.exec_module(d)
    original_once, original_exact = d.run_once, d.exact_tree
    original_container, original_docker = d.container_run, d.docker_output
    launch_bounds = {}

    def strict_container(command, docker, name, timeout):
        pos = command.index("run") + 1
        command[pos:pos] = ["-e", "T3_ENGINE=native", "-e", "T3_REQUIRE_NATIVE=1"]
        for flag in ["--network=none", "--cpus=4", "--memory=16g", "--memory-swap=16g"]:
            assert flag in command, (flag, command)
        start = time.monotonic_ns()
        try:
            return original_container(command, docker, name, timeout)
        finally:
            launch_bounds[name] = {"start": start, "finish": time.monotonic_ns()}

    def strict_docker(docker, argv):
        if argv[:1] == ["run"] and not any(x.startswith("--memory-swap") for x in argv):
            argv = ["run", "--memory-swap=16g", *argv[1:]]
        return original_docker(docker, argv)

    def strict_exact(unit, left, right):
        comparison = original_exact(unit, left, right)
        if not d.exact_ok(comparison) or not comparison.get("byte_equal"):
            raise RuntimeError("journal byte/schema/value comparison failed: " + json.dumps(comparison))
        return comparison

    def strict_once(a, unit, inputs, image, side, kind, index, directory, docker):
        record = original_once(a, unit, inputs, image, side, kind, index, directory, docker)
        name = record["command"][record["command"].index("--name") + 1]
        record["host_monotonic_interval_ns"] = launch_bounds[name]
        run_dir = directory / "runs" / unit.name / f"{kind}-{index:02d}" / side
        kept = run_dir / "retained"
        try:
            assert record["accepted"], record.get("error", record.get("check"))
            actual, phases, memory = {}, {}, {}
            for _, sub in d.trace_layout(unit):
                events = json.loads((kept / sub / "events.json").read_text())
                profile = json.loads((kept / sub / "profile.json").read_text())
                assert events.get("engine") == profile.get("engine") == "native", "Python fallback"
                for file, key in [("trace.parquet", "trace_sha256"), ("message_trace.parquet", "message_trace_sha256")]:
                    assert events[key] == d.sha(kept / sub / file), (file, "digest mismatch")
                actual[sub or "single"] = "native"
                phases[sub or "single"] = profile["phases"]
                memory[sub or "single"] = profile.get("peak_memory_bytes")
            record.update(actual_native=actual, phase_seconds_by_market=phases,
                          reported_process_peak_bytes_by_market=memory)
        except Exception as exc:
            record.update(accepted=False, native_audit_error=str(exc))
            d.dump(run_dir / "record.json", record)
            raise
        d.dump(run_dir / "record.json", record)
        return record

    d.run_once, d.exact_tree = strict_once, strict_exact
    d.container_run, d.docker_output = strict_container, strict_docker
    if args.controls_only:
        from throughput.run_unit import _stage_input
        output = args.out.resolve()
        output.mkdir(parents=True, exist_ok=False)
        docker = ["docker", "--context", "colima-agenthon"]
        records, comparisons = [], []
        control = {"executive_summary": "Untimed pinned correctness controls before paired timing. Both journals and actual native execution are required.", "complete": False, "accepted": False, "rankable": False, "runs": records, "comparisons": comparisons}
        d.dump(output / "summary.json", control)
        selected = list(dict.fromkeys(exp["units"] + exp["correctness_only_units"]))
        runargs = argparse.Namespace(trace_mode="buffered", platform="linux/amd64", timeout=600, baseline_batch_args_json=[], candidate_batch_args_json=[])
        try:
            for name in selected:
                unit = Path(plan["corpus"]) / name
                if any(d.corpus_check(unit).values()):
                    raise RuntimeError("corpus failed: " + name)
                staging = output / "inputs" / name
                staging.mkdir(parents=True)
                _stage_input(unit, staging, (unit / "batch.json").exists())
                kept = {}
                for side, img in [("baseline", plan["baseline_image"]), ("candidate", args.candidate_image)]:
                    record = strict_once(runargs, unit, staging, img, side, "correctness", 0, output, docker)
                    records.append(record)
                    kept[side] = output / "runs" / name / "correctness-00" / side / "retained"
                    d.dump(output / "summary.json", control)
                comparisons.append({"unit": name, **strict_exact(unit, kept["baseline"], kept["candidate"])})
                d.dump(output / "summary.json", control)
            control.update(complete=True, accepted=initial_hashes == source_hashes(root), source_hashes=initial_hashes)
        except Exception as exc:
            control["error"] = str(exc)
        d.dump(output / "summary.json", control)
        print(json.dumps({"controls": str(output), "complete": control["complete"], "accepted": control["accepted"], "error": control.get("error")}))
        return 0 if control["complete"] and control["accepted"] else 1
    rc = d.main(["run", "--baseline-image", plan["baseline_image"],
                 "--candidate-image", args.candidate_image,
                 "--baseline-commit", plan["base_commit"],
                 "--candidate-commit", args.candidate_commit,
                 "--units-dir", plan["corpus"], "--units", *exp["units"],
                 "--repeats", "5", "--trace-mode", "buffered", "--platform", "linux/amd64",
                 "--no-profile", "--timeout", "600", "--out", str(args.out)])
    output = args.out.resolve()
    summary = json.loads((output / "summary.json").read_text())
    complete = rc == 0 and summary.get("accepted") and initial_hashes == source_hashes(root)
    results = []
    for unit in exp["units"]:
        runs = {side: [r for r in summary["runs"] if r["unit"] == unit and r["side"] == side
                       and r["kind"] == "timing" and r.get("accepted")]
                for side in ("baseline", "candidate")}
        if not all(len(v) == 5 for v in runs.values()):
            continue
        samples = {s: [r["container_sec"] for r in rows] for s, rows in runs.items()}
        med = {s: statistics.median(v) for s, v in samples.items()}
        pairs = [{"index": i, "baseline_seconds": samples["baseline"][i],
                  "candidate_seconds": samples["candidate"][i],
                  "candidate_time_change_pct": 100 * (samples["candidate"][i] / samples["baseline"][i] - 1)}
                 for i in range(5)]
        secondary = {}
        for side, rows in runs.items():
            names = set(k for r in rows for phases in r["phase_seconds_by_market"].values() for k in phases)
            secondary[side] = {k: {"samples": [sum(p.get(k, 0) for p in r["phase_seconds_by_market"].values()) for r in rows]}
                               for k in sorted(names)}
            for value in secondary[side].values():
                value["median"] = statistics.median(value["samples"])
        results.append({"unit": unit, "container_seconds_samples": samples,
                        "median_container_seconds": med, "pairs": pairs,
                        "candidate_faster_pairs": sum(p["candidate_seconds"] < p["baseline_seconds"] for p in pairs),
                        "time_reduction_pct": 100 * (1 - med["candidate"] / med["baseline"]) if complete else None,
                        "time_change_pct": 100 * (med["candidate"] / med["baseline"] - 1) if complete else None,
                        "secondary_market_phase_sums": secondary})
    result = {"executive_summary": "Local paired comparison of one isolated native hypothesis. Positive time reduction means a shorter complete container run; all five samples and diagnostics are retained.",
              "slug": exp["slug"], "title": exp["title"], "branch": exp["branch"], "worktree": str(root),
              "base_commit": plan["base_commit"], "baseline_image_source_commit": plan["baseline_source_commit"],
              "candidate_implementation_commit": args.candidate_commit,
              "complete": bool(complete), "accepted": bool(complete), "rankable": False, "adopted": True,
              "policy": plan["policy"], "assigned_units": exp["units"], "images": summary.get("images"),
              "source_hashes": initial_hashes, "source_unchanged_during_measurement": initial_hashes == source_hashes(root),
              "counts": {"accepted_runs": sum(r.get("accepted", False) for r in summary["runs"]),
                         "timed_samples": sum(r["kind"] == "timing" for r in summary["runs"]),
                         "warmups": sum(r["kind"] == "warmup" for r in summary["runs"])},
              "results": results, "evidence_directory": str(output),
              "summary_sha256": d.sha(output / "summary.json"),
              "runner_sha256": d.sha(Path(__file__)), "shared_checker_sha256": d.sha(root / "scripts/run_differential_experiment.py"),
              "limitations": ["Mac ARM64 host with emulated Linux amd64 containers; not official timing hardware.",
                              "Native core timing includes trace finalization; it is not matcher-only time.",
                              "Batch per-market phase sums overlap or include per-market fixed costs and are secondary diagnostics.",
                              "Process peak values in profiles are not independent per-market memory peaks.",
                              "Historical Python measurements are motivation only; every control here is a fresh current-native run."],
              "error": summary.get("error")}
    dump(output / "result.json", result)
    print(json.dumps({"complete": complete, "results": [{"unit": x["unit"], "time_reduction_pct": x["time_reduction_pct"]} for x in results]}), flush=True)
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())

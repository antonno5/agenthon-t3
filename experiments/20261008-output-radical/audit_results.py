"""Executive summary: verify the four reports against every retained measurement.

This audit checks the frozen sources, schedule, clock samples and journal digests.
The unchanged shared checker owns schema/value comparisons and developer gates.
"""
from pathlib import Path
import hashlib
import json
import math
import statistics
import subprocess

AREA = Path(__file__).resolve().parent
plan = json.loads((AREA / "plan.json").read_text())
freeze = json.loads((AREA / "measurement-harness-freeze.json").read_text())["hashes"]
repo = Path(plan["corpus"]).parent

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1 << 20):
            h.update(block)
    return h.hexdigest()

for name in ("plan.json", "run_focused.py", "docker_slot.py"):
    assert sha(AREA / name) == freeze[name], name
assert sha(repo / "scripts/run_differential_experiment.py") == freeze["shared_checker"]
assert not subprocess.check_output(["git", "diff", plan["base_commit"], "--",
    "baselines", "units", "scripts", "throughput", "qfbench2_track_simulation", "templates"], cwd=repo)

reports = []
for exp in plan["experiments"]:
    result_path = Path(exp["experiment_directory"]) / "result.json"
    result = json.loads(result_path.read_text())
    assert result["complete"] and result["accepted"]
    assert result["source_unchanged_during_measurement"]
    assert result["rankable"] is False and result["adopted"] is False
    assert result["base_commit"] == plan["base_commit"]
    assert result["assigned_units"] == exp["units"]
    assert result["comparison_policy"] == exp["comparison"]
    preflight = json.loads((AREA / ("PREFLIGHT-" + exp["slug"] + ".json")).read_text())
    assert preflight.get("accepted", preflight.get("ready", False))
    assert result["images"]["baseline"]["digest"] == plan["baseline_image"]
    assert result["images"]["candidate"]["digest"] == preflight.get("candidate_image", preflight.get("image_id"))
    preflight_commit = preflight.get("implementation_commit", preflight.get("frozen_commit"))
    assert result["candidate_implementation_commit"] == preflight_commit
    assert result["runner_sha256"] == freeze["run_focused.py"]
    assert result["shared_checker_sha256"] == freeze["shared_checker"]
    assert result["counts"] == {"accepted_runs": 48, "timed_samples": 40, "warmups": 8}
    for name, digest in result["source_hashes"].items():
        frozen = subprocess.check_output(["git", "show",
            result["candidate_implementation_commit"] + ":" + name], cwd=exp["worktree"])
        assert hashlib.sha256(frozen).hexdigest() == digest, name
    evidence = Path(result["evidence_directory"])
    summary = json.loads((evidence / "summary.json").read_text())
    assert summary["accepted"] and sha(evidence / "summary.json") == result["summary_sha256"]
    assert len(summary["runs"]) == 48 and all(r["accepted"] for r in summary["runs"])
    for comparison in summary["comparisons"]:
        assert comparison["schema_equal"] and comparison["semantic_exact_equal"]
        if exp["comparison"] == "byte_exact":
            assert comparison["byte_equal"]
    journals = 0
    for record in summary["runs"]:
        assert record["image_digest"] == result["images"][record["side"]]["digest"]
        for flag in ("--network=none", "--cpus=4", "--memory=16g", "--memory-swap=16g"):
            assert flag in record["command"]
        assert set(record["actual_native"].values()) == {"native"}
        assert math.isfinite(record["container_sec"]) and record["container_sec"] > 0
        kept = evidence / "runs" / record["unit"] / f"{record['kind']}-{record['index']:02d}" / record["side"] / "retained"
        for events_path in kept.rglob("events.json"):
            events = json.loads(events_path.read_text())
            assert events["engine"] == "native"
            for filename, key in (("trace.parquet", "trace_sha256"),
                                  ("message_trace.parquet", "message_trace_sha256")):
                parquet = events_path.parent / filename
                assert parquet.stat().st_nlink == 1, str(parquet)
                assert sha(parquet) == events[key], str(parquet)
                journals += 1
    rows = []
    assert [x["unit"] for x in result["results"]] == exp["units"]
    for row in result["results"]:
        selected = [r for r in summary["runs"] if r["unit"] == row["unit"] and r["kind"] == "timing"]
        for index in range(5):
            paired = [r for r in selected if r["index"] == index]
            assert [r["side"] for r in paired] == (["baseline", "candidate"] if index % 2 == 0 else ["candidate", "baseline"])
        samples = {side: [r["container_sec"] for r in selected if r["side"] == side]
                   for side in ("baseline", "candidate")}
        assert samples == row["container_seconds_samples"]
        medians = {side: statistics.median(values) for side, values in samples.items()}
        assert medians == row["median_container_seconds"]
        percent = 100 * (1 - medians["candidate"] / medians["baseline"])
        assert abs(percent - row["time_reduction_pct"]) < 1e-10
        assert row["candidate_faster_pairs"] == sum(c < b for b, c in zip(samples["baseline"], samples["candidate"]))
        rows.append({"unit": row["unit"], "time_reduction_pct": percent,
                     "median_seconds": medians, "faster_pairs": row["candidate_faster_pairs"]})
    reports.append({"slug": exp["slug"], "candidate_commit": result["candidate_implementation_commit"],
        "result_sha256": sha(result_path), "journal_digests_checked": journals,
        "samples_checked": 40, "results": rows})

audit = {"executive_summary": "All four reports match their frozen sources and complete paired measurement records. Every retained journal digest was independently rechecked. Production code is unchanged.",
    "accepted": True, "rankable": False, "adopted": False,
    "timed_samples_checked": 160, "experiments": reports}
(AREA / "manager-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"accepted": True, "experiments": reports}, ensure_ascii=False))

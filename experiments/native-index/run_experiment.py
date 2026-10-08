"""Paired focused timing and candidate-only public correctness checks.

Executive summary: compare the new C++ implementation with the adopted Python
price-offset engine, preserving exact public journals and every measured repeat.
"""

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts import run_differential_experiment as runner  # noqa: E402
from throughput.run_unit import _stage_input  # noqa: E402

FOCUSED = [
    "t3-mp02-stp-oldest-baseline",
    "t3-mr-deep-book-state-size",
    "t3-mp05-cancel-churn-newest",
    "t3-s001-price-time-priority",
    "t3-s012-partial-fill-cancel-race",
    "t3-cancelmodify-lifecycle",
    "t3-mp07-heavy-flow-oldest",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--candidate", default="native-index:20261008")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--phase", choices=["smoke", "timing", "public"], required=True)
    a = ap.parse_args()
    folder = a.out.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    docker = ["docker", "--context", "colima-agenthon"]
    baseline = "sha256:4a54f2c8a59d8f7bd7d23373bf96e54025d01a7560289fdcf1a0f3d0a56fdfbe"
    candidate = subprocess.check_output(
        docker + ["image", "inspect", a.candidate, "--format", "{{.Id}}"], text=True
    ).strip()
    names = (
        FOCUSED
        if a.phase == "timing"
        else (
            ["t3-s001-price-time-priority"]
            if a.phase == "smoke"
            else sorted(
                p.name
                for p in (ROOT / "units").iterdir()
                if (p / "card.toml").exists() and p.name not in FOCUSED
            )
        )
    )
    summary = {
        "executive_summary": "Local non-rankable native indexed-engine experiment. Timings are paired against the existing optimized Python engine.",
        "complete": False,
        "accepted": False,
        "rankable": False,
        "adopted": False,
        "phase": a.phase,
        "baseline_image": baseline,
        "candidate_image": candidate,
        "policy": {
            "units": names,
            "repeats": a.repeats if a.phase == "timing" else 1,
            "warmups": 1 if a.phase == "timing" else 0,
            "platform": "linux/amd64",
            "context": "colima-agenthon",
            "cpus": 4,
            "memory": "16g",
            "network": "none",
            "containers": "sequential",
            "primary_clock": "Docker FinishedAt minus StartedAt",
            "simulation_clock_note": "Native core includes trace extraction; Python simulation phase excludes trace extraction.",
        },
        "source_hashes": {
            str(p.relative_to(ROOT)): runner.sha(p)
            for p in sorted(EXP.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts
        },
        "inputs": {},
        "runs": [],
        "comparisons": [],
    }
    args = argparse.Namespace(
        trace_mode="buffered",
        platform="linux/amd64",
        timeout=600,
        baseline_batch_args_json=[],
        candidate_batch_args_json=[],
    )

    def save():
        runner.dump(folder / "summary.json", summary)

    save()
    try:
        for name in names:
            unit = ROOT / "units" / name
            assert not any(runner.corpus_check(unit).values()), name
            staging = folder / "inputs" / name
            staging.mkdir(parents=True)
            _stage_input(unit, staging, (unit / "batch.json").exists())
            summary["inputs"][name] = {
                "unit_hashes": runner.tree_hashes(unit),
                "staged_hashes": runner.tree_hashes(staging),
            }
            schedule = (
                [("correctness", 0)]
                if a.phase != "timing"
                else [("warmup", 0)] + [("timing", i) for i in range(a.repeats)]
            )
            first = None
            for kind, i in schedule:
                sides = (
                    ["candidate"]
                    if a.phase != "timing"
                    else (
                        ["baseline", "candidate"]
                        if i % 2 == 0
                        else ["candidate", "baseline"]
                    )
                )
                paths = {}
                for side in sides:
                    print("RUN", name, kind, i, side, flush=True)
                    record = runner.run_once(
                        args,
                        unit,
                        staging,
                        baseline if side == "baseline" else candidate,
                        side,
                        kind,
                        i,
                        folder,
                        docker,
                    )
                    summary["runs"].append(record)
                    save()
                    if not record["accepted"]:
                        raise RuntimeError(
                            json.dumps(record.get("error", record.get("check")))
                        )
                    kept = (
                        folder / "runs" / name / f"{kind}-{i:02d}" / side / "retained"
                    )
                    paths[side] = kept
                    if side == "candidate":
                        files = (
                            list(kept.glob("*/events.json"))
                            if (unit / "batch.json").exists()
                            else [kept / "events.json"]
                        )
                        assert files and all(
                            json.loads(p.read_text()).get("engine") == "native"
                            for p in files
                        ), "Unexpected Python fallback"
                        if first is not None:
                            c = runner.exact_tree(unit, first, kept)
                            assert runner.exact_ok(c)
                            summary["comparisons"].append(
                                {
                                    "unit": name,
                                    "kind": kind,
                                    "index": i,
                                    "comparison": "candidate_stability",
                                    **c,
                                }
                            )
                        else:
                            first = kept
                if "baseline" in paths:
                    c = runner.exact_tree(unit, paths["baseline"], paths["candidate"])
                    assert runner.exact_ok(c)
                    summary["comparisons"].append(
                        {
                            "unit": name,
                            "kind": kind,
                            "index": i,
                            "comparison": "baseline_candidate",
                            **c,
                        }
                    )
                save()
        if a.phase == "timing":
            summary["results"] = []
            for name in names:
                result = {"unit": name, "metrics": {}}
                for field in ["container_sec", "adapter_sec_self_reported"]:
                    samples = {
                        side: [
                            r[field]
                            for r in summary["runs"]
                            if r["unit"] == name
                            and r["side"] == side
                            and r["kind"] == "timing"
                        ]
                        for side in ["baseline", "candidate"]
                    }
                    med = {side: statistics.median(v) for side, v in samples.items()}
                    result["metrics"][field] = {
                        "samples": samples,
                        "medians": med,
                        "speedup": med["baseline"] / med["candidate"],
                        "time_change_percent": 100
                        * (med["candidate"] / med["baseline"] - 1),
                    }
                summary["results"].append(result)
        summary.update(complete=True, accepted=True)
        save()
        print("COMPLETE", a.phase, len(summary["runs"]), "runs", flush=True)
    except BaseException as e:
        summary["error"] = f"{type(e).__name__}: {e}"
        save()
        raise


if __name__ == "__main__":
    main()

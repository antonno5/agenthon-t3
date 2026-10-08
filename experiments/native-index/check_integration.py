"""Check production integration without repeating the performance experiment.

Executive summary: compare installed production sources with the tested native
image, verify focused journals and one batch, and exercise the Python fallback
and the read-only runtime. Every container runs sequentially without a network.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts import run_differential_experiment as runner  # noqa: E402
from throughput.run_unit import _stage_input  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", default="track3-native:20261008")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--experiment-out", type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    old = args.experiment_out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    docker = ["docker", "--context", "colima-agenthon"]
    image = subprocess.check_output(
        docker + ["image", "inspect", args.image, "--format", "{{.Id}}"], text=True
    ).strip()
    result = {
        "executive_summary": "The tested native implementation is installed in the production Docker recipe; optimized Python matching is retained as fallback. Targeted integration checks do not repeat the historical timing experiment.",
        "adopted": True,
        "complete": False,
        "accepted": False,
        "rankable": False,
        "date": "2026-10-08",
        "branch": "codex/develop",
        "production_image": image,
        "experiment_result": "experiments/native-index/result.json",
        "evidence_directory": str(out.relative_to(ROOT)),
        "checks": [],
        "policy": {"platform": "linux/amd64", "cpus": 4, "memory": "16g", "network": "none", "containers": "sequential", "timing": "excluded; no new performance claim"},
    }

    def save():
        runner.dump(out / "integration.json", result)

    save()
    try:
        audit = json.loads(subprocess.check_output(
            docker + ["run", "--rm", "--platform", "linux/amd64", "--network=none",
                      "--cpus=4", "--memory=16g", "-v", f"{EXP}:/audit:ro", image,
                      "python", "/audit/source_audit.py"], text=True
        ))
        runner.dump(out / "installed-source.json", audit)
        previous = json.loads((old / "candidate-installed-source.json").read_text())
        previous_files = {k: v for k, v in previous["files"].items() if not k.startswith("native_extension/")}
        current_files = {k: v for k, v in audit["files"].items() if not k.startswith("native_extension/")}
        assert audit["versions"] == previous["versions"]
        assert current_files == previous_files, "installed Python source drift"
        native_sources = {}
        for p in (EXP / "native").rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                rel = p.relative_to(EXP / "native")
                target = ROOT / "baselines/native" / rel
                assert p.read_bytes() == target.read_bytes(), str(rel)
                native_sources[str(rel)] = runner.sha(target)
        assert (EXP / "build/native_build.py").read_bytes() == (ROOT / "baselines/build_native.py").read_bytes()
        result["source_identity"] = {
            "installed_python_sources_equal_to_tested_image": True,
            "dependency_versions_equal": True,
            "native_sources_equal": True,
            "builder_equal": True,
            "native_source_hashes": native_sources,
            "production_source_hashes": {
                str(p.relative_to(ROOT / "baselines")): runner.sha(p)
                for p in sorted((ROOT / "baselines").rglob("*"))
                if p.is_file() and "__pycache__" not in p.parts
            },
            "installed_source_audit_sha256": runner.sha(out / "installed-source.json"),
            "extension_sha256": {k: v for k, v in audit["files"].items() if k.startswith("native_extension/")},
        }
        build_log = out / "build.log"
        assert "80,000" in build_log.read_text(), "production builder did not complete the book differential test"
        result["builder_book_test"] = {"accepted": True, "mutations": 80000, "build_log_sha256": runner.sha(build_log)}
        save()
        options = argparse.Namespace(trace_mode="buffered", platform="linux/amd64", timeout=600,
                                     baseline_batch_args_json=[], candidate_batch_args_json=[])
        names = ["t3-mp02-stp-oldest-baseline", "t3-mr-deep-book-state-size",
                 "t3-mp05-cancel-churn-newest", "t3-gbatch-hetero-mix",
                 "t3-s001-price-time-priority"]
        for name in names:
            unit = ROOT / "units" / name
            staging = out / "inputs" / name
            staging.mkdir(parents=True)
            _stage_input(unit, staging, (unit / "batch.json").exists())
            print("CHECK", name, flush=True)
            record = runner.run_once(options, unit, staging, image, "candidate", "integration", 0, out, docker)
            assert record["accepted"], record.get("error", record.get("check"))
            kept = out / "runs" / name / "integration-00/candidate/retained"
            events = list(kept.glob("*/events.json")) if (unit / "batch.json").exists() else [kept / "events.json"]
            assert events and all(json.loads(p.read_text())["engine"] == "native" for p in events)
            history = list((old / "timing/runs" / name).glob("*/candidate/retained"))
            if not history:
                history = list((old / "public/runs" / name).glob("*/candidate/retained"))
            assert history, "Missing experimental output"
            comparison = runner.exact_tree(unit, history[0], kept)
            assert runner.exact_ok(comparison)
            result["checks"].append({"unit": name, "engine": "native", "accepted": True,
                                     "journals_equal_to_tested_image": comparison,
                                     "record": str((kept.parent / "record.json").relative_to(ROOT))})
            save()
        name = "t3-s001-price-time-priority"
        unit = ROOT / "units" / name
        staging = out / "inputs" / name
        options.trace_mode = "verify"
        print("CHECK Python verify fallback", flush=True)
        record = runner.run_once(options, unit, staging, image, "candidate", "python-verify", 0, out, docker)
        assert record["accepted"], record.get("error", record.get("check"))
        assert record["events"]["engine"] == "python"
        result["checks"].append({"unit": name, "engine": "python", "mode": "verify", "accepted": True,
                                 "record": str((out / "runs" / name / "python-verify-00/candidate/record.json").relative_to(ROOT))})
        save()
        raw = out / "readonly/raw"
        raw.mkdir(parents=True)
        raw.chmod(0o777)
        cmd = docker + ["run", "--rm", "--platform", "linux/amd64", "--network=none",
                        "--cpus=4", "--memory=16g", "--memory-swap=16g", "--read-only",
                        "--user", "65534:65534", "--tmpfs", "/tmp:rw,nosuid,size=128m",
                        "-v", f"{staging}:/input:ro", "-v", f"{raw}:/output", image,
                        "simulate", "--config", "/input/scenario.json", "--out",
                        "/output/trace.parquet", "--engine", "native"]
        print("CHECK read-only native runtime", flush=True)
        process = subprocess.run(cmd, capture_output=True, timeout=600)
        (raw.parent / "stdout.log").write_bytes(process.stdout)
        (raw.parent / "stderr.log").write_bytes(process.stderr)
        assert process.returncode == 0, process.stderr.decode()
        check = runner.validate_output(unit, raw, raw.parent / "retained")
        assert check["accepted"]
        assert json.loads((raw / "events.json").read_text())["engine"] == "native"
        runner.dump(raw.parent / "validation.json", {"accepted": True, "command": cmd, "check": check})
        result["checks"].append({"unit": name, "engine": "native", "read_only": True, "uid": 65534, "accepted": True})
        result.update(accepted=True, complete=True)
        save()
        print("COMPLETE", len(result["checks"]), "targeted integration checks", flush=True)
    except BaseException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        save()
        raise


if __name__ == "__main__":
    main()

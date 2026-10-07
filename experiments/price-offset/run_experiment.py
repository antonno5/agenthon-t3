"""Run only the experimental candidate; compare against retained baseline evidence."""

from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, default=root / "out/price-offset-20261007")
out = parser.parse_args().out.resolve()
out.mkdir(parents=True, exist_ok=True)
assert not (
    out / "state.json"
).exists(), "Choose a fresh --out directory; preserve existing evidence"
exp = root / "experiments/price-offset"
docker = ["docker", "--context", "colima-agenthon"]
policy = json.loads((exp / "policy.json").read_text())
assert (
    hashlib.sha256((exp / "state.py").read_bytes()).hexdigest()
    == policy["candidate_state_sha256"]
)
image = subprocess.check_output(
    docker + ["image", "inspect", policy["candidate_tag"], "--format", "{{.Id}}"],
    text=True,
).strip()
state = {
    "executive_summary": "Candidate-only offset experiment compared to retained numeric-vector timings and exact journals.",
    "rankable": False,
    "complete": False,
    "candidate_image": image,
    "policy_sha256": hashlib.sha256((exp / "policy.json").read_bytes()).hexdigest(),
    "phases": [],
}


def persist():
    (out / "state.json").write_text(json.dumps(state, indent=2) + "\n")


def run(name, cmd, path):
    print("PHASE", name, flush=True)
    state["active_phase"] = name
    persist()
    with path.open("w") as f:
        result = subprocess.run(
            [str(x) for x in cmd], stdout=f, stderr=subprocess.STDOUT
        )
    state["phases"].append(
        {
            "name": name,
            "exit_code": result.returncode,
            "log": str(path.relative_to(root)),
        }
    )
    persist()
    assert result.returncode == 0, (name, result.returncode)


persist()
try:
    run(
        "installed source audit",
        docker
        + [
            "run",
            "--rm",
            "--platform=linux/amd64",
            "--network=none",
            "-v",
            str(root / "out/python-book-layers/image_source_audit.py")
            + ":/audit.py:ro",
            image,
            "python",
            "/audit.py",
        ],
        out / "installed-source.json",
    )
    audit = json.loads((out / "installed-source.json").read_text())
    base = json.loads(
        (root / "out/price-vector-20261007/installed-source.json").read_text()
    )
    changed = [
        k
        for k in sorted(set(base["files"]) | set(audit["files"]))
        if base["files"].get(k) != audit["files"].get(k)
    ]
    assert changed == ["markets/matching/state.py"], changed
    assert audit["identity"] == base["identity"]
    assert (
        audit["files"]["markets/matching/state.py"] == policy["candidate_state_sha256"]
    )
    state["installed_changed_files"] = changed
    persist()
    tests = out / "runtime_tests"
    tests.mkdir(exist_ok=False)
    shutil.copyfile(
        root / "experiments/python-book-layers/test_runtime.py",
        tests / "test_runtime.py",
    )
    shutil.copyfile(exp / "test_vector.py", tests / "test_vector.py")
    shutil.copyfile(exp / "test_offset.py", tests / "test_offset.py")
    upstream = (
        root
        / "out/python-book-layers/upstream/abides-jpmc-public-f9cbe51342b7dedd9587e4e069040d68a5c6477f/abides-markets"
    )
    cmd = docker + [
        "run",
        "--rm",
        "--platform=linux/amd64",
        "--network=none",
        "--cpus=4",
        "--memory=16g",
        "-e",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "-e",
        "PYTHONPATH=/tooling:/upstream:/runtime_tests",
        "-e",
        "BOOK_LAYERS_CONTROL_SOURCE=/control-source",
        "-v",
        str(root / "out/python-book-layers/pytest-tooling") + ":/tooling:ro",
        "-v",
        str(upstream / "tests") + ":/upstream/tests:ro",
        "-v",
        str(upstream / "abides_markets") + ":/control-source:ro",
        "-v",
        str(tests) + ":/runtime_tests:ro",
        image,
        "python",
        "-m",
        "pytest",
        "/upstream/tests/orderbook",
        "/runtime_tests/test_runtime.py",
        "/runtime_tests/test_vector.py",
        "/runtime_tests/test_offset.py",
        "-q",
        "-o",
        "addopts=",
    ]
    run("targeted order-book runtime tests", cmd, out / "runtime-tests.log")
    print((out / "runtime-tests.log").read_text()[-350:], flush=True)
    micro = root / "experiments/price-search-comparison/microbench.py"
    expected_micro = json.loads(
        (root / "experiments/price-search-comparison/policy.json").read_text()
    )["synthetic_diagnostics"]["script_sha256"]
    assert hashlib.sha256(micro.read_bytes()).hexdigest() == expected_micro
    state["micro_script_sha256"] = expected_micro
    mout = out / "micro"
    mout.mkdir(exist_ok=False)
    for i in range(policy["micro_repeats"]):
        cmd = docker + [
            "run",
            "--rm",
            "--platform=linux/amd64",
            "--network=none",
            "--cpus=4",
            "--memory=16g",
            "-v",
            str(micro) + ":/microbench.py:ro",
            "-v",
            str(mout) + ":/results",
            image,
            "python",
            "/microbench.py",
            "--out",
            f"/results/vector-{i:02d}.json",
            "--variant",
            "price-vector",
            "--pair",
            str(i),
        ]
        run(f"micro {i}", cmd, out / f"micro-{i:02d}.log")
        measured = json.loads((mout / f"vector-{i:02d}.json").read_text())["results"]
        saved = json.loads(
            (root / f"out/price-vector-20261007/micro/vector-{i:02d}.json").read_text()
        )["results"]
        assert len(measured) == len(saved) == 30
        for a, b in zip(saved, measured):
            for field in ["levels", "phase", "operations", "domain_sha256"]:
                assert a[field] == b[field], (field, a, b)
    state["micro_domain_comparisons"] = 210
    persist()
    sys.path.insert(0, str(root))
    import scripts.run_differential_experiment as runner

    old_folder = root / "out/price-vector-20261007/simulations"
    old = json.loads((old_folder / "summary.json").read_text())
    assert old["accepted"] and old["candidate_image"]["digest"] == policy["baseline_id"]
    meta = runner.image_metadata(docker, image, "linux/amd64")
    assert meta["versions"] == old["candidate_image"]["versions"]
    folder = out / "simulations"
    folder.mkdir(exist_ok=False)
    summary = {
        "executive_summary": "New offset candidate runs only, compared with saved exact-image numeric-vector timings. Historical comparison is not paired or rankable.",
        "rankable": False,
        "complete": False,
        "accepted": False,
        "baseline_evidence": str(old_folder / "summary.json"),
        "baseline_image": policy["baseline_id"],
        "candidate_image": meta,
        "runs": [],
        "comparisons": [],
        "inputs": {},
    }
    args = argparse.Namespace(
        trace_mode="buffered",
        platform="linux/amd64",
        timeout=600,
        baseline_batch_args_json=[],
        candidate_batch_args_json=[],
    )
    # Instrumentation is a separate process and never enters measured repeats.
    for name in policy["diagnostic_units"]:
        unit = root / "units" / name
        assert runner.tree_hashes(unit) == old["inputs"][name]["unit_hashes"]
        diag = out / "diagnostics" / name
        raw = diag / "output"
        raw.mkdir(parents=True)
        cmd = docker + [
            "run",
            "--rm",
            "--platform=linux/amd64",
            "--network=none",
            "--cpus=4",
            "--memory=16g",
            "-v",
            str(unit) + ":/input:ro",
            "-v",
            str(raw) + ":/output",
            "-v",
            str(diag) + ":/diagnostics",
            "-v",
            str(exp / "diagnose.py") + ":/diagnose.py:ro",
            image,
            "python",
            "/diagnose.py",
            "--diagnostics",
            "/diagnostics/counts.json",
            "--config",
            "/input/scenario.json",
            "--out",
            "/output/trace.parquet",
            "--trace-mode",
            "buffered",
        ]
        run("untimed cancellation diagnostics", cmd, diag / "run.log")
        check = runner.validate_output(unit, raw, diag / "retained")
        assert check["accepted"], check
        comparison = runner.exact_tree(
            unit,
            old_folder / "runs" / name / "timing-00/candidate/retained",
            diag / "retained",
        )
        assert runner.exact_ok(comparison)
        runner.dump(
            diag / "validation.json",
            {"check": check, "comparison": comparison, "excluded_from_timings": True},
        )
        state["diagnostic_runs"] = 1
        persist()
    for name in policy["units"]:
        unit = root / "units" / name
        assert runner.tree_hashes(unit) == old["inputs"][name]["unit_hashes"], name
        assert not any(runner.corpus_check(unit).values()), name
        staging = folder / "inputs" / name
        staging.mkdir(parents=True)
        shutil.copyfile(unit / "scenario.json", staging / "scenario.json")
        summary["inputs"][name] = old["inputs"][name]
        first = None
        for kind, index in [("warmup", 0)] + [
            ("timing", i) for i in range(policy["repeats"])
        ]:
            print("RUN", name, kind, index, "candidate only", flush=True)
            record = runner.run_once(
                args, unit, staging, image, "candidate", kind, index, folder, docker
            )
            summary["runs"].append(record)
            runner.dump(folder / "summary.json", summary)
            assert record["accepted"], record.get("error", record.get("check"))
            kept = folder / "runs" / name / f"{kind}-{index:02d}" / "candidate/retained"
            comparison = runner.exact_tree(
                unit, old_folder / "runs" / name / "timing-00/candidate/retained", kept
            )
            assert runner.exact_ok(comparison)
            summary["comparisons"].append(
                {
                    "unit": name,
                    "kind": kind,
                    "index": index,
                    "comparison": "saved_vector_candidate",
                    **comparison,
                }
            )
            if first is not None:
                stability = runner.exact_tree(unit, first, kept)
                assert runner.exact_ok(stability)
                summary["comparisons"].append(
                    {
                        "unit": name,
                        "kind": kind,
                        "index": index,
                        "comparison": "candidate_stability",
                        **stability,
                    }
                )
            else:
                first = kept
            runner.dump(folder / "summary.json", summary)
    summary.update(complete=True, accepted=True)
    runner.dump(folder / "summary.json", summary)
    state.update(
        complete=True,
        active_phase=None,
        simulator_runs=len(summary["runs"]),
        exact_comparisons=len(summary["comparisons"]),
    )
    persist()
    print("EXPERIMENT COMPLETE", image, flush=True)
except BaseException as exc:
    state["error"] = f"{type(exc).__name__}: {exc}"
    persist()
    raise

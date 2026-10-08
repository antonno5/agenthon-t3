"""Executive summary: check the three adopted optimizations together against production.

Run from any directory. This compiles the real combined engine and a frozen
production engine, compares full outputs, and checks registry lifetime rules.
Host checks make no performance claim; pinned Docker evidence is separate.
"""
from pathlib import Path
import hashlib
import json
import os
import platform
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = "94e66380b9152d76a193ee84c70a3660c6098845"
OUT = ROOT / "out/native-adoption-20261008/host"
OUT.mkdir(parents=True, exist_ok=True)
baseline = OUT / "baseline"
baseline.mkdir(exist_ok=True)
for name in ("engine.cpp", "engine.hpp", "book.hpp", "rng.hpp"):
    (baseline / name).write_bytes(subprocess.check_output(
        ["git", "show", f"{BASE}:baselines/native/{name}"], cwd=ROOT))

CXX = os.environ.get("CXX", "c++")
COMMON = [CXX, "-std=c++17", "-fno-fast-math", "-ffp-contract=off", "-Wall", "-Wextra"]
checks = []


def run(name, command):
    result = subprocess.run(command, capture_output=True, text=True)
    (OUT / f"{name}.log").write_text(result.stdout + result.stderr)
    checks.append({"name": name, "command": command, "exit_code": result.returncode,
                   "stdout": result.stdout, "stderr": result.stderr})
    result.check_returncode()


for mode, flags in [("optimized", ["-O2"]),
                    ("sanitized", ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"])]:
    obj = OUT / f"baseline-{mode}.o"
    binary = OUT / f"integration-{mode}"
    run(f"baseline-compile-{mode}", COMMON + flags + ["-Dt3=t3_baseline", "-c", str(baseline / "engine.cpp"), "-o", str(obj)])
    run(f"integration-compile-{mode}", COMMON + flags + ["-I" + str(ROOT / "baselines/native"), "-I" + str(OUT),
                                                       str(HERE / "host_checks.cpp"), str(obj), "-o", str(binary)])
    run(f"integration-test-{mode}", [str(binary)])
    registry = OUT / f"registry-{mode}"
    run(f"registry-compile-{mode}", COMMON + flags + ["-Werror", "-I" + str(ROOT / "baselines/native"),
                                                    str(ROOT / "baselines/native/tests/agent_orders_test.cpp"), "-o", str(registry)])
    run(f"registry-test-{mode}", [str(registry)])

report = {"executive_summary": "Optimized and ASan/UBSan checks passed for the combined trace path and agent registry. Exact complete simulation columns match the frozen production engine.",
          "accepted": True, "baseline_commit": BASE, "platform": platform.platform(), "checks": checks,
          "test_source_sha256": hashlib.sha256((HERE / "host_checks.cpp").read_bytes()).hexdigest(),
          "timing_claim": False}
(HERE / "host_checks.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"accepted": True, "checks": len(checks), "stdout": [c['stdout'] for c in checks if c['stdout']]}, indent=2))

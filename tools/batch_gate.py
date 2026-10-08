"""Run an image's simulate-batch on every public t3-gbatch unit under the platform flags and
score it with the organizers' own gates (batch.score_isolation + batch.check_aggregate).
usage (from track3-simulation-public, with .venv313 python): batch_gate.py IMAGE [ENV=VAL ...]"""
import json, os, pathlib, subprocess, sys, tempfile, time, inspect
from qfbench2_track_simulation import batch as B
img = sys.argv[1]; envs = sys.argv[2:]
flags = ["--rm", "--read-only", "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop=ALL",
         "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
         "--network=none", "--cpus", "4", "--pids-limit", "256", "--ulimit", "nofile=1024:1024"]
for e in envs: flags += ["-e", e]
units = sorted(p for p in pathlib.Path("units").iterdir() if (p / "batch.json").exists())
allok = True
for u in units:
    out = pathlib.Path(tempfile.mkdtemp(prefix="bg-", dir="/tmp/claude-1001"))
    t0 = time.perf_counter()
    p = subprocess.run(["docker", "run", *flags, "-v", f"{u.resolve()}/scenarios:/input/scenarios:ro", "-v", f"{out}:/output",
                        img, "simulate-batch", "--batch-dir", "/input/scenarios", "--out-dir", "/output"], capture_output=True, text=True)
    wall = time.perf_counter() - t0
    ok_iso, fails = B.score_isolation(u, out, 6, None, {})
    agg = json.loads((out / "batch_events.json").read_text())
    try:
        res = B.check_aggregate(out, B.load_subs(u))
        ok_agg = res[0] if isinstance(res, tuple) else bool(res)
        if not ok_agg: ok_agg = f"FAIL {res[1][:1] if isinstance(res, tuple) else res}"
    except Exception as e:
        ok_agg = f"error {e}"
    engines = sorted({json.loads((out / s / "events.json").read_text()).get("engine", "?") for s in [x["sub"] for x in agg["per_scenario"]]})
    print(f"{u.name}: exit={p.returncode} isolation={'PASS' if ok_iso else 'FAIL '+str(fails[:1])} aggregate={ok_agg} engines={engines} wall={wall:.2f}s")
    allok &= p.returncode == 0 and ok_iso and ok_agg is True
    subprocess.run(["rm", "-rf", str(out)])
print("ALL OK" if allok else "PROBLEMS"); sys.exit(0 if allok else 1)

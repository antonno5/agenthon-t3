"""Throughput of an image over ALL 71 public units (65 single-scenario + 6 batch), each run once
under platform-like flags. Per unit: events / time for
  window = Docker StartedAt..FinishedAt   and   full = create+start+rm wall time.
Batch units use simulate-batch and batch_events.json total_events. Prints arithmetic/geometric
means (the leaderboard ranks by the arithmetic mean over the roster).
usage: roster71.py IMAGE UNITS_DIR [--reps N]"""
import json, math, os, pathlib, subprocess, sys, tempfile, time
from datetime import datetime
img, units = sys.argv[1], pathlib.Path(sys.argv[2])
reps = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 1
flags = ["--network", "none", "--read-only", "--user", f"{os.getuid()}:{os.getgid()}",
         "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m", "--cpus", "4", "--pids-limit", "256"]
f = lambda x: datetime.fromisoformat(x[:26].rstrip("Z"))
rows = []
for u in sorted(units.iterdir()):
    batch = (u / "batch.json").exists()
    if not batch and not (u / "scenario.json").exists():
        continue
    best_w = best_f = None
    for _ in range(reps):
        out = pathlib.Path(tempfile.mkdtemp(prefix="r71-", dir="/tmp/claude-1001"))
        if batch:
            cmd = ["-v", f"{u}/scenarios:/input/scenarios:ro", "-v", f"{out}:/output", img,
                   "simulate-batch", "--batch-dir", "/input/scenarios", "--out-dir", "/output"]
        else:
            cmd = ["-v", f"{u}:/input:ro", "-v", f"{out}:/output", img,
                   "simulate", "--config", "/input/scenario.json", "--out", "/output/trace.parquet"]
        t0 = time.perf_counter()
        cid = subprocess.run(["docker", "create", *flags, *cmd], capture_output=True, text=True).stdout.strip()
        subprocess.run(["docker", "start", "-a", cid], capture_output=True)
        st = subprocess.run(["docker", "inspect", "-f", "{{.State.StartedAt}} {{.State.FinishedAt}}", cid], capture_output=True, text=True).stdout.split()
        subprocess.run(["docker", "rm", cid], capture_output=True)
        t1 = time.perf_counter()
        n = json.loads((out / ("batch_events.json" if batch else "events.json")).read_text())["total_events" if batch else "n_events"]
        subprocess.run(["rm", "-rf", str(out)])
        w, fl = (f(st[1]) - f(st[0])).total_seconds(), t1 - t0
        best_w = w if best_w is None else min(best_w, w); best_f = fl if best_f is None else min(best_f, fl)
    rows.append((u.name, batch, n, n / best_w, n / best_f))
am = lambda xs: sum(xs) / len(xs); gm = lambda xs: math.exp(sum(map(math.log, xs)) / len(xs))
W = [r[3] for r in rows]; F = [r[4] for r in rows]; BW = [r[3] for r in rows if r[1]]
print(f"{img}: units={len(rows)} window arith={am(W):.0f} geo={gm(W):.0f} | full arith={am(F):.0f} geo={gm(F):.0f} | batch-only window arith={am(BW):.0f}")
if "--per-unit" in sys.argv:
    for r in rows: print(f"  {r[0]:40s} {'B' if r[1] else ' '} n={r[2]:>9} window={r[3]:>10.0f} full={r[4]:>10.0f}")

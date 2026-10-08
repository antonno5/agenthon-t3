"""Per-unit throughput of an image over every public single-scenario unit, two timings:
  window = Docker StartedAt..FinishedAt (official Final definition),
  full   = wall time of `docker run` incl. create/start/remove (what a naive harness sees).
Prints arithmetic and geometric means of n_events / time. usage: roster_time.py IMAGE UNITS_DIR"""
import json, math, pathlib, subprocess, sys, tempfile, time
from datetime import datetime
img, units = sys.argv[1], pathlib.Path(sys.argv[2])
flags = ["--network", "none", "--read-only", "--user", "65534:65534", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m", "--cpus", "4"]
win, full, ev = [], [], []
f = lambda x: datetime.fromisoformat(x[:26].rstrip("Z"))
for u in sorted(p for p in units.iterdir() if (p / "scenario.json").exists()):
    out = pathlib.Path(tempfile.mkdtemp(prefix="rt-", dir="/tmp/claude-1001")); out.chmod(0o777)
    t0 = time.perf_counter()
    cid = subprocess.run(["docker", "create", *flags, "-v", f"{u}:/input:ro", "-v", f"{out}:/output", img, "simulate", "--config", "/input/scenario.json", "--out", "/output/trace.parquet"], capture_output=True, text=True).stdout.strip()
    subprocess.run(["docker", "start", "-a", cid], capture_output=True)
    st = subprocess.run(["docker", "inspect", "-f", "{{.State.StartedAt}} {{.State.FinishedAt}} {{.State.ExitCode}}", cid], capture_output=True, text=True).stdout.split()
    subprocess.run(["docker", "rm", cid], capture_output=True)
    t1 = time.perf_counter()
    n = json.loads((out / "events.json").read_text())["n_events"]
    subprocess.run(["rm", "-rf", str(out)])
    w = (f(st[1]) - f(st[0])).total_seconds()
    win.append(n / w); full.append(n / (t1 - t0)); ev.append(n)
am = lambda xs: sum(xs) / len(xs); gm = lambda xs: math.exp(sum(map(math.log, xs)) / len(xs))
print(f"{img}: units={len(ev)} window arith={am(win):.0f} geo={gm(win):.0f} | full arith={am(full):.0f} geo={gm(full):.0f}")

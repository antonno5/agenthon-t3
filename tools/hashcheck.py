"""Run every public unit through `python -m abides_fork.simulate` (no Docker) and compare
trace/message_trace sha256 with the unit's reference events.json. Also reports the full
process wall time per unit (closer to the official container-window timing than the
self-reported in-sim wall clock).

usage: hashcheck.py UNITS_DIR [--workers N] [--only substr]
Python/PYTHONPATH come from the environment (see tools/env.sh).
"""
import argparse, json, math, os, pathlib, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

ap = argparse.ArgumentParser()
ap.add_argument("units")
ap.add_argument("--workers", type=int, default=4)
ap.add_argument("--only", default="")
ap.add_argument("--py", default=sys.executable)
a = ap.parse_args()
units = sorted(p for p in pathlib.Path(a.units).iterdir() if (p / "scenario.json").exists() and a.only in p.name)
tmp = pathlib.Path(tempfile.mkdtemp(prefix="hc-", dir=os.environ.get("HC_TMP", "/tmp")))

def run(u):
    ref = json.loads((u / "events.json").read_text())
    out = tmp / u.name
    out.mkdir()
    t0 = time.perf_counter()
    p = subprocess.run([a.py, "-W", "ignore", "-m", "abides_fork.simulate", "--config", str(u / "scenario.json"),
                        "--out", str(out / "trace.parquet")], capture_output=True, text=True, cwd=out)
    wall = time.perf_counter() - t0
    if p.returncode != 0:
        return u.name, "ERROR", wall, ref["n_events"], p.stderr[-800:]
    ev = json.loads((out / "events.json").read_text())
    ok = ev["trace_sha256"] == ref["trace_sha256"] and ev["message_trace_sha256"] == ref["message_trace_sha256"]
    return u.name, "OK" if ok else "MISMATCH", wall, ev["n_events"], ""

with ThreadPoolExecutor(a.workers) as ex:
    res = list(ex.map(run, units))
bad = [r for r in res if r[1] != "OK"]
for r in res:
    if r[1] != "OK":
        print(r[0], r[1], r[4])
rates = [r[3] / r[2] for r in res if r[3]]
print(f"units={len(res)} ok={len(res)-len(bad)} bad={len(bad)}  process-rate geomean={math.exp(sum(map(math.log, rates))/len(rates)):.0f} "
      f"arith={sum(rates)/len(rates):.0f} total_wall={sum(r[2] for r in res):.1f}s")
subprocess.run(["rm", "-rf", str(tmp)])
sys.exit(1 if bad else 0)

"""Local estimate of the Development score, with the platform's per-unit overhead F fixed.

usage: devscore.py UNITS_DIR BIN_DIR [BIN_DIR ...] [--reps N] [--F 0.50] [--out-dir DIR]

Development scores a unit as n_events / (container create -> remove) and ranks the mean over
units. Model: time = F + w, with w our process time (measured here: the binaries' `simulate` /
`simulate-batch`, each unit run --reps times interleaved, minimum taken) and F the platform's
fixed per-unit cost (fitted to past submissions: 0.50 s in a quiet period, 0.53-0.56 s busy).
Prints the predicted score per binary for a few F, and the units that weigh most.
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time

ap = argparse.ArgumentParser()
ap.add_argument("units")
ap.add_argument("bins", nargs="+")
ap.add_argument("--reps", type=int, default=3)
ap.add_argument("--F", type=float, default=0.50)
ap.add_argument("--out-dir", default=None, help="where outputs go (default: a temp dir)")
a = ap.parse_args()

units = sorted(u for u in os.listdir(a.units) if os.path.isdir(os.path.join(a.units, u)))
times = {b: {} for b in a.bins}
n = {}
for _ in range(a.reps):
    for u in units:
        for b in a.bins:
            out = tempfile.mkdtemp(dir=a.out_dir)
            d = os.path.join(a.units, u)
            if os.path.isdir(os.path.join(d, "scenarios")):
                cmd = [f"{b}/simulate-batch", "--batch-dir", f"{d}/scenarios", "--out-dir", out]
            else:
                cmd = [f"{b}/simulate", "--config", f"{d}/scenario.json", "--out", f"{out}/trace.parquet"]
            t0 = time.perf_counter()
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            dt = time.perf_counter() - t0
            n[u] = sum(json.load(open(os.path.join(r, "events.json")))["n_events"]
                       for r, _, fs in os.walk(out) if "events.json" in fs)
            shutil.rmtree(out)
            times[b].setdefault(u, []).append(dt)

w = {b: {u: min(v) for u, v in t.items()} for b, t in times.items()}


def score(wb, F):
    return sum(n[u] / (F + wb[u]) for u in units) / len(units)


ceiling = sum(n[u] / a.F for u in units) / len(units)
print(f"zero-work ceiling at F={a.F:.2f}: {ceiling:,.0f}")
for b in a.bins:
    wn = sum(n[u] * w[b][u] for u in units) / sum(n.values())
    preds = "  ".join(f"F={F:.2f}: {score(w[b], F):,.0f}" for F in (a.F - 0.05, a.F, a.F + 0.05))
    print(f"{b}\n  event-weighted work {1000 * wn:.1f} ms   {preds}")
b = a.bins[-1]
loss = sorted(((n[u] / a.F - n[u] / (a.F + w[b][u])) / len(units), u) for u in units)[::-1]
print(f"largest losses to work ({b}, F={a.F:.2f}):")
for value, u in loss[:10]:
    print(f"  {u:42s} n={n[u]:>8}  w={1000 * w[b][u]:6.1f} ms  -{value:,.0f}")

"""Run `python -m abides_fork.simulate_batch` on every public t3-gbatch-* unit and compare each
sub-scenario's trace/message hashes with the unit's batch.json references.
usage: batchcheck.py UNITS_DIR"""
import json, os, pathlib, subprocess, sys, tempfile, time
units = sorted(p for p in pathlib.Path(sys.argv[1]).iterdir() if (p / "batch.json").exists())
bad = 0
for u in units:
    ref = json.loads((u / "batch.json").read_text())
    out = pathlib.Path(tempfile.mkdtemp(prefix="bc-", dir=os.environ.get("HC_TMP", "/tmp")))
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-W", "ignore", "-m", "abides_fork.simulate_batch", "--batch-dir", str(u / "scenarios"),
                        "--out-dir", str(out)], capture_output=True, text=True)
    wall = time.perf_counter() - t0
    if p.returncode:
        print(u.name, "ERROR", p.stderr[-500:]); bad += 1; continue
    agg = json.loads((out / "batch_events.json").read_text())
    for s in ref["subs"]:
        ev = json.loads((out / s["sub"] / "events.json").read_text())
        ok = ev["trace_sha256"] == s["reference_trace_sha256"] and ev["message_trace_sha256"] == s["reference_message_sha256"]
        if not ok:
            bad += 1; print(u.name, s["sub"], "MISMATCH")
    print(f"{u.name}: subs={len(ref['subs'])} events={agg['total_events']} process_wall={wall:.2f}s keys={sorted(agg)}")
    subprocess.run(["rm", "-rf", str(out)])
print("BAD", bad); sys.exit(1 if bad else 0)

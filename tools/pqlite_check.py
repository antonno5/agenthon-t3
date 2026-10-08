"""Decoded-content equivalence of two t3-native binaries' outputs on all single-scenario units.
A = reference build (Arrow writer), B = candidate (pqlite). Compares pyarrow tables (schema
incl. metadata + values) and pandas.read_parquet frames (dtypes + values), and checks that
events.json hashes equal the files' real SHA-256.
usage: pqlite_check.py BIN_A BIN_B UNITS_DIR"""
import hashlib, json, pathlib, subprocess, sys, tempfile
import pandas as pd, pyarrow.parquet as pq
A, B, units = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
bad = 0; n = 0
for u in sorted(units.iterdir()):
    if not (u / "scenario.json").exists(): continue
    outs = []
    for b in (A, B):
        d = pathlib.Path(tempfile.mkdtemp(prefix="pq-", dir="/tmp/claude-1001"))
        subprocess.run([b, "--config", str(u / "scenario.json"), "--out", str(d / "trace.parquet"), "--engine", "native"], stdout=subprocess.DEVNULL, check=True)
        outs.append(d)
    ok = True
    ev = json.loads((outs[1] / "events.json").read_text())
    for f, key in (("trace.parquet", "trace_sha256"), ("message_trace.parquet", "message_trace_sha256")):
        x, y = pq.read_table(outs[0] / f), pq.read_table(outs[1] / f)
        if x.schema != y.schema or x.schema.metadata != y.schema.metadata or not x.equals(y): ok = False; print("ARROW DIFF", u.name, f)
        px, py = pd.read_parquet(outs[0] / f), pd.read_parquet(outs[1] / f)
        if not (px.dtypes.equals(py.dtypes) and px.equals(py)): ok = False; print("PANDAS DIFF", u.name, f)
        if ev[key] != hashlib.sha256((outs[1] / f).read_bytes()).hexdigest(): ok = False; print("HASH DIFF", u.name, f)
    for d in outs: subprocess.run(["rm", "-rf", str(d)])
    n += 1; bad += not ok
print(f"units {n}  equivalent {n - bad}  different {bad}"); sys.exit(1 if bad else 0)

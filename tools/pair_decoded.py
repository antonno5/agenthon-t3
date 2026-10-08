"""Run two images on all 71 public units (platform-like flags) and compare every output parquet
DECODED (pyarrow schema incl. metadata + values; pandas dtypes + values). For changes that alter
physical encoding but must not alter content. usage: pair_decoded.py IMAGE_A IMAGE_B UNITS_DIR"""
import os, pathlib, subprocess, sys, tempfile
import pandas as pd, pyarrow.parquet as pq
a, b, units = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
flags = ["--rm", "--network", "none", "--read-only", "--user", f"{os.getuid()}:{os.getgid()}",
         "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m", "--cpus", "4"]
def run(img, u):
    out = pathlib.Path(tempfile.mkdtemp(prefix="pd-", dir="/tmp/claude-1001"))
    if (u / "batch.json").exists():
        cmd = ["-v", f"{u}/scenarios:/input/scenarios:ro", "-v", f"{out}:/output", img, "simulate-batch", "--batch-dir", "/input/scenarios", "--out-dir", "/output"]
    else:
        cmd = ["-v", f"{u}:/input:ro", "-v", f"{out}:/output", img, "simulate", "--config", "/input/scenario.json", "--out", "/output/trace.parquet"]
    p = subprocess.run(["docker", "run", *flags, *cmd], capture_output=True, text=True)
    return p.returncode, out
same = diff = 0
for u in sorted(units.iterdir()):
    if not ((u / "batch.json").exists() or (u / "scenario.json").exists()): continue
    ra, oa = run(a, u); rb, ob = run(b, u)
    fa = sorted(str(f.relative_to(oa)) for f in oa.rglob("*.parquet")); fb = sorted(str(f.relative_to(ob)) for f in ob.rglob("*.parquet"))
    ok = ra == rb == 0 and fa == fb and fa
    for f in (fa if ok else []):
        x, y = pq.read_table(oa / f), pq.read_table(ob / f)
        if x.schema != y.schema or x.schema.metadata != y.schema.metadata or not x.equals(y): ok = False; print("ARROW DIFF", u.name, f); break
        px, py = pd.read_parquet(oa / f), pd.read_parquet(ob / f)
        if not (px.dtypes.equals(py.dtypes) and px.equals(py)): ok = False; print("PANDAS DIFF", u.name, f); break
    subprocess.run(["rm", "-rf", str(oa), str(ob)])
    if ok: same += 1
    else: diff += 1; print("DIFF", u.name, ra, rb)
print(f"equivalent units: {same}  differing: {diff}"); sys.exit(1 if diff else 0)

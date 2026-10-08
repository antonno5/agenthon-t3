"""Run two images on all 71 public units (platform-like flags) and compare every output parquet
byte for byte (sha256). Use when a change must not alter outputs relative to a validated image.
usage: pair_bytes.py IMAGE_A IMAGE_B UNITS_DIR"""
import hashlib, os, pathlib, subprocess, sys, tempfile
a, b, units = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
flags = ["--rm", "--network", "none", "--read-only", "--user", f"{os.getuid()}:{os.getgid()}",
         "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m", "--cpus", "4"]
def run(img, u):
    out = pathlib.Path(tempfile.mkdtemp(prefix="pb-", dir="/tmp/claude-1001"))
    if (u / "batch.json").exists():
        cmd = ["-v", f"{u}/scenarios:/input/scenarios:ro", "-v", f"{out}:/output", img, "simulate-batch", "--batch-dir", "/input/scenarios", "--out-dir", "/output"]
    else:
        cmd = ["-v", f"{u}:/input:ro", "-v", f"{out}:/output", img, "simulate", "--config", "/input/scenario.json", "--out", "/output/trace.parquet"]
    p = subprocess.run(["docker", "run", *flags, *cmd], capture_output=True, text=True)
    h = {str(f.relative_to(out)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.rglob("*.parquet"))}
    subprocess.run(["rm", "-rf", str(out)])
    return p.returncode, h
same = diff = 0
for u in sorted(units.iterdir()):
    if not ((u / "batch.json").exists() or (u / "scenario.json").exists()): continue
    ra, ha = run(a, u); rb, hb = run(b, u)
    if ra == rb == 0 and ha == hb and ha: same += 1
    else: diff += 1; print("DIFF", u.name, ra, rb, len(ha), len(hb))
print(f"identical units: {same}  differing: {diff}"); sys.exit(1 if diff else 0)

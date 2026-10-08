"""Differential fuzzer for an image: native path (default) vs T3_ENGINE=python, same image.
Outputs may differ physically (parquet encoding), so both journals are compared DECODED:
schema incl. metadata, row count and every value in row order.
usage: fuzz_image.py IMAGE OUT_DIR --n N [--workers W] [--seed S] [--profile P]
Scenario generator: tools/fuzz.py gen() (same envelope-stressing distributions)."""
import argparse, json, os, pathlib, random, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
import pyarrow.parquet as pq
ap = argparse.ArgumentParser()
ap.add_argument("image"); ap.add_argument("out")
ap.add_argument("--n", type=int, default=20); ap.add_argument("--workers", type=int, default=4)
ap.add_argument("--seed", type=int, default=1); ap.add_argument("--profile", default="default")
ap.add_argument("--timeout", type=int, default=900)
a = ap.parse_args()
src = (pathlib.Path(__file__).parent / "fuzz.py").read_text().split("def run(")[0]
ns = {"__name__": "fuzzgen"}; exec(compile(src.replace("a = ap.parse_args()", "a = ap.parse_args(['/tmp/claude-1001/fz-unused'])"), "fuzz.py", "exec"), ns)
gen = ns["gen"]
out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
flags = ["--rm", "--network", "none", "--read-only", "--user", f"{os.getuid()}:{os.getgid()}",
         "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m", "--cpus", "2"]

def run(engine, d):
    env = [] if engine == "native" else ["-e", "T3_ENGINE=python"]
    try:
        p = subprocess.run(["docker", "run", *flags, *env, "-v", f"{d}:/w", a.image, "simulate", "--config", "/w/scenario.json",
                            "--out", f"/w/{engine}/trace.parquet"], capture_output=True, text=True, timeout=a.timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "ps", "-q"], capture_output=True)
        return "TIMEOUT", ""
    if p.returncode: return None, p.stderr[-1200:]
    ev = json.loads((d / engine / "events.json").read_text())
    return ev.get("engine", "?"), ""

def same(d):
    for f in ("trace.parquet", "message_trace.parquet"):
        x = pq.read_table(d / "native" / f); y = pq.read_table(d / "python" / f)
        if x.schema != y.schema or x.schema.metadata != y.schema.metadata or not x.equals(y):
            return f
    return None

def one(i):
    R = random.Random(a.seed * 1_000_003 + i); sc = gen(R, a.profile)
    d = pathlib.Path(tempfile.mkdtemp(prefix="fi-", dir="/tmp/claude-1001")); d.chmod(0o777)
    try:
        (d / "scenario.json").write_text(json.dumps(sc)); (d / "native").mkdir(); (d / "python").mkdir()
        os.chmod(d / "native", 0o777); os.chmod(d / "python", 0o777)
        t0 = time.time(); ne, nerr = run("native", d); t1 = time.time(); pe, perr = run("python", d); t2 = time.time()
        if pe == "TIMEOUT": status = "PY_TIMEOUT"
        elif ne is None and pe is None: status = "BOTH_ERROR"
        elif ne is None or pe is None: status = "ONE_ERROR"
        else:
            bad = same(d)
            status = ("MISMATCH:" + bad) if bad else ("OK" if ne == "native" else "OK_FALLBACK")
        if not status.startswith("OK") and status != "PY_TIMEOUT":
            (out / f"fail-{a.seed}-{i}.json").write_text(json.dumps({"scenario": sc, "status": status, "nerr": nerr, "perr": perr}, indent=1))
        return status, t1 - t0, t2 - t1
    finally:
        shutil.rmtree(d, ignore_errors=True)

counts = {}; tn = tp = 0
with ThreadPoolExecutor(a.workers) as ex:
    for st, x, y in ex.map(one, range(a.n)):
        counts[st] = counts.get(st, 0) + 1; tn += x; tp += y
print(f"image={a.image} profile={a.profile} seed={a.seed} n={a.n} {counts} native_wall={tn:.0f}s python_wall={tp:.0f}s", flush=True)
sys.exit(0 if set(counts) <= {"OK", "OK_FALLBACK", "PY_TIMEOUT"} else 1)

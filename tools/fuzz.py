"""Differential fuzzer: native engine vs the Python ABIDES path on random scenarios.

usage: fuzz.py OUT_DIR --n N [--workers W] [--seed S] [--profile default|edge|big]
Each scenario is run twice through `python -m abides_fork.simulate` (T3_ENGINE=python and the
default native path) and both output hashes are compared. Mismatching scenarios are kept in
OUT_DIR/fail-*.json for replay; a summary line per batch is printed.
"""
import argparse, hashlib, json, os, pathlib, random, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--n", type=int, default=50)
ap.add_argument("--workers", type=int, default=6)
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--profile", default="default")
ap.add_argument("--py", default=sys.executable)
a = ap.parse_args()
out = pathlib.Path(a.out)
out.mkdir(parents=True, exist_ok=True)


def gen(R: random.Random, profile: str) -> dict:
    big = profile == "big"
    edge = profile == "edge"
    hz = lambda: R.choice([0.2, 1, 2, 5, 10, 20, 50]) * R.uniform(0.5, 1.5)
    agents = []
    if R.random() < 0.95:
        agents.append({"agent_type": "NoiseTrader", "count": R.randint(1, 120 if big else 40),
                       "params": {"arrival_rate_hz": hz(), "order_size_mean": R.choice([1, 5, 10, 50, 200]) * R.uniform(0.5, 2),
                                  "order_size_std": R.choice([0, 0.5, 2, 10, 60]), "price_offset_ticks": R.choice([0, 1, 3, 5, 10, 30])}})
    if R.random() < 0.8:
        agents.append({"agent_type": "MarketMaker", "count": R.randint(1, 6),
                       "params": {"rebalance_interval_ns": R.choice([10**5, 10**6, 10**7, 10**8, 5 * 10**8, 2 * 10**9]) + R.randint(0, 1000),
                                  "spread_ticks": R.choice([1, 2, 3, 4, 7, 20]), "depth_levels": R.choice([1, 2, 3, 5, 10, 25]),
                                  "size_per_level": R.choice([1, 5, 10, 50, 300])}})
    if R.random() < 0.7:
        p = {"arrival_rate_hz": hz(), "order_size_mean": R.choice([1, 10, 25, 100, 2.5, 3.5]), "threshold_ticks": R.choice([0, 1, 2, 5, 10])}
        if R.random() < 0.5:
            p["fundamental_value_source"] = "oracle"
        agents.append({"agent_type": "ValueTrader", "count": R.randint(1, 60 if big else 25), "params": p})
    if R.random() < 0.6:
        agents.append({"agent_type": "MomentumTrader", "count": R.randint(1, 60 if big else 25),
                       "params": {"arrival_rate_hz": hz(), "order_size_mean": R.choice([1, 15, 40, 0.5]), "threshold_ticks": R.choice([0, 1, 2, 5]),
                                  "lookback": R.choice([1, 2, 5, 10, 30])}})
    R.shuffle(agents)
    lat_kind = R.choice(["log_normal", "log_normal", "uniform", "pareto", "deterministic"])
    if lat_kind == "log_normal":
        mean = R.choice([5, 100, 1000, 5e4, 1e6, 2e7])
        lat = {"mean_ns": mean, "sigma": R.choice([0.0, 0.1, 0.5, 1.0, 2.5]), "min_ns": R.choice([0, 1, 50, mean / 10]), "max_ns": R.choice([mean * 3, mean * 100, 1e12])}
    elif lat_kind == "uniform":
        lo = R.choice([0, 1, 10, 1000, 1e5])
        lat = {"min_ns": lo, "max_ns": lo + R.choice([0, 5, 100, 1e4, 1e7]), "mean_ns": lo}
    elif lat_kind == "pareto":
        lat = {"min_ns": R.choice([0, 1, 100, 1e4]), "alpha": R.choice([0.6, 1.1, 1.5, 3.0]), "max_ns": R.choice([1e5, 1e8, 1e12])}
    else:
        lat = {"mean_ns": R.choice([0, 1, 10, 40, 50, 51, 1000, 1e5])}  # constant -> dense ties
    proto = R.random() < 0.4
    ex = {"symbol": "ABM", "tick_size": 1, "lot_size": 1, "min_price": 1, "max_price": 1000000,
          "order_types_allowed": ["LIMIT", "MARKET", "CANCEL", "REPLACE"],
          "stp_policy": R.choice(["cancel_newest", "cancel_oldest", "cancel_both", ""])}
    if proto:
        ex["protocol_enforcement"] = True
        ex["ack_delay_ns"] = R.choice([0, 0, 1, 100, 40000, 10**6])
        ex["compute_delay_ns"] = R.choice([0, 0, 1, 50, 1000])
    price = R.choice([100_000, 100_000, 5_000, 1_000_000, 50]) if not edge else R.choice([3, 10, 50, 200])
    op = {"initial_price": price, "kappa": R.choice([0.0, 1e-6, 1e-3, 0.05, 1.0, 20.0]), "sigma": R.choice([0.0, 1e-6, 5e-5, 1e-3, 0.05]),
          "jump_intensity": R.choice([0.0, 0.0, 0.1, 2.0, 20.0, 200.0]), "jump_sigma": R.choice([0.0, 10.0, 500.0, 5000.0]),
          "dt_ns": 1000000, "noise_type": "gaussian"}
    horizon = int(R.choice([0.2, 1, 3, 10, 30]) * 1e9 * (3 if big else 1))
    if R.random() < 0.25:
        op["scheduled_jump"] = {"time_ns": R.choice([0, 1, horizon // 3, horizon // 2, horizon - 1, horizon + 5 * 10**9]),
                                "magnitude": R.choice([-5000, -200, 0, 300, 10000])}
    # Bound the Python reference's run time: total scheduled wakeups across all agents.
    def wakeups(ag):
        pr = ag["params"]
        iv = pr["rebalance_interval_ns"] if "rebalance_interval_ns" in pr else 1e9 / pr["arrival_rate_hz"]
        mult = 2 * pr.get("depth_levels", 0) + 1 if ag["agent_type"] == "MarketMaker" else 1
        return ag["count"] * horizon / iv * mult
    while sum(map(wakeups, agents)) > (400_000 if big else 150_000) and horizon > 10**8:
        horizon //= 2
    return {"scenario_id": f"fuzz-{R.randrange(10**12)}", "seed": R.randrange(2**32), "horizon_ns": horizon,
            "schema_version": "1.0", "scenario_family": "fuzz", "description": "fuzz",
            "exchange_config": ex, "oracle_config": {"model": "ou", "params": op},
            "latency_config": {"model": lat_kind, "params": lat}, "agent_configs": agents,
            "output_config": {}, "tolerance": {}}


def run(path: pathlib.Path, engine: str, d: pathlib.Path):
    env = dict(os.environ, T3_ENGINE=engine, T3_DEBUG="1")
    try:
        p = subprocess.run([a.py, "-W", "ignore", "-m", "abides_fork.simulate", "--config", str(path), "--out", str(d / "trace.parquet")],
                           capture_output=True, text=True, env=env, cwd=d, timeout=900)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", ""
    if p.returncode != 0:
        return None, p.stderr[-1500:]
    ev = json.loads((d / "events.json").read_text())
    return (ev["trace_sha256"], ev["message_trace_sha256"], ev["n_events"]), p.stderr


def one(i: int):
    R = random.Random(a.seed * 1_000_003 + i)
    sc = gen(R, a.profile)
    d = pathlib.Path(tempfile.mkdtemp(prefix="fz-", dir=os.environ.get("HC_TMP", "/tmp")))
    try:
        sp = d / "scenario.json"
        sp.write_text(json.dumps(sc))
        (d / "py").mkdir(); (d / "nat").mkdir()
        t0 = time.time(); py, perr = run(sp, "python", d / "py"); t1 = time.time()
        nat, nerr = run(sp, "native", d / "nat"); t2 = time.time()
        used_native = "engine=native" in (nerr or "")
        if py == "TIMEOUT":
            status = "PY_TIMEOUT"
        elif py is None and nat is None:
            status = "BOTH_ERROR"
        elif py != nat:
            status = "MISMATCH"
        else:
            status = "OK" if used_native else "OK_FALLBACK"
        if status not in ("OK", "OK_FALLBACK", "PY_TIMEOUT"):
            (out / f"fail-{a.seed}-{i}.json").write_text(json.dumps({"scenario": sc, "py": py, "nat": nat, "perr": perr, "nerr": nerr}, indent=1))
        return status, (py if isinstance(py, tuple) else [0, 0, 0])[2], t1 - t0, t2 - t1
    finally:
        shutil.rmtree(d, ignore_errors=True)


counts = {}
ev_total = 0; tpy = 0; tnat = 0
with ThreadPoolExecutor(a.workers) as ex:
    for status, n_ev, a1, a2 in ex.map(one, range(a.n)):
        counts[status] = counts.get(status, 0) + 1
        ev_total += n_ev; tpy += a1; tnat += a2
print(f"profile={a.profile} seed={a.seed} n={a.n} {counts} events={ev_total} py_wall={tpy:.0f}s native_wall={tnat:.0f}s", flush=True)
sys.exit(0 if set(counts) <= {"OK", "OK_FALLBACK", "PY_TIMEOUT"} else 1)

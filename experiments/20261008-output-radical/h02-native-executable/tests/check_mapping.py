"""Executive summary: compare every mapped parameter with the existing adapter.

Selected public configs and synthetic boundary cases only; no simulation/scoring runs.
The ARM host uses a matching injected libm dispatch on both sides.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import types

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / "baselines"))
sys.modules["abides_fork._t3engine"] = types.SimpleNamespace(numpy_log=math.log)
from abides_fork import native

artifact = Path(__file__).resolve().parents[1]
policy = json.loads((artifact / "policy.json").read_text())
corpus = Path("/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/units")
mapper = Path(sys.argv[1]).resolve()
checks = []

def exact(a, b, path=""):
    if isinstance(a, float):
        assert isinstance(b, float) and a.hex() == b.hex(), (path, a, b)
    elif isinstance(a, dict):
        assert set(a) == set(b), path
        for k in a: exact(a[k], b[k], path + "/" + k)
    elif isinstance(a, (tuple, list)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)): exact(x, y, path + f"/{i}")
    else:
        assert type(a) is type(b) and a == b, (path, a, b)

with tempfile.TemporaryDirectory() as tmp:
    fixture = Path(tmp) / "config.json"
    def check(name, s, supported=True, seed=None):
        fixture.write_text(json.dumps(s))
        expected_s = s if seed is None else {**s, "seed": seed}
        expected = native._build(expected_s)
        proc = subprocess.run([str(mapper), str(fixture), *([] if seed is None else [str(seed)])], capture_output=True, text=True)
        if supported:
            assert proc.returncode == 0, (name, proc.stderr)
            assert expected is not None, name
            exact(expected, json.loads(proc.stdout))
        else:
            assert proc.returncode != 0 and expected is None, (name, expected, proc.stdout)
        checks.append({"name": name, "supported": supported, "pass": True})

    public = []
    for unit in policy["experiment"]["units"] + policy["experiment"]["correctness_only_units"]:
        folder = corpus / unit
        paths = [folder / "scenario.json"] if (folder / "scenario.json").is_file() else sorted((folder / "scenarios").glob("*.json"))
        for path in paths:
            s = json.loads(path.read_text()); check(str(path.relative_to(corpus)), s)
            public.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    base = json.loads((corpus / "t3-s001-price-time-priority/scenario.json").read_text())
    check("seed-override", base, seed=4294967295)
    for kind in ("NoiseTrader", "MarketMaker", "ValueTrader", "MomentumTrader"):
        for params in ({}, {"arrival_rate_hz": 0}, {"arrival_rate_hz": 3}, {"rebalance_interval_ns": -1}, {"rebalance_interval_ns": 1.9}):
            s = copy.deepcopy(base); s["agent_configs"] = [{"agent_type": kind, "count": 1, "params": params}]
            check(f"agent-defaults/{kind}/{params}", s)
    for size in (-3.5, 0.5, 1.5, 2.5, 3.5, 999999999999.5):
        for kind in ("ValueTrader", "MomentumTrader"):
            s = copy.deepcopy(base); s["agent_configs"] = [{"agent_type": kind, "count": 1, "params": {"order_size_mean": size}}]
            check(f"ties-to-even/{kind}/{size}", s)
    for stp in (None, "", "cancel_oldest", "cancel_newest", "other"):
        s = copy.deepcopy(base); s["exchange_config"].update(protocol_enforcement=True, stp_policy=stp, ack_delay_ns=100, compute_delay_ns=25)
        check(f"stp/{stp}", s)
    for proto in (False, "", [], {}, 0, True):
        s = copy.deepcopy(base); s["exchange_config"].update(protocol_enforcement=proto, ack_delay_ns=-1)
        check(f"python-truth/{proto!r}", s, supported=not bool(proto))
    for model in ("uniform", "pareto", "log_normal", "unknown"):
        s = copy.deepcopy(base); s["latency_config"] = {"model": model, "params": {"mean_ns": 12345.5, "sigma": 0.2, "alpha": 1.25, "min_ns": -1, "max_ns": 20}}
        check(f"latency/{model}", s)
    for key, value in (("seed", -1), ("seed", True), ("seed", 4294967296), ("horizon_ns", 0), ("horizon_ns", 1000000000000001), ("latency_config", {})):
        s = copy.deepcopy(base); s[key] = value; check(f"rejected/{key}/{value}", s, False)
    s = copy.deepcopy(base); s["oracle_config"]["params"] = {"initial_price": 0, "scheduled_jump": {"time_ns": -100, "magnitude": -(1 << 40)}, "jump_sigma": -0.0}
    check("scheduled-jump-negative", s)
    s = copy.deepcopy(base); s["agent_configs"] = [{"agent_type": "MarketMaker", "count": -2, "params": {"spread_ticks": -2.1, "depth_levels": 1.9, "size_per_level": 0}}]
    check("fractional-clamps-negative-count", s)
    for target, key, value in (("scenario", "horizon_ns", "1000000000"),
                               ("oracle", "initial_price", "100000"),
                               ("exchange", "stp_policy", True)):
        s = copy.deepcopy(base)
        if target == "scenario": s[key] = value
        elif target == "oracle": s["oracle_config"].setdefault("params", {})[key] = value
        else: s["exchange_config"].update(protocol_enforcement=True, stp_policy=True)
        fixture.write_text(json.dumps(s))
        assert native._build(s) is not None
        proc = subprocess.run([str(mapper), str(fixture)], capture_output=True, text=True)
        assert proc.returncode != 0
        checks.append({"name": f"conservative-fallback/{target}/{key}", "supported": False,
                       "python_accepts": True, "pass": True})

result = {"pass": True, "checks": checks, "count": len(checks), "public_configs": public,
          "host_log_dispatch": "injected matching libm; production x86 dispatch deferred to Docker"}
(artifact / "evidence/mapping-checks.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"pass": True, "count": len(checks)}))

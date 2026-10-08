"""Lean entry point for the ``simulate`` / ``simulate-batch`` verbs.

The image runs ``python3 -S`` (no ``site``: site-packages is not even on sys.path) and this
module imports only ``sys``, ``os``, ``json``, ``time`` and the native engine. Container wall
time is the ranked quantity and a run is otherwise ~10-50 ms of work, so interpreter start-up
and imports (argparse, typing, pathlib, hashlib + libcrypto, site's .pth scan, ...) are a
real share of every unit, especially with a cold page cache.

It handles exactly the documented invocations:

    simulate [simulate] --config PATH --out PATH [--seed N]
    simulate-batch [simulate-batch] --batch-dir DIR --out-dir DIR

and produces outputs identical to ``abides_fork.simulate`` / ``abides_fork.simulate_batch``
(same files, same events.json / batch_events.json keys and formatting). Anything else -- an
unexpected argument, a scenario outside the native envelope, an engine refusal, any error --
enables ``site`` and hands the original argv to those full modules, which run the Python ABIDES
path (and argparse's own usage/errors) exactly as before.
"""

import json
import os
import sys
import time


def _parse(argv, verb, required, optional=()):
    """Strict parser for --key VALUE / --key=VALUE; None if anything is unexpected."""
    args = list(argv)
    if args and args[0] == verb:
        args = args[1:]
    known = set(required) | set(optional)
    out = {}
    i = 0
    while i < len(args):
        a = args[i]
        if not a.startswith("--"):
            return None
        if "=" in a:
            key, value = a[2:].split("=", 1)
            i += 1
        else:
            if i + 1 >= len(args):
                return None
            key, value = a[2:], args[i + 1]
            i += 2
        if key not in known or key in out:
            return None
        out[key] = value
    if any(k not in out for k in required):
        return None
    return out


def _simulate_native(config_path, out_path, seed=None):
    """One scenario on the native path; returns the events dict or None (nothing to trust)."""
    from abides_fork import native

    if native._t3engine is None or not os.path.isfile(config_path):
        return None
    with open(config_path) as fh:
        scenario = json.loads(fh.read())
    if seed is not None:
        scenario = {**scenario, "seed": int(seed)}
    cfg = native.build_native_config(scenario)
    if cfg is None:
        return None
    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    msg_path = os.path.join(out_dir, "message_trace.parquet")
    try:
        ran = native._t3engine.run_write(cfg, out_path, msg_path)
    except RuntimeError:
        return None
    if ran is None:
        return None
    n_events, n_messages, wall_clock_sec = ran
    if os.environ.get("T3_DEBUG"):
        print("engine=native", file=sys.stderr)
    import resource

    sha = native._t3engine.sha256_file
    # Same keys, order and formatting as abides_fork.simulate.simulate.
    events = {
        "scenario_id": str(scenario["scenario_id"]),
        "seed": int(scenario["seed"]),
        "n_events": n_events,
        "wall_clock_sec": float(wall_clock_sec),
        "events_per_sec": float(n_events / wall_clock_sec) if wall_clock_sec > 0 else 0.0,
        "trace_sha256": sha(out_path),
        "n_messages": n_messages,
        "message_trace_sha256": sha(msg_path),
        "peak_memory_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
        "gpu_seconds": 0.0,
    }
    with open(os.path.join(out_dir, "events.json"), "w") as fh:
        fh.write(json.dumps(events, indent=2) + "\n")
    return events


def _full(module, argv):
    """Hand over to the full CLI module (enables site-packages first)."""
    import site

    site.main()
    if module == "simulate":
        from abides_fork.simulate import main
    else:
        from abides_fork.simulate_batch import main
    return main(argv)


def _finish(code):
    # Outputs are written and closed; skip interpreter teardown (container wall time).
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def simulate_main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if os.environ.get("T3_ENGINE", "native") != "python":
        a = _parse(argv, "simulate", ("config", "out"), ("seed",))
        if a is not None:
            try:
                seed = int(a["seed"]) if "seed" in a else None
                events = _simulate_native(a["config"], a["out"], seed)
            except Exception:
                events = None
            if events is not None:
                print(json.dumps(events))
                _finish(0)
    _finish(_full("simulate", argv))


def simulate_batch_main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if os.environ.get("T3_ENGINE", "native") != "python":
        a = _parse(argv, "simulate-batch", ("batch-dir", "out-dir"))
        if a is not None:
            batch = _batch_native(a["batch-dir"], a["out-dir"])
            if batch is not None:
                print(json.dumps(batch))
                _finish(0)
    _finish(_full("simulate_batch", argv))


def _batch_native(batch_dir, out_dir):
    """abides_fork.simulate_batch.simulate_batch on the native path, or None to hand over.

    Sub-scenarios already written by a partial native attempt are simply rewritten by the full
    path, which recomputes everything from scratch.
    """
    try:
        # pathlib's glob("*.json") on one directory == names ending in ".json", sorted.
        names = sorted(n for n in os.listdir(batch_dir) if n.endswith(".json"))
    except OSError:
        return None
    if not names:
        return None  # the full path raises its own SystemExit message
    per_scenario = []
    total_events = 0
    peak_memory_bytes = 0
    gpu_seconds = 0.0
    t0 = time.perf_counter()
    for name in names:
        sub = name[: -len(".json")]
        try:
            ev = _simulate_native(
                os.path.join(batch_dir, name), os.path.join(out_dir, sub, "trace.parquet")
            )
        except Exception:
            ev = None
        if ev is None:
            return None
        total_events += int(ev["n_events"])
        peak_memory_bytes = max(peak_memory_bytes, int(ev.get("peak_memory_bytes", 0)))
        gpu_seconds += float(ev.get("gpu_seconds", 0.0))
        per_scenario.append(
            {"sub": sub, "n_events": int(ev["n_events"]), "trace_sha256": ev["trace_sha256"]}
        )
    wall_clock_sec = time.perf_counter() - t0
    # Same keys, order and formatting as abides_fork.simulate_batch.simulate_batch.
    batch_events = {
        "n_scenarios": len(names),
        "total_events": total_events,
        "wall_clock_sec": float(wall_clock_sec),
        "events_per_sec": float(total_events / wall_clock_sec) if wall_clock_sec > 0 else 0.0,
        "peak_memory_bytes": peak_memory_bytes,
        "gpu_seconds": gpu_seconds,
        "per_scenario": per_scenario,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "batch_events.json"), "w") as fh:
        fh.write(json.dumps(batch_events, indent=2) + "\n")
    return batch_events

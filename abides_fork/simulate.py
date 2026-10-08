"""Experimental native CLI with the existing optimized Python engine as fallback.

Executive summary: run the indexed native simulator, keep canonical journals and
measure the complete adapter. Native-only measurements fail rather than fallback.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

from abides_fork import native
from abides_fork.scenario_io import read_scenario


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def simulate(
    config_path,
    out_path,
    seed=None,
    *,
    trace_mode="buffered",
    profile_components=False,
    engine=None,
):
    if trace_mode not in {"buffered", "legacy", "verify"}:
        raise ValueError(f"unknown trace mode: {trace_mode}")
    engine = engine or os.environ.get("T3_ENGINE", "auto")
    strict = engine == "native" or os.environ.get("T3_REQUIRE_NATIVE") == "1"
    if engine == "python" or trace_mode != "buffered" or profile_components:
        from abides_fork.python_simulate import simulate as python_simulate

        ev = python_simulate(
            config_path,
            out_path,
            seed,
            trace_mode=trace_mode,
            profile_components=profile_components,
        )
        ev["engine"] = "python"
        Path(out_path).with_name("events.json").write_text(
            json.dumps(ev, indent=2) + "\n"
        )
        return ev
    started = time.perf_counter()
    scenario = json.loads(read_scenario(config_path))
    if seed is not None:
        scenario = {**scenario, "seed": int(seed)}
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    msg = out.with_name("message_trace.parquet")
    cfg = native.build_native_config(scenario)
    configured = time.perf_counter()
    ran = None
    if cfg is not None:
        try:
            ran = native.run_and_write(cfg, out, msg)
        except RuntimeError:
            if strict:
                raise
    if ran is None:
        if strict:
            raise RuntimeError(
                "scenario requires Python fallback; native-only run rejected"
            )
        return simulate(config_path, out_path, seed, engine="python")
    written = time.perf_counter()
    n_events, n_messages, core_seconds = ran
    ev = {
        "scenario_id": str(scenario["scenario_id"]),
        "seed": int(scenario["seed"]),
        "n_events": n_events,
        "n_messages": n_messages,
        "engine": "native",
        "trace_sha256": sha(out),
        "message_trace_sha256": sha(msg),
        "peak_memory_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        * 1024,
        "gpu_seconds": 0.0,
        "simulation_wall_clock_sec": core_seconds,
    }
    ev["wall_clock_sec"] = time.perf_counter() - started
    ev["events_per_sec"] = n_events / ev["wall_clock_sec"]
    out.with_name("events.json").write_text(json.dumps(ev, indent=2) + "\n")
    out.with_name("profile.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "engine": "native",
                "trace_mode": trace_mode,
                "detailed": False,
                "timing_kind": "wall_clock_phases",
                "wall_clock_sec": ev["wall_clock_sec"],
                "phases": {
                    "configuration": configured - started,
                    "simulation_and_trace_finalize": core_seconds,
                    "parquet_write": max(0.0, written - configured - core_seconds),
                    "hashing": ev["wall_clock_sec"] - (written - started),
                },
                "components": {},
                "simulation_components": {},
                "component_calls": {},
                "gpu_utilization": 0.0,
                "peak_memory_bytes": ev["peak_memory_bytes"],
            },
            indent=2,
        )
        + "\n"
    )
    ev["wall_clock_sec"] = time.perf_counter() - started
    ev["events_per_sec"] = n_events / ev["wall_clock_sec"]
    out.with_name("events.json").write_text(json.dumps(ev, indent=2) + "\n")
    return ev


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("verb", nargs="?", default="simulate", choices=["simulate"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int)
    ap.add_argument(
        "--trace-mode", default="buffered", choices=["buffered", "legacy", "verify"]
    )
    ap.add_argument("--profile-components", action="store_true")
    ap.add_argument("--engine", choices=["auto", "native", "python"])
    args = vars(ap.parse_args(argv))
    args.pop("verb")
    args["config_path"] = args.pop("config")
    args["out_path"] = args.pop("out")
    print(json.dumps(simulate(**args)))
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)  # All output files are closed before skipping interpreter cleanup.

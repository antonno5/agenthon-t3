#!/usr/bin/env python3
"""Executive summary: check the runner against four public reference outputs.

This copies public artifacts to a fresh local output tree. It validates the checker
only; it does not invoke or validate a simulator and produces no speed evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import run_differential_experiment as runner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units-dir", type=Path, default=runner.ROOT / "units")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    results = []
    for unit in runner.select_units(args.units_dir.resolve(), None, False):
        raw = args.out / unit.name / "raw"
        raw.mkdir(parents=True)
        if (unit / "batch.json").exists():
            entries = []
            for reference, sub in runner.trace_layout(unit):
                shutil.copytree(reference, raw / sub)
                events = json.loads((reference / "events.json").read_text())
                entries.append(
                    {
                        "sub": sub,
                        "n_events": events["n_events"],
                        "wall": events["wall_clock_sec"],
                    }
                )
            total, wall = (
                sum(e["n_events"] for e in entries),
                sum(e["wall"] for e in entries),
            )
            runner.dump(
                raw / "batch_events.json",
                {
                    "total_events": total,
                    "wall_clock_sec": wall,
                    "events_per_sec": total / wall,
                    "n_scenarios": len(entries),
                    "per_scenario": [
                        {"sub": e["sub"], "n_events": e["n_events"]} for e in entries
                    ],
                },
            )
        else:
            for name in (*runner.TRACE_FILES, "events.json"):
                shutil.copy2(unit / name, raw / name)
        code = runner.main(
            [
                "check",
                "--unit",
                str(unit),
                "--baseline-output",
                str(raw.resolve()),
                "--candidate-output",
                str(raw.resolve()),
                "--out",
                str((args.out / unit.name / "check").resolve()),
            ]
        )
        results.append(
            {
                "unit": unit.name,
                "exit_code": code,
                "basis": "reference_artifact_replay_only; no simulator invoked",
            }
        )
    runner.dump(args.out / "results.json", results)
    return int(any(r["exit_code"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())

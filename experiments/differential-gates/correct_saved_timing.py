#!/usr/bin/env python3
"""Executive summary: correct saved clocks without repeating a simulator run.

Docker State timestamps give container lifetime; the old container_sec recorded
the host Docker CLI elapsed instead. Preserve original reports and raw elapsed,
update only derived timing fields and leave gate/trace evidence unchanged.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import run_differential_experiment as runner  # noqa: E402


def correct(directory: Path) -> dict:
    summary_path = directory / "summary.json"
    summary = json.loads(summary_path.read_text())
    if summary.get("timing_correction"):
        raise ValueError(
            "timing correction already recorded; refusing a second correction"
        )
    backup = directory / "timing-correction-original"
    backup.mkdir(exist_ok=False)
    shutil.copy2(summary_path, backup / "summary.json")
    original_summary_sha = runner.sha(summary_path)
    original_runner_sha = summary["metadata"]["source_hashes"][
        "scripts/run_differential_experiment.py"
    ]
    original_checks = [r.get("check") for r in summary["runs"]]
    corrections = []
    for record in summary["runs"] + summary.get("original_baseline_failures", []):
        if record.get("container_clock") == "Docker State FinishedAt - StartedAt":
            raise ValueError("source run already uses State timing")
        relative = (
            Path("runs")
            / record["unit"]
            / f"{record['kind']}-{record['index']:02d}"
            / record["side"]
            / "record.json"
        )
        path = directory / relative
        if path.exists():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
        raw_cli = record["container_sec"]
        duration = runner.container_state_seconds(record["state"])
        note = {
            "old_container_sec_was_host_cli_elapsed": raw_cli,
            "source": "saved Docker State StartedAt/FinishedAt",
            "simulation_reexecuted": False,
        }
        record.update(
            host_launch_sec=raw_cli,
            raw_cli_elapsed_sec=raw_cli,
            host_launch_clock="original perf_counter around Docker CLI",
            container_sec=duration,
            container_clock="Docker State FinishedAt - StartedAt",
            timing_correction=note,
        )
        if "adapter_sec_self_reported" in record:
            record["cold_start_and_container_other_sec"] = max(
                0, duration - record["adapter_sec_self_reported"]
            )
        if path.exists():
            runner.dump(path, record)
        corrections.append(
            {
                "record": str(relative),
                "host_launch_sec": raw_cli,
                "container_sec": duration,
            }
        )
    summary["timing_summary"] = []
    for unit in dict.fromkeys(r["unit"] for r in summary["runs"]):
        clocks = {
            side: [
                r["container_sec"]
                for r in summary["runs"]
                if r["unit"] == unit
                and r["side"] == side
                and r["kind"] == "timing"
                and r["accepted"]
            ]
            for side in ("baseline", "candidate")
        }
        if all(clocks.values()):
            medians = {side: statistics.median(v) for side, v in clocks.items()}
            summary["timing_summary"].append(
                {
                    "unit": unit,
                    "median_container_sec": medians,
                    "local_speedup": medians["baseline"] / medians["candidate"]
                    if summary["accepted"]
                    else None,
                }
            )
    assert original_checks == [r.get("check") for r in summary["runs"]]
    note = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "original_summary_sha256": original_summary_sha,
        "original_runner_sha256": original_runner_sha,
        "original_metadata_preserved": True,
        "raw_cli_elapsed_preserved": True,
        "gate_trace_evidence_unchanged": True,
        "simulation_reexecuted": False,
        "original_backup": str(backup),
        "corrections": corrections,
        "correction_script_sha256": runner.sha(Path(__file__)),
    }
    summary["timing_correction"] = note
    runner.dump(summary_path, summary)
    note["corrected_summary_sha256"] = runner.sha(summary_path)
    runner.dump(directory / "timing-correction.json", note)
    return note


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    args = parser.parse_args()
    result = correct(args.source_run.resolve())
    print(
        json.dumps(
            {
                "source_run": str(args.source_run),
                "records_corrected": len(result["corrections"]),
                "simulation_reexecuted": False,
            }
        )
    )

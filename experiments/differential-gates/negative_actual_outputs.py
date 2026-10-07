#!/usr/bin/env python3
"""Executive summary: test rejection using copies of real, successful image outputs.

No container is launched. The source evidence, inputs and public references are
read-only; every change is made in a fresh output directory and checked by CLI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import run_differential_experiment as runner  # noqa: E402
from throughput.run_unit import retain_output  # noqa: E402

CASES = ("event", "roworder", "message", "causality", "sha")


def _replace_value(table, column: str, row: int, value):
    import pyarrow as pa

    index = table.schema.get_field_index(column)
    if index < 0:
        raise ValueError(f"missing required mutation column: {column}")
    field = table.schema.field(index)
    values = table.column(index).to_pylist()
    values[row] = value
    return table.set_column(index, field, pa.array(values, type=field.type))


def mutate(unit: Path, output: Path, case: str) -> dict:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    sub = runner.trace_layout(unit)[0][1]
    trace = output / sub / "trace.parquet"
    ledger = output / sub / "message_trace.parquet"
    target = trace if case in ("event", "roworder") else ledger
    detail = {"case": case, "sub": sub}
    if case != "sha":
        table = pq.read_table(target)
        if table.num_rows < 2:
            raise ValueError("negative control needs at least two output rows")
        if case == "event":
            types = table.column("msg_type").to_pylist()
            row = next(
                i
                for i, kind in enumerate(types)
                if kind in ("ORDER_FILLED", "PARTIAL_FILL")
            )
            table = _replace_value(
                table, "price", row, table.column("price")[row].as_py() + 1
            )
            detail.update(row=row, column="price")
        elif case == "roworder":
            # Swap distinct rows; reversing identical rows would be a vacuous control.
            row = next(
                i
                for i in range(1, table.num_rows)
                if not table.slice(0, 1).equals(table.slice(i, 1))
            )
            indices = list(range(table.num_rows))
            indices[0], indices[row] = indices[row], indices[0]
            table = pc.take(table, pa.array(indices, type=pa.int64()))
            detail.update(swapped_rows=[0, row])
        elif case == "message":
            table = _replace_value(table, "seq", 1, table.column("seq")[0].as_py())
            detail.update(row=1, column="seq")
        elif case == "causality":
            unused_parent = (
                max(x for x in table.column("message_id").to_pylist() if x is not None)
                + 1
            )
            table = _replace_value(table, "causal_parent", 1, unused_parent)
            detail.update(
                row=1, column="causal_parent", fabricated_parent=unused_parent
            )
        else:
            raise ValueError(f"unknown mutation: {case}")
        pq.write_table(table, target)
    events_path = output / sub / "events.json"
    events = json.loads(events_path.read_text())
    events["trace_sha256"] = "0" * 64 if case == "sha" else runner.sha(trace)
    if "message_trace_sha256" in events:
        events["message_trace_sha256"] = runner.sha(ledger)
    runner.dump(events_path, events)
    batch_path = output / "batch_events.json"
    if batch_path.exists() and case != "sha":
        batch = json.loads(batch_path.read_text())
        for entry in batch["per_scenario"]:
            if entry["sub"] == sub and "trace_sha256" in entry:
                entry["trace_sha256"] = runner.sha(trace)
        runner.dump(batch_path, batch)
    detail["output_hashes"] = runner.tree_hashes(output)
    return detail


def cli_check(unit: Path, source: Path, candidate: Path, destination: Path) -> dict:
    command = [
        sys.executable,
        str(Path(runner.__file__)),
        "check",
        "--unit",
        str(unit),
        "--baseline-output",
        str(source),
        "--candidate-output",
        str(candidate),
        "--out",
        str(destination),
    ]
    process = subprocess.run(command, capture_output=True, timeout=600)
    (destination.parent / f"{destination.name}.stdout.log").write_bytes(process.stdout)
    (destination.parent / f"{destination.name}.stderr.log").write_bytes(process.stderr)
    return {
        "command": command,
        "exit_code": process.returncode,
        "report": str(destination / "summary.json"),
    }


def run_controls(
    source_run: Path,
    units_dir: Path,
    directory: Path,
    side: str,
    names: list[str] | None = None,
    cases: list[str] | None = None,
) -> dict:
    summary_path = source_run / "summary.json"
    source = json.loads(summary_path.read_text())
    if (
        not source.get("complete")
        or not source.get("accepted")
        or not source.get("images")
        or not source.get("runs")
    ):
        raise ValueError(
            "source must be a complete, accepted image run with recorded image/run evidence"
        )
    result = {
        "source_summary_sha256": runner.sha(summary_path),
        "source_images": source["images"],
        "side": side,
        "rankable": False,
        "complete": False,
        "controls_passed": False,
        "positive_controls": [],
        "negative_controls": [],
    }
    units = runner.select_units(units_dir, names or list(runner.DEFAULT_UNITS), False)
    selected_cases = cases or list(CASES)
    if len(set(selected_cases)) != len(selected_cases) or any(
        c not in CASES for c in selected_cases
    ):
        raise ValueError("invalid or duplicate negative control case")
    result["coverage"] = {
        "units": [u.name for u in units],
        "cases": selected_cases,
        "missing_sub_for_batches": True,
    }
    for unit in units:
        record = next(
            r
            for r in source["runs"]
            if r["unit"] == unit.name
            and r["side"] == side
            and r["kind"] == "timing"
            and r["accepted"]
        )
        actual = (
            source_run
            / "runs"
            / unit.name
            / f"timing-{record['index']:02d}"
            / side
            / "retained"
        )
        frozen = directory / unit.name / "source"
        retain_output(actual, frozen, unit)
        if runner.tree_hashes(frozen) != record["check"]["hashes"]:
            raise ValueError(
                f"source output changed since the recorded run: {unit.name}"
            )
        positive = cli_check(unit, frozen, frozen, directory / unit.name / "positive")
        result["positive_controls"].append({"unit": unit.name, **positive})
        if positive["exit_code"] != 0:
            raise ValueError(f"actual positive CLI control failed: {unit.name}")
        for case in (
            *selected_cases,
            *(("missing_sub",) if (unit / "batch.json").exists() else ()),
        ):
            output = directory / unit.name / case / "mutated"
            shutil.copytree(frozen, output)
            if case == "missing_sub":
                sub = runner.trace_layout(unit)[-1][1]
                shutil.rmtree(output / sub)
                mutation = {"case": case, "removed_sub": sub}
            else:
                mutation = mutate(unit, output, case)
            checked = cli_check(unit, frozen, output, output.parent / "checked")
            report = json.loads(Path(checked["report"]).read_text())
            # A crashed CLI/parser is not evidence that the checker rejected a mutation.
            caught = (
                checked["exit_code"] == 1
                and report.get("complete") is True
                and report.get("accepted") is False
                and report.get("check", {}).get("baseline", {}).get("accepted") is True
            )
            result["negative_controls"].append(
                {"unit": unit.name, **mutation, **checked, "mutation_rejected": caught}
            )
            runner.dump(directory / "negative-summary.json", result)
        if (
            runner.tree_hashes(frozen) != record["check"]["hashes"]
            or runner.tree_hashes(actual) != record["check"]["hashes"]
        ):
            raise ValueError(f"negative controls changed source: {unit.name}")
    result["complete"] = len(result["positive_controls"]) == len(units) and len(
        result["negative_controls"]
    ) == len(units) * len(selected_cases) + sum(
        (u / "batch.json").exists() for u in units
    )
    result["controls_passed"] = result["complete"] and all(
        r["mutation_rejected"] for r in result["negative_controls"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--units-dir", type=Path, default=runner.ROOT / "units")
    parser.add_argument(
        "--side", choices=("baseline", "candidate"), default="candidate"
    )
    parser.add_argument(
        "--units",
        nargs="+",
        help="Subset to avoid repeating controls already evidenced by the manager",
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=CASES,
        help="Subset of mutations; coverage is recorded explicitly",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    directory = args.out.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    result = {"rankable": False, "complete": False, "controls_passed": False}
    try:
        result = run_controls(
            args.source_run.resolve(),
            args.units_dir.resolve(),
            directory,
            args.side,
            args.units,
            args.cases,
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    runner.dump(directory / "negative-summary.json", result)
    print(
        json.dumps(
            {
                "output": str(directory),
                "complete": result["complete"],
                "controls_passed": result["controls_passed"],
                "error": result.get("error"),
            }
        )
    )
    return 0 if result["complete"] and result["controls_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

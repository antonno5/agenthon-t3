"""Measure message-table extraction and Python heap separately from simulation."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc
import types
from typing import Any
from unittest.mock import patch

import pandas as pd


def load_adapter(path: Path) -> Any:
    """Load the real adapter; the unused ABIDES order-log parser is a tripwire."""
    utils = types.ModuleType("abides_core.utils")

    def unused(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("message benchmark unexpectedly invoked order-log parsing")

    setattr(utils, "parse_logs_df", unused)
    spec = importlib.util.spec_from_file_location("_ledger_adapter", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {"abides_core": types.ModuleType("abides_core"), "abides_core.utils": utils},
    ):
        spec.loader.exec_module(module)
    return module


def delivery(seq: int) -> tuple[Any, ...]:
    received = 1_612_483_200_000_000_001 + seq * 1000
    wakeup = seq % 5 == 0
    latency = 0 if wakeup else (seq * 7919) % 50_000
    recipient = seq % 3 + 1
    uid = seq // 3 + 1
    return (
        seq,
        received,
        None if wakeup else received - latency,
        latency,
        recipient if wakeup else 0,
        recipient,
        uid,
        "AGENT_WAKEUP" if wakeup else "LimitOrderMsg",
        None if wakeup else 2**53 + seq,
        None if wakeup or uid == 1 else uid - 1,
    )


def state_for(variant: str, count: int, columns: list[str]) -> dict[str, Any]:
    if variant == "after":
        return {
            "message_ledger_format": "delivery_order_v1",
            "message_ledger": [delivery(seq) for seq in range(count)],
        }
    ledger = []
    seqmap = {}
    for seq in range(count):
        row = delivery(seq)
        ledger.append(dict(zip(columns[1:], row[1:])))
        seqmap[(row[6], row[5])] = seq
    # Undelivered sends have no entry in the delivery map.
    for index in range(count // 100):
        undelivered = list(delivery(count + index))
        undelivered[6] = count + index + 1
        ledger.append(dict(zip(columns[1:], undelivered[1:])))
    ledger.sort(key=lambda row: row["t_send_ns"] or row["t_recv_ns"])
    return {"message_ledger": ledger, "deliver_seq_by_key": seqmap}


def benchmark(
    count: int,
    repeats: int,
    output: Path,
    before_adapter: Path | None = None,
    after_adapter: Path | None = None,
) -> dict[str, Any]:
    if before_adapter is not None and after_adapter is not None:
        before_module, after_module = (
            load_adapter(before_adapter),
            load_adapter(after_adapter),
        )
        assert before_module.MESSAGE_TRACE_COLUMNS == after_module.MESSAGE_TRACE_COLUMNS
        columns = before_module.MESSAGE_TRACE_COLUMNS
        extractors = {
            "before": before_module.extract_message_trace,
            "after": after_module.extract_message_trace,
        }
    else:
        from abides_fork.trace import MESSAGE_TRACE_COLUMNS, extract_message_trace

        columns = MESSAGE_TRACE_COLUMNS
        extractors = {"before": extract_message_trace, "after": extract_message_trace}
    output.mkdir(parents=True, exist_ok=True)
    samples: dict[str, list[float]] = {"before": [], "after": []}
    # Allocation tracking is disabled for all speed measurements.
    for index in range(repeats + 1):
        variants = ("before", "after") if index % 2 == 0 else ("after", "before")
        for variant in variants:
            state = state_for(variant, count, columns)
            gc.collect()
            start = time.perf_counter()
            frame = extractors[variant](state)
            elapsed = time.perf_counter() - start
            if index:
                samples[variant].append(elapsed)
            assert len(frame) == count
            del state, frame

    memory = {}
    for variant in ("before", "after"):
        gc.collect()
        tracemalloc.start()
        state = state_for(variant, count, columns)
        frame = extractors[variant](state)
        _, memory[variant] = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        del state, frame

    before = extractors["before"](state_for("before", count, columns))
    after = extractors["after"](state_for("after", count, columns))
    pd.testing.assert_frame_equal(before, after)
    checks = {}
    for variant, frame in (("before", before), ("after", after)):
        path = output / f"{variant}.parquet"
        frame.to_parquet(path, compression="snappy", index=False)
        checks[variant] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {
        "delivered_rows": count,
        "undelivered_before": count // 100,
        "repeats": repeats,
        "warmups": 1,
        "samples_sec": samples,
        "median_extract_sec": {k: statistics.median(v) for k, v in samples.items()},
        "peak_python_heap_bytes": memory,
        "memory_scope": "state construction plus extraction; excludes Parquet; not RSS",
        "time_scope": "extraction only; excludes state construction and Parquet; tracemalloc disabled",
        "parquet_sha256": checks,
        "parquet_bytes_equal": checks["before"] == checks["after"],
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "pandas", "pyarrow")
        },
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=90_000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--before-adapter", type=Path)
    parser.add_argument("--after-adapter", type=Path)
    args = parser.parse_args()
    if args.rows < 1 or args.repeats < 1:
        parser.error("rows and repeats must be positive")
    if bool(args.before_adapter) != bool(args.after_adapter):
        parser.error("both adapter paths must be supplied")
    print(
        json.dumps(
            benchmark(
                args.rows,
                args.repeats,
                args.out,
                args.before_adapter,
                args.after_adapter,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

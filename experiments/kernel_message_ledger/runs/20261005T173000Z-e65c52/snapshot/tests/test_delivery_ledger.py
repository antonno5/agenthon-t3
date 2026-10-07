"""Compatibility of the compact delivery ledger with scored Parquet outputs."""

from __future__ import annotations

import importlib.util
import io
import os
import random
import sys
import types
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> Any:
    utils = types.ModuleType("abides_core.utils")
    utils.parse_logs_df = lambda state: state["raw"]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "abides_core", types.ModuleType("abides_core"))
    monkeypatch.setitem(sys.modules, "abides_core.utils", utils)
    source = (
        Path(os.environ["QFB2_LEDGER_ADAPTER"])
        if os.environ.get("QFB2_LEDGER_ADAPTER")
        else Path(__file__).resolve().parents[1] / "baselines/abides_fork/trace.py"
    )
    spec = importlib.util.spec_from_file_location("_delivery_trace", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, compression="snappy", index=False)
    return buffer.getvalue()


def test_empty_delivery_ledger_preserves_schema(adapter: Any) -> None:
    result = adapter.extract_message_trace(
        {"message_ledger_format": "delivery_order_v1", "message_ledger": []}
    )
    legacy = adapter.extract_message_trace({})
    pd.testing.assert_frame_equal(result, legacy)
    assert parquet_bytes(result) == parquet_bytes(legacy)


def test_delivery_rows_match_legacy_broadcast_wakeup_and_causality(
    adapter: Any,
) -> None:
    epoch = 1_612_483_200_000_000_001
    rows = [
        (0, epoch, None, 0, 1, 1, 10, "AGENT_WAKEUP", None, None),
        (1, epoch + 9, epoch + 1, 8, 1, 0, 11, "LimitOrderMsg", 2**53 + 1, 10),
        (2, epoch + 12, epoch + 10, 2, 0, 1, 12, "OrderAcceptedMsg", 2**53 + 1, 11),
        (3, epoch + 15, epoch + 10, 5, 0, 2, 12, "OrderAcceptedMsg", 2**53 + 1, 11),
    ]
    legacy_rows = [dict(zip(adapter.MESSAGE_TRACE_COLUMNS, row)) for row in rows]
    # The legacy list is in send order; one extra send never reaches its recipient.
    undelivered = {**legacy_rows[1], "message_id": 13, "t_recv_ns": epoch + 100}
    legacy = adapter.extract_message_trace(
        {
            "message_ledger": [
                legacy_rows[0],
                legacy_rows[1],
                legacy_rows[3],
                undelivered,
                legacy_rows[2],
            ],
            "deliver_seq_by_key": {(10, 1): 0, (11, 0): 1, (12, 1): 2, (12, 2): 3},
        }
    )
    result = adapter.extract_message_trace(
        {"message_ledger_format": "delivery_order_v1", "message_ledger": rows}
    )
    pd.testing.assert_frame_equal(result, legacy)
    assert result["t_send_ns"].iloc[1] == epoch + 1
    assert result["order_id"].iloc[1] == 2**53 + 1
    assert parquet_bytes(result) == parquet_bytes(legacy)


def test_delivery_format_reproduces_public_reference_ledger(adapter: Any) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "units/t3-s001-price-time-priority/message_trace.parquet"
    )
    if source.read_bytes()[:4] != b"PAR1":
        pytest.skip("public reference ledger requires Git LFS content")
    reference = pd.read_parquet(source)
    # Convert nullable cells back to the kernel's None representation.
    rows = [
        tuple(None if pd.isna(value) else value for value in row)
        for row in reference.itertuples(index=False, name=None)
    ]
    result = adapter.extract_message_trace(
        {"message_ledger_format": "delivery_order_v1", "message_ledger": rows}
    )
    pd.testing.assert_frame_equal(result, reference)
    assert parquet_bytes(result) == parquet_bytes(reference)


@pytest.mark.parametrize("integer", [2**53 - 1, 2**53 + 1, 2**63 - 11])
def test_nullable_int64_boundaries_survive_parquet_roundtrip(
    adapter: Any, integer: int
) -> None:
    rows = [
        (0, integer, None, 0, 1, 1, integer, "AGENT_WAKEUP", None, None),
        (
            1,
            integer + 9,
            integer + 1,
            8,
            1,
            0,
            integer + 1,
            "LimitOrderMsg",
            integer,
            integer,
        ),
    ]
    frame = adapter.extract_message_trace(
        {"message_ledger_format": "delivery_order_v1", "message_ledger": rows}
    )
    reread = pd.read_parquet(io.BytesIO(parquet_bytes(frame)))
    pd.testing.assert_frame_equal(frame, reread)
    assert reread.loc[1, "t_send_ns"] == integer + 1
    assert reread.loc[1, "order_id"] == integer
    assert reread.loc[1, "causal_parent"] == integer
    assert reread.loc[1, "t_recv_ns"] - reread.loc[1, "t_send_ns"] == 8


def test_extraction_does_not_mutate_or_share_kernel_ledger(adapter: Any) -> None:
    row = (0, 1009, 1001, 8, 0, 1, 10, "OrderAcceptedMsg", 7, None)
    state = {"message_ledger_format": "delivery_order_v1", "message_ledger": [row]}
    first = adapter.extract_message_trace(state)
    first.loc[0, "order_id"] = 999
    second = adapter.extract_message_trace(state)
    assert state["message_ledger"] == [row]
    assert second.loc[0, "order_id"] == 7


@pytest.mark.parametrize("seed", range(20))
def test_randomized_delivery_ledgers_match_legacy_parquet(
    adapter: Any, seed: int
) -> None:
    rng = random.Random(seed)
    epoch = 1_612_483_200_000_000_001
    rows = []
    for seq in range(300):
        receive = epoch + seq * 1000
        wakeup = rng.random() < 0.2
        latency = 0 if wakeup else rng.randrange(1000)
        sender, recipient = rng.randrange(4), rng.randrange(4)
        rows.append(
            (
                seq,
                receive,
                None if wakeup else receive - latency,
                latency,
                recipient if wakeup else sender,
                recipient,
                2**53 + seq,
                "AGENT_WAKEUP" if wakeup else "LimitOrderMsg",
                None if wakeup or rng.random() < 0.5 else 2**53 + rng.randrange(300),
                None if wakeup or seq == 0 else 2**53 + rng.randrange(seq),
            )
        )
    legacy_rows = [dict(zip(adapter.MESSAGE_TRACE_COLUMNS, row)) for row in rows]
    rng.shuffle(legacy_rows)
    legacy = adapter.extract_message_trace(
        {
            "message_ledger": legacy_rows,
            "deliver_seq_by_key": {(row[6], row[5]): row[0] for row in rows},
        }
    )
    compact = adapter.extract_message_trace(
        {"message_ledger_format": "delivery_order_v1", "message_ledger": rows}
    )
    pd.testing.assert_frame_equal(compact, legacy)
    assert parquet_bytes(compact) == parquet_bytes(legacy)

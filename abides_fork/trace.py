"""Extract the canonical Track 3 message trace from an ABIDES ``end_state``.

ABIDES logs per-agent events; ``abides_core.utils.parse_logs_df`` flattens them
into a DataFrame. This module maps the relevant ABIDES event types onto the
canonical 7-column ``trace.parquet`` schema defined in
``templates/trace_column_registry.json``:

    [t_ns, agent_id, msg_type, side, price, size, order_id]

ABIDES event type      -> canonical msg_type
    ORDER_SUBMITTED     -> ORDER_SUBMITTED
    ORDER_ACCEPTED      -> ORDER_ACCEPTED
    ORDER_EXECUTED      -> PARTIAL_FILL (non-final per order) / ORDER_FILLED (final)
    ORDER_CANCELLED     -> ORDER_CANCELLED
    ORDER_REPLACED      -> ORDER_REPLACED
    BEST_BID / BEST_ASK -> QUOTE_UPDATE (side BID / ASK)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

TRACE_COLUMNS: list[str] = [
    "t_ns",
    "agent_id",
    "msg_type",
    "side",
    "price",
    "size",
    "order_id",
]

# ABIDES EventType -> canonical msg_type for order-lifecycle events whose price
# is the order's limit price. ORDER_EXECUTED is handled separately (fill price,
# and the PARTIAL_FILL / ORDER_FILLED split).
_ORDER_EVENT_MAP: dict[str, str] = {
    "ORDER_SUBMITTED": "ORDER_SUBMITTED",
    "ORDER_ACCEPTED": "ORDER_ACCEPTED",
    "ORDER_CANCELLED": "ORDER_CANCELLED",
    "ORDER_REPLACED": "ORDER_REPLACED",
}

_TRACE_DTYPES: dict[str, str] = {
    "t_ns": "int64",
    "agent_id": "int32",
    "msg_type": "string",
    "side": "string",
    "price": "int64",
    "size": "int64",
    "order_id": "int64",
}

# --- v2 enriched message-level trace (companion to the order-event trace) --------------
# One row per DELIVERED (sub)message from the kernel ledger, carrying the network + causal
# metadata the v2 latency / event-order / wakeup / reactive / protocol gates need. This is a
# SEPARATE table (message granularity != order-event granularity), so trace.parquet stays a
# byte-for-byte v1 superset and existing Tier-A/Tier-B/stylized checks are unaffected.
MESSAGE_TRACE_COLUMNS: list[str] = [
    "seq",
    "t_recv_ns",
    "t_send_ns",
    "latency_ns",
    "src_id",
    "dst_id",
    "message_id",
    "msg_type",
    "order_id",
    "causal_parent",
]

_MSG_DTYPES: dict[str, str] = {
    "seq": "int64",
    "t_recv_ns": "int64",
    "t_send_ns": "Int64",  # nullable: wakeups have no send time
    "latency_ns": "int64",
    "src_id": "int32",
    "dst_id": "int32",
    "message_id": "int64",
    "msg_type": "string",
    "order_id": "Int64",  # nullable: non-order messages
    "causal_parent": "Int64",  # nullable: root events
}


def _side_to_str(value: Any) -> str | None:
    """Normalize an ABIDES ``Side`` enum (or string) to ``"BID"`` / ``"ASK"``."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    enum_val = getattr(value, "value", None)
    if enum_val in ("BID", "ASK"):
        return str(enum_val)
    text = str(value).upper()
    if "BID" in text:
        return "BID"
    if "ASK" in text:
        return "ASK"
    return None


def _raw_from_logs(end_state: dict[str, Any]) -> pd.DataFrame:
    """The subset of ``abides_core.utils.parse_logs_df`` that ``extract_trace`` reads.

    Same rows in the same order (agents in list order, each agent's log in append order),
    same ``EventTime`` / ``agent_id`` fallbacks, but only the columns used below, built
    straight from the ``_OrderSnapshot`` tuples ``config.py`` logs instead of exploding a
    dict per row.
    """
    ev_time: list = []
    ev_type: list = []
    agent_ids: list = []
    order_ids: list = []
    sides: list = []
    limit_prices: list = []
    fill_prices: list = []
    quantities: list = []
    scalars: list = []
    nan = np.nan
    int_types = (int, np.int64)
    for agent in end_state["agents"]:
        aid = agent.id
        for t, etype, ev in agent.log:
            ev_time.append(t if isinstance(t, int_types) else 0)
            ev_type.append(etype)
            if isinstance(ev, tuple):
                o_agent, side, limit_price, fill_price, qty, oid = ev
                agent_ids.append(aid if o_agent is None else o_agent)
                order_ids.append(nan if oid is None else oid)
                sides.append(side)
                limit_prices.append(nan if limit_price is None else limit_price)
                fill_prices.append(nan if fill_price is None else fill_price)
                quantities.append(nan if qty is None else qty)
                scalars.append(nan)
            else:
                agent_ids.append(aid)
                order_ids.append(nan)
                sides.append(nan)
                limit_prices.append(nan)
                fill_prices.append(nan)
                quantities.append(nan)
                scalars.append(nan if ev is None else ev)
    return pd.DataFrame(
        {
            "EventTime": np.array(ev_time, dtype=np.int64),
            "EventType": ev_type,
            "agent_id": agent_ids,
            "order_id": np.array(order_ids, dtype=np.float64),
            "side": sides,
            "limit_price": np.array(limit_prices, dtype=np.float64),
            "fill_price": np.array(fill_prices, dtype=np.float64),
            "quantity": np.array(quantities, dtype=np.float64),
            "ScalarEventValue": scalars,
        }
    )


def extract_trace(end_state: dict[str, Any]) -> pd.DataFrame:
    """Build the canonical 7-column trace DataFrame from an ABIDES ``end_state``.

    Args:
        end_state: the dict returned by ``abides_core.abides.run``.

    Returns:
        A DataFrame with columns ``TRACE_COLUMNS`` and canonical dtypes, sorted by
        ``(t_ns, order_id)``.
    """
    raw = _raw_from_logs(end_state)

    # --- order-lifecycle events (rows carrying an order_id), vectorized ---------
    # parse_logs_df returns a non-unique index (per-agent row numbers); sort by
    # EventTime and reset so the final-execution lookup is positionally unambiguous
    # and the post-sort tie order is the causal (processing) order.
    orders = (
        raw[raw["order_id"].notna()]
        .sort_values("EventTime", kind="stable")
        .reset_index(drop=True)
    )
    keep = orders["EventType"].isin(_ORDER_EVENT_MAP.keys()) | (
        orders["EventType"] == "ORDER_EXECUTED"
    )
    o = orders[keep].reset_index(drop=True)
    is_exec = o["EventType"] == "ORDER_EXECUTED"
    # The final ORDER_EXECUTED per order_id is the ORDER_FILLED; earlier ones are
    # PARTIAL_FILL ("final" = last occurrence per order_id in EventTime order).
    final_pos = o[is_exec].drop_duplicates("order_id", keep="last").index
    is_final = o.index.isin(final_pos)
    msg_type = (
        o["EventType"]
        .map(_ORDER_EVENT_MAP)
        .where(
            ~is_exec,
            pd.Series(
                np.where(is_final, "ORDER_FILLED", "PARTIAL_FILL"), index=o.index
            ),
        )
    )
    # ORDER_EXECUTED rows carry the fill price; lifecycle rows carry the limit price.
    # Reference the columns lazily so a fills-only / no-fills trace cannot KeyError.
    limit_price = (
        o["limit_price"]
        if "limit_price" in o.columns
        else pd.Series(np.nan, index=o.index)
    )
    fill_price = (
        o["fill_price"]
        if "fill_price" in o.columns
        else pd.Series(np.nan, index=o.index)
    )
    price = limit_price.where(~is_exec, fill_price)
    # Normalize the Side enum once per distinct value, then map (C-level) — much
    # cheaper than calling _side_to_str on every row at F6 scale.
    side_map = {v: _side_to_str(v) for v in o["side"].dropna().unique()}
    order_df = pd.DataFrame(
        {
            "t_ns": o["EventTime"],
            "agent_id": o["agent_id"],
            "msg_type": msg_type,
            "side": o["side"].map(side_map),
            "price": price,
            "size": o["quantity"],
            "order_id": o["order_id"],
        }
    )

    # --- quote events: BEST_BID / BEST_ASK -> QUOTE_UPDATE (vectorized) ---------
    # ABIDES emits a best-bid/ask event per book change, so several land on the same
    # nanosecond as an agent posts a price ladder. Keep only the final quote per
    # (t_ns, side): the resting best price at that instant. This keeps quote timestamps
    # unique per side (the scorer's mid-price series reindexes on them and cannot
    # tolerate duplicate labels). "Final" = last occurrence in emission order; the
    # surviving rows are ordered by each (t_ns, side)'s first appearance.
    quotes = raw[raw["EventType"].isin(["BEST_BID", "BEST_ASK"])]
    qparts = quotes["ScalarEventValue"].astype(str).str.split(",", expand=True)
    if qparts.shape[1] >= 3:
        # ScalarEventValue is "SYMBOL,price,volume" -> exactly two commas, int fields.
        q_price = pd.to_numeric(qparts[1], errors="coerce")
        q_size = pd.to_numeric(qparts[2], errors="coerce")
        valid = (
            (quotes["ScalarEventValue"].astype(str).str.count(",") == 2)
            & q_price.notna()
            & q_size.notna()
        )
    else:
        valid = pd.Series(False, index=quotes.index)
    qv = quotes[valid].reset_index(drop=True)
    if qv.empty:
        quote_df = pd.DataFrame(columns=TRACE_COLUMNS)
    else:
        side = pd.Series(
            np.where(qv["EventType"] == "BEST_BID", "BID", "ASK"), index=qv.index
        )
        # factorize gives each (t_ns, side) a rank by first appearance == the order a
        # dict keyed on first insertion would yield.
        key = qv["EventTime"].astype("int64").astype(str) + "|" + side
        quote_df = pd.DataFrame(
            {
                "t_ns": qv["EventTime"],
                "agent_id": qv["agent_id"],
                "msg_type": "QUOTE_UPDATE",
                "side": side,
                "price": q_price[valid].to_numpy(),
                "size": q_size[valid].to_numpy(),
                "order_id": -1,
                "_rank": pd.factorize(key)[0],
            }
        )
        quote_df = (
            quote_df.drop_duplicates(["t_ns", "side"], keep="last")
            .sort_values("_rank", kind="stable")
            .drop(columns="_rank")
        )

    # --- combine, fill missing numerics, sort canonically ----------------------
    trace = pd.concat([order_df, quote_df], ignore_index=True)
    if trace.empty:
        return trace.astype(_TRACE_DTYPES)
    trace["price"] = trace["price"].fillna(0)
    trace["size"] = trace["size"].fillna(0)
    trace["order_id"] = trace["order_id"].fillna(-1)
    trace = trace.sort_values(["t_ns", "order_id"], kind="stable").reset_index(
        drop=True
    )
    return trace.astype(_TRACE_DTYPES)


def extract_message_trace(end_state: dict[str, Any]) -> pd.DataFrame:
    """Build the v2 message-level enriched trace from the kernel ledger in ``end_state``.

    Companion to the order-lifecycle ``trace.parquet``: one row per DELIVERED (sub)message,
    ordered by the faithful kernel processing order (``seq``). Requires the
    ``kernel_message_ledger`` patch (``end_state["message_ledger"]`` +
    ``end_state["deliver_seq_by_key"]``); returns an empty typed frame if absent.

    Args:
        end_state: the dict returned by ``abides_core.abides.run``.

    Returns:
        A DataFrame with columns ``MESSAGE_TRACE_COLUMNS`` and canonical dtypes.
    """
    ledger = end_state.get("message_ledger") or []
    seqmap = end_state.get("deliver_seq_by_key") or {}
    empty = pd.DataFrame({c: [] for c in MESSAGE_TRACE_COLUMNS}).astype(_MSG_DTYPES)
    if not ledger:
        return empty

    # Attach the faithful delivery seq (keyed by (message_id, recipient) — a broadcast message
    # carries one id but N deliveries) and keep only DELIVERED rows (undelivered sends past
    # stop_time have no seq). Sort by processing order. Ledger rows are kernel tuples:
    # (message_id, src_id, dst_id, t_send_ns, t_recv_ns, latency_ns, msg_type, order_id,
    #  causal_parent).
    get = seqmap.get
    rows = [
        (seq, r) for r in ledger if (seq := get((r[0], r[2]))) is not None
    ]
    if not rows:
        return empty
    rows.sort(key=lambda sr: sr[0])
    seqs = [s for s, _ in rows]
    (
        message_id,
        src_id,
        dst_id,
        t_send,
        t_recv,
        latency,
        msg_type,
        order_id,
        causal_parent,
    ) = zip(*(r for _, r in rows))

    # The nullable-int columns (t_send_ns, order_id, causal_parent) MUST stay exact int64:
    # routing None+int through float64 would round the ~1.6e18 ns timestamps. Build each as
    # an int64 value array plus a null mask (the IntegerArray pd.array would produce).
    def _nullable_int(values: tuple) -> pd.arrays.IntegerArray:
        mask = np.fromiter((v is None for v in values), dtype=bool, count=len(values))
        data = np.fromiter(
            (0 if v is None else v for v in values), dtype=np.int64, count=len(values)
        )
        return pd.arrays.IntegerArray(data, mask)

    df = pd.DataFrame(
        {
            "seq": np.array(seqs, dtype=np.int64),
            "t_recv_ns": np.array(t_recv, dtype=np.int64),
            "t_send_ns": _nullable_int(t_send),
            "latency_ns": np.array(latency, dtype=np.int64),
            "src_id": np.array(src_id, dtype=np.int32),
            "dst_id": np.array(dst_id, dtype=np.int32),
            "message_id": np.array(message_id, dtype=np.int64),
            "msg_type": pd.array(msg_type, dtype="string"),
            "order_id": _nullable_int(order_id),
            "causal_parent": _nullable_int(causal_parent),
        }
    ).astype(_MSG_DTYPES)
    return df[MESSAGE_TRACE_COLUMNS]

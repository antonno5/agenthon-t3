"""Capture canonical exchange events directly in fixed-width column buffers.

ABIDES's legacy parser flattens logs in agent-list order, not delivery order.
Equal-time ties, final-fill labels and quote deduplication preserve that ordering.
Only observation changes: message delivery, random draws and book logic are untouched.
"""

from __future__ import annotations

from array import array
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Iterator

import numpy as np
import pandas as pd

from abides_fork.trace import TRACE_COLUMNS, _side_to_str

_TYPES = (
    "ORDER_SUBMITTED",
    "ORDER_ACCEPTED",
    "ORDER_CANCELLED",
    "ORDER_REPLACED",
    "PARTIAL_FILL",
    "ORDER_FILLED",
    "QUOTE_UPDATE",
)
_CODES = {name: i for i, name in enumerate(_TYPES)}
_SIDES = (None, "BID", "ASK")


class Columns:
    """One growable typed array per output column; no event dictionaries."""

    def __init__(self) -> None:
        self.t_ns = array("q")
        self.agent_id = array("i")
        self.kind = array("b")
        self.side = array("b")
        self.price = array("q")
        self.size = array("q")
        self.order_id = array("q")

    def append(
        self,
        t: int,
        agent: int,
        kind: int,
        side: int,
        price: int,
        size: int,
        order: int,
    ) -> int:
        index = len(self.t_ns)
        self.t_ns.append(t)
        self.agent_id.append(agent)
        self.kind.append(kind)
        self.side.append(side)
        self.price.append(price)
        self.size.append(size)
        self.order_id.append(order)
        return index

    def numpy(self, column: str) -> Any:
        dtype = (
            "int8"
            if column in {"kind", "side"}
            else ("int32" if column == "agent_id" else "int64")
        )
        return np.frombuffer(getattr(self, column), dtype=dtype)


class TraceCollector:
    def __init__(self, agents: list[Any]) -> None:
        self.ranks = {agent.id: rank for rank, agent in enumerate(agents)}
        self.orders = {agent.id: Columns() for agent in agents}
        self.quotes = Columns()
        self.quote_index: dict[tuple[int, int], int] = {}
        self.quote_first: list[tuple[int, int]] = []
        self.quote_last: list[tuple[int, int]] = []
        self.quote_sequence = {agent.id: 0 for agent in agents}
        self.final_fill: dict[int, tuple[tuple[int, int, int], Columns, int]] = {}

    def record(self, agent: Any, event_type: str, event: Any) -> None:
        t = agent.current_time
        t = int(t) if isinstance(t, (int, np.integer)) else 0
        rank = self.ranks[agent.id]
        if event_type in {"BEST_BID", "BEST_ASK"}:
            if isinstance(event, dict):
                return
            parts = str(event).split(",")
            if len(parts) != 3:
                return
            try:
                price = self._integer(parts[1])
                size = self._integer(parts[2])
            except (ValueError, OverflowError):
                return
            side = 1 if event_type == "BEST_BID" else 2
            ordinal = self.quote_sequence[agent.id]
            self.quote_sequence[agent.id] += 1
            flat_key = (rank, ordinal)
            key = (t, side)
            index = self.quote_index.get(key)
            if index is None:
                index = self.quotes.append(t, agent.id, 6, side, price, size, -1)
                self.quote_index[key] = index
                self.quote_first.append(flat_key)
                self.quote_last.append(flat_key)
            else:
                self.quote_first[index] = min(self.quote_first[index], flat_key)
                if flat_key > self.quote_last[index]:
                    self.quote_last[index] = flat_key
                    self.quotes.agent_id[index] = agent.id
                    self.quotes.price[index] = price
                    self.quotes.size[index] = size
            return

        if event_type not in _CODES and event_type != "ORDER_EXECUTED":
            return
        if not isinstance(event, dict) or event.get("order_id") is None:
            return
        columns = self.orders[agent.id]
        order = int(event["order_id"])
        side = _SIDES.index(_side_to_str(event.get("side")))
        execution = event_type == "ORDER_EXECUTED"
        order_price = event.get("fill_price" if execution else "limit_price")
        owner = event.get("agent_id")
        index = columns.append(
            t,
            int(owner) if owner is not None else agent.id,
            4 if execution else _CODES[event_type],
            side,
            int(order_price) if order_price is not None else 0,
            int(event.get("quantity") or 0),
            order,
        )
        if execution:
            fill_key = (t, rank, index)
            previous = self.final_fill.get(order)
            if previous is None or fill_key > previous[0]:
                if previous is not None:
                    previous[1].kind[previous[2]] = 4
                columns.kind[index] = 5
                self.final_fill[order] = (fill_key, columns, index)

    @staticmethod
    def _integer(value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return int(float(value))

    def to_frame(self) -> pd.DataFrame:
        # Original order rows precede quote rows before the final stable sort.
        buffers = list(self.orders.values()) + [self.quotes]
        data = {
            column: np.concatenate([buffer.numpy(column) for buffer in buffers])
            for column in (
                "t_ns",
                "agent_id",
                "kind",
                "side",
                "price",
                "size",
                "order_id",
            )
        }
        n_orders = sum(len(buffer.t_ns) for buffer in self.orders.values())
        quote_order = sorted(
            range(len(self.quote_first)), key=self.quote_first.__getitem__
        )
        initial = np.concatenate(
            (np.arange(n_orders), n_orders + np.asarray(quote_order, dtype=np.int64))
        )
        # lexsort uses the flattened ordinal as an explicit last tie-breaker.
        selection = initial[
            np.lexsort(
                (
                    np.arange(len(initial)),
                    data["order_id"][initial],
                    data["t_ns"][initial],
                )
            )
        ]
        result = pd.DataFrame(
            {
                "t_ns": data["t_ns"][selection],
                "agent_id": data["agent_id"][selection],
                "msg_type": pd.array(
                    np.asarray(_TYPES, dtype=object)[data["kind"][selection]],
                    dtype="string",
                ),
                "side": pd.array(
                    np.asarray(_SIDES, dtype=object)[data["side"][selection]],
                    dtype="string",
                ),
                "price": data["price"][selection],
                "size": data["size"][selection],
                "order_id": data["order_id"][selection],
            }
        )
        return result[TRACE_COLUMNS]

    @contextmanager
    def capture(self, *, retain_logs: bool = False) -> Iterator[None]:
        from abides_core.agent import Agent

        original = Agent.logEvent

        def log_event(
            agent: Any,
            event_type: str,
            event: Any = "",
            append_summary_log: bool = False,
            deepcopy_event: bool = True,
        ) -> None:
            if not agent.log_events:
                return
            self.record(agent, event_type, event)
            if retain_logs:
                original(agent, event_type, event, append_summary_log, deepcopy_event)
            elif append_summary_log:
                payload = deepcopy(event) if deepcopy_event else event
                agent.kernel.append_summary_log(agent.id, event_type, payload)

        Agent.logEvent = log_event
        try:
            yield
        finally:
            Agent.logEvent = original

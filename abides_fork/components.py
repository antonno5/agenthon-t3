"""Optional exclusive wall-clock accounting for diagnostic runs only.

Nested callbacks are subtracted from their caller, so totals never double-count
matching, latency or event capture as agent time. Wrappers are removed on exit.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from functools import wraps
import queue
import time
from typing import Any, Callable, Iterator


class ComponentProfiler:
    def __init__(self, clock: Callable[[], int] = time.perf_counter_ns) -> None:
        self.clock = clock
        self.seconds: dict[str, float] = defaultdict(float)
        self.calls: dict[str, int] = defaultdict(int)
        self.stack: list[list[int]] = []

    def wrap(self, function: Callable[..., Any], category: str) -> Callable[..., Any]:
        @wraps(function)
        def measured(*args: Any, **kwargs: Any) -> Any:
            frame = [self.clock(), 0]
            self.stack.append(frame)
            try:
                return function(*args, **kwargs)
            finally:
                elapsed = self.clock() - frame[0]
                self.stack.pop()
                if self.stack:
                    self.stack[-1][1] += elapsed
                self.seconds[category] += (elapsed - frame[1]) / 1e9
                self.calls[category] += 1

        return measured

    @contextmanager
    def instrument(self) -> Iterator[None]:
        from abides_core.agent import Agent
        from abides_markets.agents import ExchangeAgent
        from abides_markets.order_book import OrderBook
        from abides_markets.oracles import SparseMeanRevertingOracle
        from abides_fork.agents import ScheduledAgent
        from abides_fork.config import ScenarioLatencyModel

        targets = (
            [
                (queue.PriorityQueue, name, "event_queue")
                for name in ("put", "get", "empty")
            ]
            + [
                (ScheduledAgent, name, "agent_logic")
                for name in ("wakeup", "receive_message")
            ]
            + [
                (ExchangeAgent, name, "exchange")
                for name in ("wakeup", "receive_message")
            ]
            + [
                (OrderBook, name, "matching")
                for name in (
                    "handle_limit_order",
                    "handle_market_order",
                    "cancel_order",
                    "modify_order",
                    "partial_cancel_order",
                    "replace_order",
                )
            ]
            + [
                (ScenarioLatencyModel, "get_latency", "latency"),
                (SparseMeanRevertingOracle, "observe_price", "oracle"),
                (Agent, "logEvent", "event_capture"),
            ]
        )
        originals: list[tuple[Any, str, bool, Any]] = []
        try:
            for owner, name, category in targets:
                local = name in owner.__dict__
                original = getattr(owner, name)
                originals.append((owner, name, local, original))
                setattr(owner, name, self.wrap(original, category))
            yield
        finally:
            for owner, name, local, original in reversed(originals):
                if local:
                    setattr(owner, name, original)
                else:
                    delattr(owner, name)

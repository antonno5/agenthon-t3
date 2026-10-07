"""Count actual offset usage in an untimed candidate simulation.

Executive summary: distinguish head deletions from other cancellations without
changing the trading rules; instrumentation is excluded from timing samples.
"""

from collections import Counter
import argparse
import json
from pathlib import Path
import time
from abides_markets.matching.state import _PriceLevels
from abides_markets.matching.price_level import PriceLevel
from abides_markets.order_book import OrderBook
from abides_fork.simulate import main as simulate

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--diagnostics", type=Path, required=True)
args, argv = parser.parse_known_args()
counts = Counter()
levels = Counter()
context = ["other"]


def wrap_position(original):
    def position(self, order):
        levels[len(self)] += 1
        start = time.perf_counter_ns()
        result = original(self, order)
        counts["search_nanoseconds"] += time.perf_counter_ns() - start
        counts["search_calls"] += 1
        counts["search_head"] += result == 0
        return result

    return position


def wrap_inserted(original):
    def inserted(self, index):
        before = self._prices_start
        result = original(self, index)
        counts["inserted_levels"] += 1
        counts[
            "insert_"
            + ("head" if index == 0 else "tail" if index == len(self) - 1 else "middle")
        ] += 1
        counts["prefix_slot_reuses"] += before > 0 and self._prices_start == before - 1
        return result

    return inserted


def wrap_remove(original):
    def remove(self, index):
        start = self._prices_start
        old = self._prices
        tick = time.perf_counter_ns()
        result = original(self, index)
        counts["key_remove_nanoseconds"] += time.perf_counter_ns() - tick
        counts["removed_levels"] += 1
        position = "head" if index == 0 else "tail" if index == len(self) else "middle"
        counts["remove_" + position] += 1
        counts[context[0] + "_remove_" + position] += 1
        if not self:
            counts["empty_resets"] += 1
        elif self._prices is not old:
            counts["compactions"] += 1
        elif index == 0 and self._prices_start == start + 1:
            counts["head_offset_advances"] += 1
        counts["max_discarded_prefix"] = max(
            counts["max_discarded_prefix"], self._prices_start
        )
        counts["max_key_slots"] = max(counts["max_key_slots"], len(self._prices))
        assert len(self._prices) <= 2 * len(self) + 63
        return result

    return remove


def wrap_ordered(original):
    def ordered(self, order):
        causes = []
        if self._dirty:
            causes.append("dirty")
        if self._revision != PriceLevel._price_revision:
            causes.append("price_revision")
        if self._length != len(self):
            causes.append("length")
        result = original(self, order)
        counts["certificate_checks"] += 1
        if causes:
            counts["rebuilds"] += 1
            for cause in causes:
                counts["rebuild_" + cause] += 1
        return result

    return ordered


def wrap_cancel(original):
    def cancel(self, *argv, **kwargs):
        prior = context[0]
        context[0] = "cancel"
        before = len(self.bids) + len(self.asks)
        try:
            result = original(self, *argv, **kwargs)
            counts["cancel_requests"] += 1
            counts["cancel_successes"] += bool(result)
            if result:
                counts[
                    "cancel_removed_level"
                    if len(self.bids) + len(self.asks) < before
                    else "cancel_kept_level"
                ] += 1
            return result
        finally:
            context[0] = prior

    return cancel


_PriceLevels._position = wrap_position(_PriceLevels._position)
_PriceLevels._inserted = wrap_inserted(_PriceLevels._inserted)
_PriceLevels._remove_key = wrap_remove(_PriceLevels._remove_key)
_PriceLevels._ordered_for = wrap_ordered(_PriceLevels._ordered_for)
OrderBook.cancel_order = wrap_cancel(OrderBook.cancel_order)
try:
    status = simulate(argv)
finally:
    args.diagnostics.parent.mkdir(parents=True, exist_ok=True)
    args.diagnostics.write_text(
        json.dumps(
            {
                "executive_summary": "Untimed instrumented candidate run; counts describe actual index operations, not an official or comparable latency profile.",
                "rankable": False,
                "counts": dict(counts),
                "price_level_count_at_search": dict(sorted(levels.items())),
            },
            indent=2,
        )
        + "\n"
    )
raise SystemExit(status)

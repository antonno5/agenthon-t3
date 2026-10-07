"""Measure price-search workloads on deterministic synthetic Python books.

Executive summary: isolate lookup, add, cancel, modify and new-level churn at six
book sizes. These warm-book timings are diagnostic, not full simulator scores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import time

from abides_markets.order_book import OrderBook
from abides_markets.orders import LimitOrder, Side


class Owner:
    mkt_open = 0
    current_time = 0
    book_logging = False
    book_log_depth = 10
    stp_policy = None

    def send_message(self, *args):
        pass

    def logEvent(self, *args):
        pass


def order(identifier, price, quantity=1):
    return LimitOrder(1, 0, "X", quantity, Side.ASK, price, order_id=identifier)


def case(size, phase, count):
    book = OrderBook(Owner(), "X")
    for i in range(size):
        book.enter_order(order(-1 - i, 1000 + 2 * i), quiet=True)
    rng = random.Random(20261006)
    positions = [rng.randrange(size) for _ in range(count)]
    orders = [
        order(10000 + i, 1000 + 2 * position + (phase == "new_level_churn"))
        for i, position in enumerate(positions)
    ]
    replacements = [
        order(-1 - position, 1000 + 2 * position, 1 + (i % 2))
        for i, position in enumerate(positions)
    ]
    if phase == "cancel_existing":
        for value in orders:
            book.enter_order(value, quiet=True)
    # Warm lazy metadata for the measured initial book; mutations remain timed.
    list(book._matching_price_levels(book.asks, order(-1, 1000)))
    checksum = 0
    started = time.perf_counter_ns()
    if phase == "lookup":
        for value in orders:
            for index, level in book._matching_price_levels(book.asks, value):
                checksum += index + level.price
    elif phase == "add_existing":
        for value in orders:
            book.enter_order(value, quiet=True)
    elif phase == "cancel_existing":
        for value in orders:
            assert book.cancel_order(value, quiet=True)
    elif phase == "modify_existing":
        for position, replacement in zip(positions, replacements):
            book.modify_order(order(-1 - position, 1000 + 2 * position), replacement)
    elif phase == "new_level_churn":
        for value in orders:
            book.enter_order(value, quiet=True)
            assert book.cancel_order(value, quiet=True)
    else:
        raise ValueError(phase)
    elapsed = (time.perf_counter_ns() - started) / 1e9
    # Domain outputs only; caches and implementation metadata are excluded.
    state = {
        "l2": book.get_l2_ask_data(),
        "l3": book.get_l3_ask_data(),
        "checksum": checksum,
        "history": book.history,
    }
    digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    return {
        "levels": size,
        "phase": phase,
        "operations": count,
        "seconds": elapsed,
        "ns_per_operation": elapsed * 1e9 / count,
        "domain_sha256": digest,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--pair", type=int, required=True)
    args = parser.parse_args()
    results = []
    for size in [1, 4, 16, 64, 256, 1024]:
        for phase in [
            "lookup",
            "add_existing",
            "cancel_existing",
            "modify_existing",
            "new_level_churn",
        ]:
            case(size, phase, 200)
            results.append(case(size, phase, 2000))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "executive_summary": "Diagnostic synthetic warm-book timings, not an official simulator score.",
                "variant": args.variant,
                "pair": args.pair,
                "rankable": False,
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()

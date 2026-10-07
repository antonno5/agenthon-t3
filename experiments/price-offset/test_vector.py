"""Check maintained price keys and the head path on the actual installed engine."""

from copy import deepcopy
import pickle
import pytest
from test_runtime import new_book, limit
from abides_markets.matching.state import _PriceLevels
from abides_markets.orders import Side


def check_vector(levels, side):
    target = limit(9999, side, 100)
    if levels._ordered_for(target):
        assert levels._prices[levels._prices_start :] == [
            (-x.price if side.is_bid() else x.price) for x in levels
        ]
        assert levels._prices[levels._prices_start :] == sorted(
            levels._prices[levels._prices_start :]
        )
        assert len(levels._prices) - levels._prices_start == len(levels)


@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_head_lookup_and_existing_add_do_not_call_binary_search(side, monkeypatch):
    import abides_markets.matching.state as state

    book, _ = new_book()
    prices = range(2048, 0, -2) if side.is_bid() else range(2, 2050, 2)
    for i, price in enumerate(prices):
        book._place_order(limit(i, side, price))
    levels = book.bids if side.is_bid() else book.asks
    target = limit(5000, side, levels[0].price)

    def forbidden(*args, **kwargs):
        pytest.fail("Head operation must not invoke binary search")

    monkeypatch.setattr(state, "bisect_left", forbidden)
    monkeypatch.setattr(_PriceLevels, "_key", forbidden)
    assert list(book._matching_price_levels(levels, target)) == [(0, levels[0])]
    book._place_order(target)
    assert levels[0].remove_order(target.order_id) is not None


@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
@pytest.mark.parametrize(
    "mutation",
    [
        "delete_head",
        "delete_tail",
        "delete_slice",
        "pop_head",
        "pop_tail",
        "remove",
        "insert_negative",
        "insert_clamped",
        "append",
        "replace",
        "extend",
        "reverse_sort",
        "price_edit",
        "clear",
    ],
)
def test_price_vector_tracks_public_mutations(side, mutation):
    book, _ = new_book()
    prices = [106, 104, 102, 100] if side.is_bid() else [100, 102, 104, 106]
    for i, p in enumerate(prices):
        book._place_order(limit(i, side, p))
    levels = book.bids if side.is_bid() else book.asks

    def extra(price):
        from abides_markets.price_level import PriceLevel

        return PriceLevel([(limit(5000, side, price), {})])

    if mutation == "delete_head":
        del levels[0]
    elif mutation == "delete_tail":
        del levels[-1]
    elif mutation == "delete_slice":
        del levels[1::2]
    elif mutation == "pop_head":
        levels.pop(0)
    elif mutation == "pop_tail":
        levels.pop()
    elif mutation == "remove":
        levels.remove(levels[1])
    elif mutation == "insert_negative":
        levels.insert(-1, extra(101 if side.is_bid() else 105))
    elif mutation == "insert_clamped":
        levels.insert(-99, extra(108 if side.is_bid() else 98))
    elif mutation == "append":
        levels.append(extra(98 if side.is_bid() else 108))
    elif mutation == "replace":
        levels[1] = extra(104 if side.is_bid() else 102)
    elif mutation == "extend":
        levels.extend([extra(98 if side.is_bid() else 108)])
    elif mutation == "reverse_sort":
        levels.reverse()
        levels.sort(key=lambda x: x.price, reverse=side.is_bid())
    elif mutation == "price_edit":
        levels[1].price = 105 if side.is_bid() else 101
    elif mutation == "clear":
        levels.clear()
    check_vector(levels, side)
    assert levels._ordered_for(limit(9999, side, 100))
    for i, level in enumerate(levels):
        assert list(
            book._matching_price_levels(levels, limit(9999, side, level.price))
        ) == [(i, level)]


@pytest.mark.parametrize("clone", [deepcopy, lambda x: pickle.loads(pickle.dumps(x))])
@pytest.mark.parametrize("count", [1, 10])
def test_vector_clone_keeps_independent_cache(clone, count):
    book, _ = new_book()
    for i in range(count):
        book._place_order(limit(i, price=100 + i))
    copied = clone(book.asks)
    assert copied._prices == book.asks._prices
    assert copied._prices is not book.asks._prices
    copied.pop(0)
    check_vector(copied, Side.ASK)
    check_vector(book.asks, Side.ASK)
    assert len(book.asks) == count and len(copied) == count - 1

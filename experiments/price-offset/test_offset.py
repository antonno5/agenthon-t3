"""Check offset reuse, compaction, public mutation and logical price positions."""

from copy import deepcopy
import pickle
import weakref
import gc
import pytest
from abides_markets.orders import Side
from test_runtime import new_book, limit
from test_vector import check_vector


def seeded(side, count):
    book, _ = new_book()
    for i in range(count):
        book._place_order(
            limit(i, side, 2000 - 2 * i if side.is_bid() else 1000 + 2 * i)
        )
    return book, book.bids if side.is_bid() else book.asks


def assert_bound(levels, side):
    check_vector(levels, side)
    assert len(levels._prices) <= 2 * len(levels) + 63
    if not levels:
        assert levels._prices == [] and levels._prices_start == 0


@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_head_keys_are_retained_and_prefix_slots_reused(side):
    book, levels = seeded(side, 200)
    storage = levels._prices
    keys = storage.copy()
    removed = [levels.pop(0) for _ in range(20)]
    assert levels._prices is storage and storage == keys
    assert levels._prices_start == 20
    assert_bound(levels, side)
    target = limit(9999, side, levels[37].price)
    assert list(book._matching_price_levels(levels, target)) == [(37, levels[37])]
    for level in reversed(removed):
        levels.insert(0, level)
        assert_bound(levels, side)
    assert levels._prices_start == 0 and levels._prices is storage
    assert levels._prices == keys


@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_middle_tail_and_slice_changes_with_nonzero_offset(side):
    book, levels = seeded(side, 200)
    for _ in range(20):
        del levels[0]
    for i in [12, -1, -7, 0]:
        del levels[i]
        assert_bound(levels, side)
    del levels[2::3]
    assert_bound(levels, side)
    for i, level in enumerate(levels):
        assert list(
            book._matching_price_levels(levels, limit(9999, side, level.price))
        ) == [(i, level)]
    levels.reverse()
    assert not levels._ordered_for(limit(9999, side, 1000))
    levels.sort(key=lambda x: x.price, reverse=side.is_bid())
    assert_bound(levels, side)


@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_compaction_boundary_and_sustained_removal_bound(side):
    _, levels = seeded(side, 128)
    for _ in range(63):
        levels.pop(0)
        assert_bound(levels, side)
    assert levels._prices_start == 63
    old_storage = levels._prices
    levels.pop(0)
    assert levels._prices_start == 0 and levels._prices is not old_storage
    assert len(levels._prices) == 64
    while levels:
        levels.pop(0)
        assert_bound(levels, side)


@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_tail_removals_also_bound_a_large_discarded_prefix(side):
    _, levels = seeded(side, 300)
    for _ in range(100):
        levels.pop(0)
    assert levels._prices_start == 100
    while levels:
        levels.pop()
        assert_bound(levels, side)


@pytest.mark.parametrize("clone", [deepcopy, lambda x: pickle.loads(pickle.dumps(x))])
@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_nonzero_offset_clone_and_public_price_edit(side, clone):
    _, levels = seeded(side, 100)
    for _ in range(10):
        levels.pop(0)
    copied = clone(levels)
    assert copied._prices is not levels._prices
    assert_bound(copied, side)
    copied.pop(0)
    assert_bound(copied, side)
    assert len(levels) == 90 and len(copied) == 89
    levels[0].price += 1 if side.is_bid() else -1
    assert_bound(levels, side)
    assert levels._prices_start == 0


def test_discarded_keys_do_not_retain_removed_levels():
    _, levels = seeded(Side.ASK, 200)
    level = levels[0]
    ref = weakref.ref(level)
    del levels[0]
    del level
    gc.collect()
    assert ref() is None
    assert levels._prices_start == 1

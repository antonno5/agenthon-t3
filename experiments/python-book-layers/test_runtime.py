"""Exercise the installed Python layers against real pinned ABIDES book code."""

from copy import deepcopy
from enum import Enum
import importlib.util
import os
from pathlib import Path
import pickle
import random
import sys
import warnings

import numpy as np
import pytest

from abides_core import Message
from abides_markets.matching.facade import OrderBook as LayeredBook
from abides_markets.matching.price_level import PriceLevel as LayeredLevel
from abides_markets.order_book import OrderBook
from abides_markets.orders import LimitOrder, MarketOrder, Side
from abides_markets.price_level import PriceLevel


def load_original(filename, class_name):
    directory = Path(os.environ["BOOK_LAYERS_CONTROL_SOURCE"])
    name = "abides_markets._layers_control_" + filename.removesuffix(".py")
    spec = importlib.util.spec_from_file_location(name, directory / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name), module


@pytest.fixture(scope="module")
def original_book():
    original_level, _ = load_original("price_level.py", "PriceLevel")
    original, module = load_original("order_book.py", "OrderBook")
    module.PriceLevel = original_level
    return original


def freeze(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.ndarray):
        return (str(value.dtype), value.shape, freeze(value.tolist()))
    if isinstance(value, np.generic):
        return freeze(value.item())
    if isinstance(value, dict):
        return {k: freeze(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [freeze(v) for v in value]
    if hasattr(value, "__dict__"):
        return (type(value).__name__, freeze(vars(value)))
    return value


class Owner:
    def __init__(self, stp=None):
        self.mkt_open = 0
        self.current_time = 0
        self.book_logging = True
        self.book_log_depth = 10
        self.stp_policy = stp
        self.messages = []
        self.events = []
        self.callbacks = []

    def send_message(self, recipient, message):
        self.messages.append((recipient, message))
        self.callbacks.append(
            (
                "send",
                recipient,
                freeze(message),
                self.book.get_l2_bid_data(),
                self.book.get_l2_ask_data(),
            )
        )

    def logEvent(self, *args):
        self.events.append(deepcopy(args))
        self.callbacks.append(("log", freeze(args)))


def new_book(cls=OrderBook, stp=None):
    owner = Owner(stp)
    book = cls(owner, "X")
    owner.book = book
    return book, owner


def limit(order_id, side=Side.ASK, price=100, quantity=5, agent=1, **kwargs):
    return LimitOrder(agent, 0, "X", quantity, side, price, order_id=order_id, **kwargs)


def snapshot(book, owner):
    positions = {}
    for side in ("bids", "asks"):
        for level_index, level in enumerate(getattr(book, side)):
            for queue in ("visible_orders", "hidden_orders"):
                for index, (order, _) in enumerate(getattr(level, queue)):
                    positions[id(order)] = (side, level_index, queue, index)
    links = []
    for side in ("bids", "asks"):
        for level in getattr(book, side):
            for queue in (level.visible_orders, level.hidden_orders):
                for _, metadata in queue:
                    if "ptc_other_half" in metadata:
                        links.append(positions.get(id(metadata["ptc_other_half"])))
    return freeze(
        {
            "state": {k: v for k, v in vars(book).items() if k != "owner"},
            "links": links,
            "messages": owner.messages,
            "events": owner.events,
            "callbacks": owner.callbacks,
            "l2_bid": book.get_l2_bid_data(),
            "l2_ask": book.get_l2_ask_data(),
            "l3_bid": book.get_l3_bid_data(),
            "l3_ask": book.get_l3_ask_data(),
            "imbalance": book.get_imbalance(),
            "volume": book.get_transacted_volume(),
            "l1_history": book.get_L1_snapshots(),
            "l2_history": book.get_L2_snapshots(3),
        }
    )


def test_import_identity_and_pickle():
    assert OrderBook is LayeredBook
    assert PriceLevel is LayeredLevel
    book, _ = new_book()
    book.handle_limit_order(limit(1))
    clone = pickle.loads(pickle.dumps(book))
    assert type(clone) is OrderBook
    assert type(clone.asks[0]) is PriceLevel
    assert clone.owner.book is clone
    assert clone.get_l2_ask_data() == [(100, 5)]
    copied = deepcopy(book)
    assert copied.owner.book is copied
    assert copied.asks is not book.asks


def test_callbacks_observe_each_intermediate_fill():
    book, owner = new_book()
    book.handle_limit_order(limit(10, quantity=5))
    book.handle_limit_order(limit(11, quantity=8))
    owner.callbacks.clear()
    book.handle_limit_order(limit(12, Side.BID, 101, 12, agent=2))
    sends = [c for c in owner.callbacks if c[0] == "send"]
    assert [c[1] for c in sends] == [1, 2, 1, 2]
    assert [c[4] for c in sends] == [[(100, 8)], [(100, 8)], [(100, 1)], [(100, 1)]]
    assert [row["asks"].tolist() for row in book.book_log2[-2:]] == [
        [[100, 8]],
        [[100, 1]],
    ]


def test_subclass_dispatch_and_public_list_assignment():
    class CustomBook(OrderBook):
        def execute_order(self, order):
            self.executions = getattr(self, "executions", 0) + 1
            return super().execute_order(order)

        def get_l2_ask_data(self, depth=sys.maxsize):
            self.queries = getattr(self, "queries", 0) + 1
            return super().get_l2_ask_data(depth)

    book, _ = new_book(CustomBook)
    asks = []
    book.asks = asks
    book.handle_limit_order(limit(1))
    assert book.asks is asks
    assert book.executions == 1
    assert book.queries > 0


def test_visible_priority_over_earlier_hidden():
    book, owner = new_book()
    book.handle_limit_order(limit(1, is_hidden=True))
    book.handle_limit_order(limit(2))
    book.handle_limit_order(limit(3, Side.BID, agent=2))
    executions = [
        m.order.order_id for _, m in owner.messages if m.type() == "OrderExecutedMsg"
    ]
    assert executions == [2, 3]
    assert book.asks[0].hidden_orders[0][0].order_id == 1


def apply(book, name, args, kwargs):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = getattr(book, name)(*deepcopy(args), **deepcopy(kwargs))
            outcome = ("return", freeze(result))
        except Exception as error:
            outcome = ("raise", type(error).__name__, str(error))
    return outcome, [(type(w.message).__name__, str(w.message)) for w in caught]


@pytest.mark.parametrize("stp", [None, "cancel_newest", "cancel_oldest"])
@pytest.mark.parametrize("seed", [17, 491, 914])
def test_seeded_commands_match_original_after_every_operation(original_book, stp, seed):
    baseline, old_owner = new_book(original_book, stp)
    candidate, new_owner = new_book(OrderBook, stp)
    rng = random.Random(seed)
    for step in range(300):
        old_owner.current_time = new_owner.current_time = step * 1000
        resting = [
            o
            for levels in (baseline.bids, baseline.asks)
            for level in levels
            for queue in (level.visible_orders, level.hidden_orders)
            for o, _ in queue
        ]
        choice = rng.randrange(7) if resting else 0
        args, kwargs = [], {}
        if choice in (0, 1):
            name = "handle_limit_order"
            args = [
                limit(
                    rng.randrange(1, 80),
                    rng.choice([Side.BID, Side.ASK]),
                    rng.randrange(96, 105),
                    rng.randrange(1, 15),
                    rng.randrange(1, 4),
                    is_hidden=rng.random() < 0.15,
                    is_price_to_comply=rng.random() < 0.08,
                    insert_by_id=rng.random() < 0.1,
                    is_post_only=rng.random() < 0.1,
                    tag={"step": step},
                )
            ]
            kwargs = {"quiet": rng.random() < 0.1}
        elif choice == 2:
            name = "handle_market_order"
            args = [
                MarketOrder(
                    rng.randrange(1, 4),
                    step * 1000,
                    "X",
                    rng.randrange(1, 20),
                    rng.choice([Side.BID, Side.ASK]),
                    order_id=1000 + step,
                )
            ]
        else:
            selected = deepcopy(rng.choice(resting))
            if choice == 3:
                name, args = "cancel_order", [selected]
                if rng.random() < 0.2:
                    selected.limit_price += 50
                kwargs = {"quiet": rng.random() < 0.2}
            elif choice == 4:
                replacement = deepcopy(selected)
                replacement.quantity = rng.randrange(0, 20)
                name, args = "modify_order", [selected, replacement]
            elif choice == 5:
                name, args = (
                    "partial_cancel_order",
                    [selected, rng.randrange(0, selected.quantity + 2)],
                )
            else:
                replacement = limit(
                    1000 + step,
                    selected.side,
                    rng.randrange(96, 105),
                    rng.randrange(1, 15),
                    selected.agent_id,
                )
                name, args = "replace_order", [selected.agent_id, selected, replacement]
        counter = Message._Message__message_id_counter
        old_result = apply(baseline, name, args, kwargs)
        after_old = Message._Message__message_id_counter
        Message._Message__message_id_counter = counter
        new_result = apply(candidate, name, args, kwargs)
        assert Message._Message__message_id_counter == after_old
        assert old_result == new_result, (step, name)
        assert snapshot(baseline, old_owner) == snapshot(candidate, new_owner), (
            step,
            name,
        )


def test_duplicate_ids_and_priority_changes_match_original(original_book):
    baseline, old_owner = new_book(original_book)
    candidate, new_owner = new_book()
    operations = [
        ("handle_limit_order", [limit(7, quantity=5)], {}),
        ("handle_limit_order", [limit(8, quantity=5)], {}),
        ("handle_limit_order", [limit(7, quantity=9, is_hidden=True)], {}),
        ("modify_order", [limit(7), limit(7, quantity=8)], {}),
        ("partial_cancel_order", [limit(8), 2], {}),
        ("cancel_order", [limit(7)], {}),
        ("handle_limit_order", [limit(20, Side.BID, quantity=20, agent=2)], {}),
    ]
    for name, args, kwargs in operations:
        counter = Message._Message__message_id_counter
        old_result = apply(baseline, name, args, kwargs)
        after_old = Message._Message__message_id_counter
        Message._Message__message_id_counter = counter
        assert apply(candidate, name, args, kwargs) == old_result
        assert Message._Message__message_id_counter == after_old
        assert snapshot(candidate, new_owner) == snapshot(baseline, old_owner)


def test_duplicate_public_levels_keep_lifecycle_traversal(original_book):
    baseline, old_owner = new_book(original_book)
    candidate, new_owner = new_book()
    old_level = sys.modules[original_book.__module__].PriceLevel
    baseline.asks = [old_level([(limit(7), {})]), old_level([(limit(7), {})])]
    supplied = [PriceLevel([(limit(7), {})]), PriceLevel([(limit(7), {})])]
    candidate.asks = supplied
    for name, args in [
        ("modify_order", [limit(7), limit(7, quantity=3)]),
        ("cancel_order", [limit(7)]),
    ]:
        counter = Message._Message__message_id_counter
        old_result = apply(baseline, name, args, {})
        after_old = Message._Message__message_id_counter
        Message._Message__message_id_counter = counter
        assert apply(candidate, name, args, {}) == old_result
        assert Message._Message__message_id_counter == after_old
        assert snapshot(candidate, new_owner) == snapshot(baseline, old_owner)
        assert candidate.asks is supplied


def test_public_level_list_edits_remain_observable(original_book):
    baseline, old_owner = new_book(original_book)
    candidate, new_owner = new_book()
    old_level = sys.modules[original_book.__module__].PriceLevel
    for book, level_class in [(baseline, old_level), (candidate, PriceLevel)]:
        book.asks.append(level_class([(limit(1, price=100), {})]))
        book.asks.insert(0, level_class([(limit(2, price=99), {})]))
        book.asks[1:] = [level_class([(limit(3, price=101), {})])]
    counter = Message._Message__message_id_counter
    old_result = apply(baseline, "cancel_order", [limit(3, price=101)], {})
    after_old = Message._Message__message_id_counter
    Message._Message__message_id_counter = counter
    assert apply(candidate, "cancel_order", [limit(3, price=101)], {}) == old_result
    assert Message._Message__message_id_counter == after_old
    assert snapshot(candidate, new_owner) == snapshot(baseline, old_owner)


@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_bisect_search_and_insertion_read_logarithmic_number_of_prices(
    side, monkeypatch
):
    from abides_markets.matching.state import _PriceLevels

    book, _ = new_book()
    prices = range(4096, 0, -2) if side.is_bid() else range(2, 4098, 2)
    for order_id, price in enumerate(prices):
        book._place_order(limit(order_id, side, price))
    levels = book.bids if side.is_bid() else book.asks
    calls = []
    original_key = _PriceLevels._key

    def counted_key(self, level):
        calls.append(level.price)
        return original_key(self, level)

    monkeypatch.setattr(_PriceLevels, "_key", counted_key)
    target = limit(9000, side, 2048)
    assert [
        (i, level.price) for i, level in book._matching_price_levels(levels, target)
    ] == [(1024 if side.is_bid() else 1023, 2048)]
    assert len(calls) <= 12
    calls.clear()
    book._place_order(target)
    assert len(calls) <= 12
    calls.clear()
    book._place_order(limit(9001, side, 2049))
    assert len(calls) <= 16
    assert [level.price for level in levels] == sorted(
        [*prices, 2049], reverse=side.is_bid()
    )
    # The newly inserted level and its neighbors remain certified; no next-read scan.
    calls.clear()
    assert len(list(book._matching_price_levels(levels, target))) == 1
    assert len(calls) <= 12
    calls.clear()
    assert list(book._matching_price_levels(levels, limit(9002, side, 2051))) == []
    assert len(calls) <= 12


def assert_same_operation(baseline, candidate, name, args, kwargs=None):
    counter = Message._Message__message_id_counter
    old_result = apply(baseline, name, args, kwargs or {})
    after_old = Message._Message__message_id_counter
    Message._Message__message_id_counter = counter
    assert apply(candidate, name, args, kwargs or {}) == old_result
    assert Message._Message__message_id_counter == after_old
    assert snapshot(candidate, candidate.owner) == snapshot(baseline, baseline.owner)


@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
@pytest.mark.parametrize(
    "edit",
    [
        "append",
        "insert",
        "slice",
        "delete",
        "pop",
        "remove",
        "reverse",
        "sort",
        "extend",
        "iadd",
        "imul",
        "clear",
        "price",
        "side",
    ],
)
def test_managed_public_mutations_match_original(original_book, side, edit):
    baseline, _ = new_book(original_book)
    candidate, _ = new_book()
    old_level = sys.modules[original_book.__module__].PriceLevel
    prices = [104, 102, 100] if side.is_bid() else [100, 102, 104]
    for order_id, price in enumerate(prices, 1):
        assert_same_operation(
            baseline, candidate, "enter_order", [limit(order_id, side, price)]
        )
    for book, level_class in [(baseline, old_level), (candidate, PriceLevel)]:
        levels = book.bids if side.is_bid() else book.asks

        def extra():
            return level_class([(limit(7, side, 102), {})])

        if edit == "append":
            levels.append(extra())
        elif edit == "insert":
            levels.insert(0, extra())
        elif edit == "slice":
            levels[1:] = [extra(), extra()]
        elif edit == "delete":
            del levels[::2]
        elif edit == "pop":
            levels.pop(0)
        elif edit == "remove":
            levels.remove(levels[0])
        elif edit == "reverse":
            levels.reverse()
        elif edit == "sort":
            levels.sort(key=lambda level: level.price, reverse=side.is_ask())
        elif edit == "extend":
            levels.extend([extra(), extra()])
        elif edit == "iadd":
            levels += [extra(), extra()]
        elif edit == "imul":
            levels *= 2
        elif edit == "clear":
            levels.clear()
        elif edit == "price":
            levels[0].price = 102
        elif edit == "side":
            levels[0].side = Side.ASK if side.is_bid() else Side.BID
    # Existing-level lookup, insertion and duplicate cancellation after each edit.
    for name, args in [
        ("modify_order", [limit(7, side, 102), limit(7, side, 102, quantity=8)]),
        ("enter_order", [limit(8, side, 101)]),
        ("cancel_order", [limit(7, side, 102)]),
    ]:
        assert_same_operation(baseline, candidate, name, args)


@pytest.mark.parametrize(
    "clone", [deepcopy, lambda book: pickle.loads(pickle.dumps(book))]
)
def test_bisect_clones_preserve_domain_state_and_mutations(original_book, clone):
    baseline, _ = new_book(original_book)
    candidate, _ = new_book()
    for side in (Side.BID, Side.ASK):
        for order_id, price in enumerate([100, 103, 101, 102]):
            assert_same_operation(
                baseline, candidate, "enter_order", [limit(order_id, side, price)]
            )
    candidate = clone(candidate)
    assert set(vars(candidate)) == set(vars(baseline))
    for side in (Side.BID, Side.ASK):
        levels = candidate.bids if side.is_bid() else candidate.asks
        levels.reverse()
        old_levels = baseline.bids if side.is_bid() else baseline.asks
        old_levels.reverse()
        assert_same_operation(
            baseline, candidate, "enter_order", [limit(10, side, 102)]
        )
        assert_same_operation(
            baseline, candidate, "cancel_order", [limit(2, side, 101)]
        )


def test_custom_price_level_dispatch_remains_linear(original_book):
    baseline, _ = new_book(original_book)
    candidate, _ = new_book()
    old_level = sys.modules[original_book.__module__].PriceLevel

    def customized(base):
        class CustomLevel(base):
            def order_has_equal_price(self, order):
                # Nonlocal matching semantics must be dispatched for every level.
                return order.limit_price == 999 or super().order_has_equal_price(order)

        return CustomLevel

    for book, base in [(baseline, old_level), (candidate, PriceLevel)]:
        custom = customized(base)
        book.asks.extend(
            [custom([(limit(7, price=100), {})]), custom([(limit(7, price=102), {})])]
        )
    assert_same_operation(
        baseline,
        candidate,
        "modify_order",
        [limit(7, price=999), limit(7, price=999, quantity=8)],
    )


def test_callback_reordering_during_duplicate_traversal_matches_original(original_book):
    baseline, _ = new_book(original_book)
    candidate, _ = new_book()
    old_level = sys.modules[original_book.__module__].PriceLevel
    for book, level_class in [(baseline, old_level), (candidate, PriceLevel)]:
        book.asks.extend(
            [
                level_class([(limit(7, price=100), {})]),
                level_class([(limit(8, price=100), {})]),
                level_class([(limit(7, price=100), {})]),
            ]
        )
        send = book.owner.send_message

        def mutate(recipient, message, book=book, send=send):
            send(recipient, message)
            book.asks[1].price = 101

        book.owner.send_message = mutate
    assert_same_operation(
        baseline, candidate, "modify_order", [limit(7), limit(7, quantity=8)]
    )


def test_sorted_public_edit_is_revalidated_once_and_deletion_keeps_certificate(
    monkeypatch,
):
    from abides_markets.matching.state import _PriceLevels

    book, _ = new_book()
    for price in range(512):
        book._place_order(limit(price, price=price))
    book.asks.reverse()
    book.asks.sort(key=lambda level: level.price)
    calls = []
    original_key = _PriceLevels._key

    def counted_key(self, level):
        calls.append(level.price)
        return original_key(self, level)

    monkeypatch.setattr(_PriceLevels, "_key", counted_key)
    target = limit(256, price=256)
    assert list(book._matching_price_levels(book.asks, target))[0][0] == 256
    assert len(calls) >= 512  # Public mutation needs one ordering check.
    calls.clear()
    assert book._remove_order_from_level(book.asks, 256, target.order_id) is not None
    assert list(book._matching_price_levels(book.asks, target)) == []
    assert len(calls) <= 10
    calls.clear()
    target = limit(257, price=257)
    assert list(book._matching_price_levels(book.asks, target))[0][0] == 256
    assert len(calls) <= 10


@pytest.mark.parametrize("field", ["price", "side"])
def test_deleted_level_fields_preserve_original_exception_order(original_book, field):
    baseline, _ = new_book(original_book)
    candidate, _ = new_book()
    for price in [100, 102, 104]:
        assert_same_operation(
            baseline, candidate, "enter_order", [limit(price, price=price)]
        )
    # Certify the candidate before the public edit; deleting a later field must
    # not make modify fail before updating the first matching level's quantity.
    assert list(candidate._matching_price_levels(candidate.asks, limit(100)))
    for book in (baseline, candidate):
        delattr(book.asks[-1], field)
    counter = Message._Message__message_id_counter
    old_result = apply(
        baseline, "modify_order", [limit(100), limit(100, quantity=8)], {}
    )
    after_old = Message._Message__message_id_counter
    Message._Message__message_id_counter = counter
    assert (
        apply(candidate, "modify_order", [limit(100), limit(100, quantity=8)], {})
        == old_result
    )
    assert Message._Message__message_id_counter == after_old
    assert old_result[0][0] == "raise"
    # Snapshot queries can also raise on a missing price; compare complete domain
    # state and journals directly, without querying the malformed book again.
    assert freeze({k: v for k, v in vars(candidate).items() if k != "owner"}) == freeze(
        {k: v for k, v in vars(baseline).items() if k != "owner"}
    )
    assert freeze(candidate.owner.messages) == freeze(baseline.owner.messages)
    assert freeze(candidate.owner.callbacks) == freeze(baseline.owner.callbacks)


@pytest.mark.parametrize(
    "comparator",
    ["order_has_equal_price", "order_has_better_price", "order_has_worse_price"],
)
def test_instance_comparator_override_and_removal_match_original(
    original_book, comparator
):
    baseline, _ = new_book(original_book)
    candidate, _ = new_book()
    for price in [100, 102, 104]:
        assert_same_operation(
            baseline, candidate, "enter_order", [limit(7, price=price)]
        )
    assert list(candidate._matching_price_levels(candidate.asks, limit(7, price=102)))
    for book in (baseline, candidate):
        setattr(book.asks[0], comparator, lambda order: True)
    if comparator == "order_has_equal_price":
        assert_same_operation(
            baseline,
            candidate,
            "modify_order",
            [limit(7, price=102), limit(7, price=102, quantity=8)],
        )
    else:
        assert_same_operation(baseline, candidate, "enter_order", [limit(9, price=103)])
    for book in (baseline, candidate):
        # An override that forced insertion may no longer be on the first level.
        for level in book.asks:
            if comparator in vars(level):
                delattr(level, comparator)
    assert_same_operation(baseline, candidate, "cancel_order", [limit(7, price=102)])

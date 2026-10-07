# Copyright (c) 2021, J.P. Morgan Chase. All rights reserved.
# Derived from pinned ABIDES f9cbe51342b7dedd9587e4e069040d68a5c6477f.
# Distributed under the BSD 3-Clause license in LICENSE.abides.

"""State initialization; retains the original public attributes and list storage."""

from bisect import bisect_left
from typing import Any, Dict, List, Optional, Set, Tuple
from abides_core import Agent, NanosecondTime
from ..orders import LimitOrder, Side
from .price_level import PriceLevel


class _PriceLevels(list):
    """Numeric search keys with a reusable discarded prefix and bounded storage.

    Best-level removal advances the active start instead of shifting key entries.
    Public reorderings and price edits retain the certified-vector fallback.
    """

    def __init__(self, side):
        super().__init__()
        self._side = side
        self._dirty = False
        self._ordered = True
        self._revision = PriceLevel._price_revision
        self._length = 0
        self._prices = []
        self._prices_start = 0

    def _key(self, level):
        return -level.price if self._side.is_bid() else level.price

    def _eligible_level(self, level):
        if type(level) is not PriceLevel:
            return False
        fields = vars(level)
        return (
            type(fields.get("price")) is int  # noqa: E721
            and fields.get("side") == self._side
            and "order_has_equal_price" not in fields
            and "order_has_better_price" not in fields
            and "order_has_worse_price" not in fields
        )

    def _ordered_for(self, order):
        if (
            self._dirty
            or self._revision != PriceLevel._price_revision
            or self._length != len(self)
        ):
            self._ordered = True
            prices = []
            previous = None
            for level in self:
                if not self._eligible_level(level):
                    self._ordered = False
                    break
                key = self._key(level)
                if previous is not None and key < previous:
                    self._ordered = False
                    break
                prices.append(key)
                previous = key
            self._prices = prices if self._ordered else []
            self._prices_start = 0
            self._dirty = False
            self._revision = PriceLevel._price_revision
            self._length = len(self)
        return (
            self._ordered
            and order.side == self._side
            and type(order.limit_price) is int  # noqa: E721
        )

    def _position(self, order):
        # Only called after _ordered_for has certified the vector and order.
        key = -order.limit_price if self._side.is_bid() else order.limit_price
        start = self._prices_start
        if start == len(self._prices) or key <= self._prices[start]:
            return 0
        return bisect_left(self._prices, key, start + 1) - start

    def _inserted(self, index):
        # Pickle/deepcopy can append before restoring the container attributes.
        if (
            getattr(self, "_dirty", True)
            or self._revision != PriceLevel._price_revision
            or not self._ordered
            or len(self._prices) - self._prices_start != len(self) - 1
        ):
            self._dirty = True
            return
        level = self[index]
        if not self._eligible_level(level):
            self._dirty = True
        else:
            key = self._key(level)
            absolute = self._prices_start + index
            if (index > 0 and self._prices[absolute - 1] > key) or (
                absolute < len(self._prices) and key > self._prices[absolute]
            ):
                self._dirty = True
            elif index == 0 and self._prices_start:
                self._prices_start -= 1
                self._prices[self._prices_start] = key
            else:
                self._prices.insert(absolute, key)
        self._length = len(self)

    def append(self, level):
        super().append(level)
        self._inserted(len(self) - 1)

    def insert(self, index, level):
        length = len(self)
        super().insert(index, level)
        self._inserted(max(0, length + index) if index < 0 else min(index, length))

    def _remove_key(self, index):
        if not self:
            self._prices = []
            self._prices_start = 0
            return
        if index == 0:
            self._prices_start += 1
        else:
            del self._prices[self._prices_start + index]
        start = self._prices_start
        # At most twice the live count plus 63 discarded integer keys remain.
        # Compaction work is amortized over preceding removals, not every search.
        if start >= 64 and start >= len(self):
            self._prices = self._prices[start:]
            self._prices_start = 0

    def __delitem__(self, index):
        length = len(self)
        super().__delitem__(index)
        if (
            self._ordered
            and not self._dirty
            and self._revision == PriceLevel._price_revision
            and type(index) is int  # noqa: E721
        ):
            self._remove_key(index if index >= 0 else length + index)
        else:
            # Arbitrary public slices/custom index objects are revalidated once.
            self._dirty = True
        self._length = len(self)

    def pop(self, index=-1):
        length = len(self)
        result = super().pop(index)
        if (
            self._ordered
            and not self._dirty
            and self._revision == PriceLevel._price_revision
            and type(index) is int  # noqa: E721
        ):
            self._remove_key(index if index >= 0 else length + index)
        else:
            self._dirty = True
        self._length = len(self)
        return result

    def remove(self, level):
        # Public remove uses equality rather than a certified numeric position.
        super().remove(level)
        self._dirty = True
        self._length = len(self)

    def clear(self):
        super().clear()
        self._prices = []
        self._prices_start = 0
        self._dirty = False
        self._ordered = True
        self._revision = PriceLevel._price_revision
        self._length = 0

    def __setitem__(self, index, value):
        self._dirty = True
        return super().__setitem__(index, value)

    def extend(self, levels):
        self._dirty = True
        return super().extend(levels)

    def __iadd__(self, levels):
        self._dirty = True
        return super().__iadd__(levels)

    def __imul__(self, count):
        self._dirty = True
        return super().__imul__(count)

    def reverse(self):
        self._dirty = True
        return super().reverse()

    def sort(self, *args, **kwargs):
        self._dirty = True
        return super().sort(*args, **kwargs)


class OrderBookState:
    def __init__(self, owner: Agent, symbol: str) -> None:
        """Creates a new OrderBook class instance for a single symbol.

        Arguments:
            owner: The agent this order book belongs to, usually an `ExchangeAgent`.
            symbol: The symbol of the stock or security that is traded on this order book.
        """
        self.owner: Agent = owner
        self.symbol: str = symbol
        self.bids: List[PriceLevel] = _PriceLevels(Side.BID)
        self.asks: List[PriceLevel] = _PriceLevels(Side.ASK)
        self.last_trade: Optional[int] = None

        # Create an empty list of dictionaries to log the full order book depth (price and volume) each time it changes.
        self.book_log2: List[Dict[str, Any]] = []
        self.quotes_seen: Set[int] = set()

        # Create an order history for the exchange to report to certain agent types.
        self.history: List[Dict[str, Any]] = []

        self.last_update_ts: Optional[NanosecondTime] = self.owner.mkt_open

        self.buy_transactions: List[Tuple[NanosecondTime, int]] = []
        self.sell_transactions: List[Tuple[NanosecondTime, int]] = []

    def _matching_price_levels(self, book, order):
        """Find the first price in logarithmic time; retain live duplicate traversal."""
        if type(book) is _PriceLevels and book._ordered_for(order):
            index = book._position(order)
            # Do not precompute a range: cancellation can delete a yielded level.
            # Advancing the live index reproduces enumerate's duplicate behavior.
            while index < len(book):
                if not book._ordered_for(order):
                    # A lifecycle callback may reorder or change a level between
                    # yields. Continue the original live scan from its next index.
                    for next_index, level in enumerate(book):
                        if next_index >= index and level.order_has_equal_price(order):
                            yield next_index, level
                    return
                if not book[index].order_has_equal_price(order):
                    return
                yield index, book[index]
                index += 1
            return
        for index, level in enumerate(book):
            if level.order_has_equal_price(order):
                yield index, level

    def _insert_price_level(self, book, index, level):
        """Use list mutation hooks without adding book-level state."""
        if index == len(book):
            book.append(level)
        else:
            book.insert(index, level)

    def _remove_empty_level(self, book, index):
        """Remove an empty level at the original point in each lifecycle."""
        if book[index].is_empty:
            del book[index]
            return True
        return False

    def _remove_order_from_level(self, book, index, order_id):
        """Remove the first matching record and then its empty level."""
        result = book[index].remove_order(order_id)
        if result is not None:
            self._remove_empty_level(book, index)
        return result

    def _place_order(self, order: LimitOrder, metadata=None):
        book = self.bids if order.side.is_bid() else self.asks

        if len(book) == 0:
            # There were no orders on this side of the book.
            self._insert_price_level(
                book, len(book), PriceLevel([(order, metadata or {})])
            )
        elif book[-1].order_has_worse_price(order):
            # There were orders on this side, but this order is worse than all of them.
            # (New lowest bid or highest ask.)
            self._insert_price_level(
                book, len(book), PriceLevel([(order, metadata or {})])
            )
        elif type(book) is _PriceLevels and book._ordered_for(order):
            index = book._position(order)
            if index < len(book) and book[index].order_has_equal_price(order):
                book[index].add_order(order, metadata or {})
            elif index < len(book):
                self._insert_price_level(
                    book, index, PriceLevel([(order, metadata or {})])
                )
        else:
            # There are orders on this side.  Insert this order in the correct position in the list.
            # Note that o is a LIST of all orders (oldest at index 0) at this same price.
            for i, price_level in enumerate(book):
                if price_level.order_has_better_price(order):
                    self._insert_price_level(
                        book, i, PriceLevel([(order, metadata or {})])
                    )
                    break
                elif price_level.order_has_equal_price(order):
                    book[i].add_order(order, metadata or {})
                    break

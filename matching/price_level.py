# Copyright (c) 2021, J.P. Morgan Chase. All rights reserved.
# Derived from pinned ABIDES f9cbe51342b7dedd9587e4e069040d68a5c6477f.
# Distributed under the BSD 3-Clause license in LICENSE.abides.

from typing import Dict, List, Optional, Tuple

from ..orders import LimitOrder, Side


class PriceLevel:
    """
    A class that represents a single price level containing multiple orders for one
    side of an order book. The option to have hidden orders is supported. This class
    abstracts the complextity of handling both visible and hidden orders away from
    the parent order book.

    Visible orders are consumed first, followed by any hidden orders.

    Attributes:
        visible_orders: A list of visible orders, where the order with index=0 is first
            in the queue and will be exexcuted first.
        hidden_orders: A list of hidden orders, where the order with index=0 is first
            in the queue and will be exexcuted first.
        price: The price this PriceLevel represents.
        side: The side of the market this PriceLevel represents.
    """

    # Shared invalidation epoch, outside every level and book's domain state.
    # Public price/side edits and instance comparator overrides change the epoch.
    _price_revision = 0

    def __setattr__(self, name, value):
        if (name in ("price", "side") and name in self.__dict__) or name in (
            "order_has_equal_price",
            "order_has_better_price",
            "order_has_worse_price",
        ):
            PriceLevel._price_revision += 1
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if (
            name
            in (
                "price",
                "side",
                "order_has_equal_price",
                "order_has_better_price",
                "order_has_worse_price",
            )
            and name in self.__dict__
        ):
            PriceLevel._price_revision += 1
        object.__delattr__(self, name)

    def __init__(self, orders: List[Tuple[LimitOrder, Dict]]) -> None:
        """
        Arguments:
            orders: A list of orders, containing both visible and hidden orders that
                will be correctly allocated on initialisation. At least one order must
                be given.
        """
        if len(orders) == 0:
            raise ValueError(
                "At least one LimitOrder must be given when initialising a PriceLevel."
            )

        self.visible_orders: List[Tuple[LimitOrder, Dict]] = []
        self.hidden_orders: List[Tuple[LimitOrder, Dict]] = []

        self.price: int = orders[0][0].limit_price
        self.side: Side = orders[0][0].side

        for order, metadata in orders:
            self.add_order(order, metadata)

    def add_order(self, order: LimitOrder, metadata: Optional[Dict] = None) -> None:
        """
        Adds an order to the correct queue in the price level.

        Orders are added to the back of their respective queue.

        Arguments:
            order: The `LimitOrder` to add, can be visible or hidden.
            metadata: Optional dict of metadata values to associate with the order.
        """

        if order.is_hidden:
            self.hidden_orders.append((order, metadata or {}))
        elif order.insert_by_id:
            insert_index = 0
            for order2, _ in self.visible_orders:
                if order2.order_id > order.order_id:
                    break
                insert_index += 1
            self.visible_orders.insert(insert_index, (order, metadata or {}))
        else:
            self.visible_orders.append((order, metadata or {}))

    def update_order_quantity(self, order_id: int, new_quantity: int) -> bool:
        """
        Updates the quantity of an order.

        The new_quantity must be greater than 0. To remove an order from the price
        level use the `remove_order` method instead.

        If the new quantity is less than or equal to the current quantity the order's
        position in its respective queue will be maintained.

        If the new quantity is more than the current quantity the order will be moved
        to the back of its respective queue.

        Arguments:
            order_id: The ID of the order to update.
            quantity: The new quantity to update with.

        Returns:
            True if the update was sucessful, False if a matching order with the
            given ID could not be found or if the new quantity given is 0.
        """
        if new_quantity == 0:
            return False
        location = self._find_order(order_id)
        if location is None:
            return False
        queue, index = location
        order, _ = queue[index]
        if new_quantity <= order.quantity:
            self._set_order_quantity(order, new_quantity)
        else:
            self._move_to_tail(queue, index, new_quantity)
        return True

    def remove_order(self, order_id: int) -> Optional[Tuple[LimitOrder, Dict]]:
        """
        Attempts to remove an order from the price level.

        Arguments:
            order_id: The ID of the order to remove.

        Returns:
            The order object if the order was found and removed, else None.
        """
        location = self._find_order(order_id)
        if location is None:
            return None
        return self._remove_at(*location)

    def peek(self) -> Tuple[LimitOrder, Dict]:
        """
        Returns the highest priority order in the price level. Visible orders are returned first,
        followed by hidden orders if no visible order exist.

        Raises a ValueError exception if the price level has no orders.
        """
        if len(self.visible_orders) > 0:
            return self.visible_orders[0]
        elif len(self.hidden_orders) > 0:
            return self.hidden_orders[0]
        else:
            raise ValueError(
                "Can't peek at LimitOrder in PriceLevel as it contains no orders"
            )

    def pop(self) -> Tuple[LimitOrder, Dict]:
        """
        Removes the highest priority order in the price level and returns it. Visible
        orders are returned first, followed by hidden orders if no visible order exist.

        Raises a ValueError exception if the price level has no orders.
        """
        if len(self.visible_orders) > 0:
            return self._remove_at(self.visible_orders, 0)
        elif len(self.hidden_orders) > 0:
            return self._remove_at(self.hidden_orders, 0)
        else:
            raise ValueError(
                "Can't pop LimitOrder from PriceLevel as it contains no orders"
            )

    def _find_order(self, order_id):
        """Visible records precede hidden records, including duplicate IDs."""
        for queue in (self.visible_orders, self.hidden_orders):
            for index, (order, _) in enumerate(queue):
                if order.order_id == order_id:
                    return queue, index
        return None

    @staticmethod
    def _remove_at(queue, index):
        return queue.pop(index)

    @staticmethod
    def _set_order_quantity(order, quantity):
        # No new validation: retain legacy zero/negative and PTC behavior.
        order.quantity = quantity

    def _move_to_tail(self, queue, index, quantity):
        entry = self._remove_at(queue, index)
        self._set_order_quantity(entry[0], quantity)
        queue.append(entry)

    def order_is_match(self, order: LimitOrder) -> bool:
        """
        Checks if an order on the opposite side of the book is a match with this price
        level.

        The given order must be a `LimitOrder`.

        Arguments:
            order: The order to compare.

        Returns:
            True if the order is a match.
        """
        if order.side == self.side:
            raise ValueError("Attempted to compare order on wrong side of book")

        if (
            order.side.is_bid()
            and (order.limit_price >= self.price)
            and (not (order.is_post_only and self.total_quantity == 0))
        ):
            return True

        if (
            order.side.is_ask()
            and (order.limit_price <= self.price)
            and (not (order.is_post_only and self.total_quantity == 0))
        ):
            return True

        return False

    def order_has_better_price(self, order: LimitOrder) -> bool:
        """
        Checks if an order on this side of the book has a better price than this price
        level.

        Arguments:
            order: The order to compare.

        Returns:
            True if the given order has a better price.
        """
        if order.side != self.side:
            raise ValueError("Attempted to compare order on wrong side of book")

        if order.side.is_bid() and (order.limit_price > self.price):
            return True

        if order.side.is_ask() and (order.limit_price < self.price):
            return True

        return False

    def order_has_worse_price(self, order: LimitOrder) -> bool:
        """
        Checks if an order on this side of the book has a worse price than this price
        level.

        Arguments:
            order: The order to compare.

        Returns:
            True if the given order has a worse price.
        """
        if order.side != self.side:
            raise ValueError("Attempted to compare order on wrong side of book")

        if order.side.is_bid() and (order.limit_price < self.price):
            return True

        if order.side.is_ask() and (order.limit_price > self.price):
            return True

        return False

    def order_has_equal_price(self, order: LimitOrder) -> bool:
        """
        Checks if an order on this side of the book has an equal price to this price
        level.

        Arguments:
            order: The order to compare.

        Returns:
            True if the given order has an equal price.
        """
        if order.side != self.side:
            raise ValueError("Attempted to compare order on wrong side of book")

        return order.limit_price == self.price

    @property
    def total_quantity(self) -> int:
        """
        Returns the total visible order quantity of this price level.
        """
        return sum(order.quantity for order, _ in self.visible_orders)

    @property
    def is_empty(self) -> bool:
        """
        Returns True if this price level has no orders.
        """
        return len(self.visible_orders) == 0 and len(self.hidden_orders) == 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PriceLevel):
            raise NotImplementedError

        return (
            self.visible_orders == other.visible_orders
            and self.hidden_orders == other.hidden_orders
        )


PriceLevel.__module__ = "abides_markets.price_level"

# ruff: noqa: E712
# Keep the exact pinned comparisons; this extraction does not change semantics.
# Copyright (c) 2021, J.P. Morgan Chase. All rights reserved.
# Derived from pinned ABIDES f9cbe51342b7dedd9587e4e069040d68a5c6477f.
# Distributed under the BSD 3-Clause license in LICENSE.abides.

"""Compatible OrderBook combining state, matching and queries with lifecycle methods."""

import logging
from copy import deepcopy
from typing import Dict, Optional
import numpy as np
from ..messages.orderbook import (
    OrderCancelledMsg,
    OrderPartialCancelledMsg,
    OrderModifiedMsg,
    OrderReplacedMsg,
)
from ..orders import LimitOrder
from .state import OrderBookState
from .matcher import Matching
from .queries import BookQueries

logger = logging.getLogger("abides_markets.order_book")


class OrderBook(OrderBookState, Matching, BookQueries):
    """Basic class for an order book for one symbol, in the style of the major US Stock Exchanges.

    An OrderBook requires an owning agent object, which it will use to send messages
    outbound via the simulator Kernel (notifications of order creation, rejection,
    cancellation, execution, etc).

    Attributes:
        owner: The agent this order book belongs to.
        symbol: The symbol of the stock or security that is traded on this order book.
        bids: List of bid price levels (index zero is best bid), stored as a PriceLevel object.
        asks: List of ask price levels (index zero is best ask), stored as a PriceLevel object.
        last_trade: The price that the last trade was made at.
        book_log: Log of the full order book depth (price and volume) each time it changes.
        book_log2: TODO
        quotes_seen: TODO
        history: A truncated history of previous trades.
        last_update_ts: The last timestamp the order book was updated.
        buy_transactions: An ordered list of all previous buy transaction timestamps and quantities.
        sell_transactions: An ordered list of all previous sell transaction timestamps and quantities.
    """

    def enter_order(
        self,
        order: LimitOrder,
        metadata: Optional[Dict] = None,
        quiet: bool = False,  ###!! originally true
    ) -> None:
        """Enters a limit order into the OrderBook in the appropriate location.

        This does not test for matching/executing orders -- this function
        should only be called after a failed match/execution attempt.

        Arguments:
            order: The limit order to enter into the order book.
            quiet: If True messages will not be sent to agents and entries will not be added to
                history. Used when this function is a part of a more complex order.
        """

        if order.is_price_to_comply and (
            (metadata is None) or (metadata == {}) or ("ptc_hidden" not in metadata)
        ):
            hidden_order = deepcopy(order)
            visible_order = deepcopy(order)

            hidden_order.is_hidden = True

            # Adjust price of displayed order to one tick away from the center of the market
            hidden_order.limit_price += 1 if order.side.is_bid() else -1

            hidden_order_metadata = dict(
                ptc_hidden=True,
                ptc_other_half=visible_order,
            )

            visible_order_metadata = dict(
                ptc_hidden=False,
                ptc_other_half=hidden_order,
            )

            self.enter_order(hidden_order, hidden_order_metadata, quiet=True)
            self.enter_order(visible_order, visible_order_metadata, quiet=quiet)
            return

        self._place_order(order, metadata)

        if quiet == False:
            self.history.append(
                dict(
                    time=self.owner.current_time,
                    type="LIMIT",
                    order_id=order.order_id,
                    agent_id=order.agent_id,
                    side=order.side.value,
                    quantity=order.quantity,
                    price=order.limit_price,
                )
            )

        if (self.owner.book_logging == True) and (quiet == False):
            # append current OB state to book_log2
            self.append_book_log2()

    def cancel_order(
        self,
        order: LimitOrder,
        tag: str = None,
        cancellation_metadata: Optional[Dict] = None,
        quiet: bool = False,
    ) -> bool:
        """Attempts to cancel (the remaining, unexecuted portion of) a trade in the order book.

        By definition, this pretty much has to be a limit order.  If the order cannot be found
        in the order book (probably because it was already fully executed), presently there is
        no message back to the agent.  This should possibly change to some kind of failed
        cancellation message.  (?)  Otherwise, the agent receives ORDER_CANCELLED with the
        order as the message body, with the cancelled quantity correctly represented as the
        number of shares that had not already been executed.

        Arguments:
            order: The limit order to cancel from the order book.
            quiet: If True messages will not be sent to agents and entries will not be added to
                history. Used when this function is a part of a more complex order.

        Returns:
            A bool indicating if the order cancellation was successful.
        """

        book = self.bids if order.side.is_bid() else self.asks

        # If there are no orders on this side of the book, there is nothing to do.
        if not book:
            return False

        # There are orders on this side.  Find the price level of the order to cancel,
        # then find the exact order and cancel it.
        for i, price_level in self._matching_price_levels(book, order):
            # cancelled_order, metadata = (lambda x: x if x!=None else (None,None))(price_level.remove_order(order.order_id))
            cancelled_order_result = self._remove_order_from_level(
                book, i, order.order_id
            )

            if cancelled_order_result is not None:
                cancelled_order, metadata = cancelled_order_result

                logger.debug("CANCELLED: order {}", order)
                logger.debug(
                    "SENT: notifications of order cancellation to agent {} for order {}",
                    cancelled_order.agent_id,
                    cancelled_order.order_id,
                )

                if cancelled_order.is_price_to_comply:
                    self.cancel_order(metadata["ptc_other_half"], quiet=True)

                if not quiet:
                    self.history.append(
                        dict(
                            time=self.owner.current_time,
                            type="CANCEL",
                            order_id=cancelled_order.order_id,
                            tag=tag,
                            metadata=cancellation_metadata
                            if tag == "auctionFill"
                            else None,
                        )
                    )

                    self.owner.send_message(
                        order.agent_id, OrderCancelledMsg(cancelled_order)
                    )

                # We found the order and cancelled it, so stop looking.
                self.last_update_ts = self.owner.current_time

                if (self.owner.book_logging == True) and (quiet == False):
                    ### append current OB state to book_log2
                    self.append_book_log2()

                return True

        return False

    def modify_order(self, order: LimitOrder, new_order: LimitOrder) -> None:
        """Modifies the quantity of an existing limit order in the order book.

        Arguments:
            order: The existing order in the order book.
            new_order: The new order to replace the old order with.
        """

        if order.order_id != new_order.order_id:
            return

        book = self.bids if order.side.is_bid() else self.asks

        for _, price_level in self._matching_price_levels(book, order):
            if price_level.update_order_quantity(order.order_id, new_order.quantity):
                self.history.append(
                    dict(
                        time=self.owner.current_time,
                        type="MODIFY",
                        order_id=order.order_id,
                        new_side=order.side.value,
                        new_quantity=new_order.quantity,
                    )
                )

                logger.debug("MODIFIED: order {}", order)
                logger.debug(
                    "SENT: notifications of order modification to agent {} for order {}",
                    new_order.agent_id,
                    new_order.order_id,
                )
                self.owner.send_message(order.agent_id, OrderModifiedMsg(new_order))

                self.last_update_ts = self.owner.current_time

                if self.owner.book_logging == True is not None:
                    # append current OB state to book_log2
                    self.append_book_log2()

    def partial_cancel_order(
        self,
        order: LimitOrder,
        quantity: int,
        tag: str = None,
        cancellation_metadata: Optional[Dict] = None,
    ) -> None:
        """cancel a part of the quantity of an existing limit order in the order book.

        Arguments:
            order: The existing order in the order book.
            new_order: The new order to replace the old order with.
        """

        if order.order_id == 19653081:
            print("inside OB partialCancel")
        book = self.bids if order.side.is_bid() else self.asks

        new_order = deepcopy(order)
        new_order.quantity -= quantity

        for _, price_level in self._matching_price_levels(book, order):
            if price_level.update_order_quantity(order.order_id, new_order.quantity):
                self.history.append(
                    dict(
                        time=self.owner.current_time,
                        type="CANCEL_PARTIAL",
                        order_id=order.order_id,
                        quantity=quantity,
                        tag=tag,
                        metadata=cancellation_metadata
                        if tag == "auctionFill"
                        else None,
                    )
                )

                logger.debug("CANCEL_PARTIAL: order {}", order)
                logger.debug(
                    "SENT: notifications of order partial cancellation to agent {} for order {}",
                    new_order.agent_id,
                    quantity,
                )
                self.owner.send_message(
                    order.agent_id, OrderPartialCancelledMsg(new_order)
                )

                self.last_update_ts = self.owner.current_time

                if self.owner.book_logging == True:
                    ### append current OB state to book_log2
                    self.append_book_log2()

    def replace_order(
        self,
        agent_id: int,
        old_order: LimitOrder,
        new_order: LimitOrder,
    ) -> None:
        """Removes an order from the book and replaces it with a new one in one step.

        This is equivalent to calling cancel_order followed by handle_limit_order.

        If the old order cannot be cancelled, the new order is not inserted.

        Arguments:
            agent_id: The ID of the agent making this request - this must be the ID of
                the agent who initially created the order.
            old_order: The existing order in the order book to be cancelled.
            new_order: The new order to be inserted into the order book.
        """

        if self.cancel_order(old_order, quiet=True) == True:
            self.history.append(
                dict(
                    time=self.owner.current_time,
                    type="REPLACE",
                    old_order_id=old_order.order_id,
                    new_order_id=new_order.order_id,
                    quantity=new_order.quantity,
                    price=new_order.limit_price,
                )
            )

            self.handle_limit_order(new_order, quiet=True)

            logger.debug(
                "SENT: notifications of order replacement to agent {agent_id} for old order {old_order.order_id}, new order {new_order.order_id}"
            )

            self.owner.send_message(agent_id, OrderReplacedMsg(old_order, new_order))

        if self.owner.book_logging == True:
            # append current OB state to book_log2
            self.append_book_log2()

    def append_book_log2(self):
        row = {
            "QuoteTime": self.owner.current_time,
            "bids": np.array(self.get_l2_bid_data(depth=self.owner.book_log_depth)),
            "asks": np.array(self.get_l2_ask_data(depth=self.owner.book_log_depth)),
        }
        # if (row["bids"][0][0]>=row["asks"][0][0]): print("WARNING: THIS IS A REAL PROBLEM: an order book contains bids and asks at the same quote price!")
        self.book_log2.append(row)


OrderBook.__module__ = "abides_markets.order_book"

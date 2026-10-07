# ruff: noqa: E712
# Keep the exact pinned comparisons; this extraction does not change semantics.
# Copyright (c) 2021, J.P. Morgan Chase. All rights reserved.
# Derived from pinned ABIDES f9cbe51342b7dedd9587e4e069040d68a5c6477f.
# Distributed under the BSD 3-Clause license in LICENSE.abides.

"""Matching methods, including the original ordered callbacks and STP handling."""

import logging
import warnings
from copy import deepcopy
from typing import List, Optional, Tuple
from ..messages.orderbook import OrderAcceptedMsg, OrderExecutedMsg, OrderCancelledMsg
from ..orders import LimitOrder, MarketOrder, Order

logger = logging.getLogger("abides_markets.order_book")


class Matching:
    def handle_limit_order(self, order: LimitOrder, quiet: bool = False) -> None:
        """Matches a limit order or adds it to the order book.

        Handles partial matches piecewise,
        consuming all possible shares at the best price before moving on, without regard to
        order size "fit" or minimizing number of transactions.  Sends one notification per
        match.

        Arguments:
            order: The limit order to process.
            quiet: If True messages will not be sent to agents and entries will not be added to
                history. Used when this function is a part of a more complex order.
        """

        if order.symbol != self.symbol:
            warnings.warn(
                f"{order.symbol} order discarded. Does not match OrderBook symbol: {self.symbol}"
            )
            return

        if (order.quantity <= 0) or (int(order.quantity) != order.quantity):
            warnings.warn(
                f"{order.symbol} order discarded. Quantity ({order.quantity}) must be a positive integer."
            )
            return

        if (order.limit_price < 0) or (int(order.limit_price) != order.limit_price):
            warnings.warn(
                f"{order.symbol} order discarded. Limit price ({order.limit_price}) must be a positive integer."
            )
            return

        executed: List[Tuple[int, int]] = []

        while True:
            # Self-trade prevention (opt-in via ExchangeAgent.stp_policy; None = legacy no-op).
            # Prevents an agent from matching its own resting order at the best crossable level.
            stp_policy = getattr(self.owner, "stp_policy", None)
            if stp_policy:
                opp = self.asks if order.side.is_bid() else self.bids
                if opp and opp[0].order_is_match(order):
                    resting = opp[0].peek()[0]
                    if resting.agent_id == order.agent_id:
                        if stp_policy == "cancel_oldest" and self.cancel_order(
                            resting, quiet=quiet
                        ):
                            # Cancel the resting same-agent order; re-attempt against the next level.
                            continue
                        if stp_policy != "cancel_oldest":
                            # cancel_newest (default): cancel the incoming aggressor's remainder.
                            if not quiet:
                                self.owner.send_message(
                                    order.agent_id, OrderCancelledMsg(deepcopy(order))
                                )
                            break

            matched_order = self.execute_order(order)

            if matched_order is not None:
                # Accumulate the volume and average share price of the currently executing inbound trade.
                assert matched_order.fill_price is not None
                executed.append((matched_order.quantity, matched_order.fill_price))

                if order.quantity <= 0:
                    break

            else:
                # No matching order was found, so the new order enters the order book.  Notify the agent.
                self.enter_order(deepcopy(order), quiet=quiet)

                logger.debug("ACCEPTED: new order {}", order)
                logger.debug(
                    "SENT: notifications of order acceptance to agent {} for order {}",
                    order.agent_id,
                    order.order_id,
                )

                if not quiet:
                    self.owner.send_message(order.agent_id, OrderAcceptedMsg(order))

                break

        # Now that we are done executing or accepting this order, log the new best bid and ask.
        if self.bids:
            self.owner.logEvent(
                "BEST_BID",
                "{},{},{}".format(
                    self.symbol, self.bids[0].price, self.bids[0].total_quantity
                ),
            )

        if self.asks:
            self.owner.logEvent(
                "BEST_ASK",
                "{},{},{}".format(
                    self.symbol, self.asks[0].price, self.asks[0].total_quantity
                ),
            )

        # Also log the last trade (total share quantity, average share price).
        if len(executed) > 0:
            trade_qty = 0
            trade_price = 0
            for q, p in executed:
                logger.debug("Executed: {} @ {}", q, p)
                trade_qty += q
                trade_price += p * q

            avg_price = int(round(trade_price / trade_qty))
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Avg: {trade_qty} @ ${avg_price:0.4f}")
            self.owner.logEvent("LAST_TRADE", f"{trade_qty},${avg_price:0.4f}")

            self.last_trade = avg_price

    def handle_market_order(self, order: MarketOrder) -> None:
        """Takes a market order and attempts to fill at the current best market price.

        Arguments:
            order: The market order to process.
        """

        if order.symbol != self.symbol:
            warnings.warn(
                f"{order.symbol} order discarded. Does not match OrderBook symbol: {self.symbol}"
            )

            return

        if (order.quantity <= 0) or (int(order.quantity) != order.quantity):
            warnings.warn(
                f"{order.symbol} order discarded.  Quantity ({order.quantity}) must be a positive integer."
            )
            return

        order = deepcopy(order)

        while order.quantity > 0:
            # Self-trade prevention (opt-in; see handle_limit_order). Market orders match any resting
            # order, so only the same-agent check at the best level is needed.
            stp_policy = getattr(self.owner, "stp_policy", None)
            if stp_policy:
                opp = self.asks if order.side.is_bid() else self.bids
                if opp and opp[0].peek()[0].agent_id == order.agent_id:
                    if stp_policy == "cancel_oldest" and self.cancel_order(
                        opp[0].peek()[0]
                    ):
                        continue
                    if stp_policy != "cancel_oldest":
                        self.owner.send_message(
                            order.agent_id, OrderCancelledMsg(deepcopy(order))
                        )
                        break

            if self.execute_order(order) is None:
                break

    def execute_order(self, order: Order) -> Optional[Order]:
        """Finds a single best match for this order, without regard for quantity.

        Returns the matched order or None if no match found.  DOES remove,
        or decrement quantity from, the matched order from the order book
        (i.e. executes at least a partial trade, if possible).

        Arguments:
            order: The order to execute.
        """
        # Track which (if any) existing order was matched with the current order.
        book = self.asks if order.side.is_bid() else self.bids

        # First, examine the correct side of the order book for a match.
        if len(book) == 0:
            # No orders on this side.
            return None
        elif isinstance(order, LimitOrder) and not book[0].order_is_match(order):
            # There were orders on the right side, but the prices do not overlap.
            # Or: bid could not match with best ask, or vice versa.
            # Or: bid offer is below the lowest asking price, or vice versa.
            return None
        elif order.tag in ["MR_preprocess_ADD", "MR_preprocess_REPLACE"]:
            # if an order enters here it means it was going to execute at entry
            # but instead it was caught by MR_preprocess_add
            self.owner.logEvent(order.tag + "_POST_ONLY", {"order_id": order.order_id})
            return None
        else:
            # There are orders on the right side, and the new order's price does fall
            # somewhere within them.  We can/will only match against the oldest order
            # among those with the best price.  (i.e. best price, then FIFO)

            # The matched order might be only partially filled. (i.e. new order is smaller)
            is_ptc_exec = False
            if order.quantity >= book[0].peek()[0].quantity:
                # Consume entire matched order.
                matched_order, matched_order_metadata = book[0].pop()

                # If the order is a part of a price to comply pair, also remove the other
                # half of the order from the book.
                if matched_order.is_price_to_comply:
                    is_ptc_exec = True
                    if matched_order_metadata["ptc_hidden"] == False:
                        raise Exception(
                            "Should not be executing on the visible half of a price to comply order!"
                        )

                    assert (
                        self._remove_order_from_level(book, 1, matched_order.order_id)
                        is not None
                    )

                # If the matched price now has no orders, remove it completely.
                self._remove_empty_level(book, 0)
            else:
                # Consume only part of matched order.
                book_order, book_order_metadata = book[0].peek()

                matched_order = deepcopy(book_order)
                matched_order.quantity = order.quantity

                book[0]._set_order_quantity(
                    book_order, book_order.quantity - matched_order.quantity
                )

                # If the order is a part of a price to comply pair, also adjust the
                # quantity of the other half of the pair.
                if book_order.is_price_to_comply:
                    is_ptc_exec = True
                    if book_order_metadata["ptc_hidden"] == False:
                        raise Exception(
                            "Should not be executing on the visible half of a price to comply order!"
                        )

                    other_half = book_order_metadata["ptc_other_half"]
                    book[0]._set_order_quantity(
                        other_half, other_half.quantity - matched_order.quantity
                    )

            # When two limit orders are matched, they execute at the price that
            # was being "advertised" in the order book.
            matched_order.fill_price = matched_order.limit_price

            if order.side.is_bid():
                self.buy_transactions.append(
                    (self.owner.current_time, matched_order.quantity)
                )
            else:
                self.sell_transactions.append(
                    (self.owner.current_time, matched_order.quantity)
                )

            self.history.append(
                dict(
                    time=self.owner.current_time,
                    type="EXEC",
                    order_id=matched_order.order_id,
                    agent_id=matched_order.agent_id,
                    oppos_order_id=order.order_id,
                    oppos_agent_id=order.agent_id,
                    side="SELL"
                    if order.side.is_bid()
                    else "BUY",  # by def exec if from point of view of passive order being exec
                    quantity=matched_order.quantity,
                    price=matched_order.limit_price if is_ptc_exec else None,
                )
            )

            filled_order = deepcopy(order)
            filled_order.quantity = matched_order.quantity
            filled_order.fill_price = matched_order.fill_price

            order.quantity -= filled_order.quantity

            logger.debug(
                "MATCHED: new order {} vs old order {}", filled_order, matched_order
            )
            logger.debug(
                "SENT: notifications of order execution to agents {} and {} for orders {} and {}",
                filled_order.agent_id,
                matched_order.agent_id,
                filled_order.order_id,
                matched_order.order_id,
            )

            self.owner.send_message(
                matched_order.agent_id, OrderExecutedMsg(matched_order)
            )
            self.owner.send_message(order.agent_id, OrderExecutedMsg(filled_order))

            if self.owner.book_logging == True:
                # append current OB state to book_log2
                self.append_book_log2()

            # Return (only the executed portion of) the matched order.
            return matched_order

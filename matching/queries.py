# ruff: noqa: E713
# Keep the exact pinned comparisons; this extraction does not change semantics.
# Copyright (c) 2021, J.P. Morgan Chase. All rights reserved.
# Derived from pinned ABIDES f9cbe51342b7dedd9587e4e069040d68a5c6477f.
# Distributed under the BSD 3-Clause license in LICENSE.abides.

"""Read methods and exports; preserves original snapshots and edge cases."""

import sys
from typing import List, Optional, Tuple
import numpy as np
import pandas as pd
from abides_core.utils import str_to_ns, ns_date
from ..orders import Side


class BookQueries:
    def get_l1_bid_data(self) -> Optional[Tuple[int, int]]:
        """Returns the current best bid price and of the book and the volume at this price."""

        if len(self.bids) == 0:
            return None
        index = 0
        while not self.bids[index].total_quantity > 0:
            index += 1
        return self.bids[0].price, self.bids[0].total_quantity

    def get_l1_ask_data(self) -> Optional[Tuple[int, int]]:
        """Returns the current best ask price of the book and the volume at this price."""

        if len(self.asks) == 0:
            return None
        index = 0
        while not self.asks[index].total_quantity > 0:
            index += 1
        return self.asks[index].price, self.asks[index].total_quantity

    def get_l2_bid_data(self, depth: int = sys.maxsize) -> List[Tuple[int, int]]:
        """Returns the price and total quantity of all limit orders on the bid side.

        Arguments:
            depth: If given, will only return data for the first N levels of the order book side.

        Returns:
            A list of tuples where the first element of the tuple is the price and the second
            element of the tuple is the total volume at that price.

            The list is given in order of price, with the centre of the book first.
        """

        return list(
            filter(
                lambda x: x[1] > 0,
                [
                    (price_level.price, price_level.total_quantity)
                    for price_level in self.bids[:depth]
                ],
            )
        )

    def get_l2_ask_data(self, depth: int = sys.maxsize) -> List[Tuple[int, int]]:
        """Returns the price and total quantity of all limit orders on the ask side.

        Arguments:
            depth: If given, will only return data for the first N levels of the order book side.

        Returns:
            A list of tuples where the first element of the tuple is the price and the second
            element of the tuple is the total volume at that price.

            The list is given in order of price, with the centre of the book first.
        """

        return list(
            filter(
                lambda x: x[1] > 0,
                [
                    (price_level.price, price_level.total_quantity)
                    for price_level in self.asks[:depth]
                ],
            )
        )

    def get_l3_bid_data(self, depth: int = sys.maxsize) -> List[Tuple[int, List[int]]]:
        """Returns the price and quantity of all limit orders on the bid side.

        Arguments:
            depth: If given, will only return data for the first N levels of the order book side.

        Returns:
            A list of tuples where the first element of the tuple is the price and the second
            element of the tuple is the list of order quantities at that price.

            The list of order quantities is given in order of priority and the overall list
            is given in order of price, with the centre of the book first.
        """

        return [
            (
                price_level.price,
                [order.quantity for order, _ in price_level.visible_orders],
            )
            for price_level in self.bids[:depth]
        ]

    def get_l3_ask_data(self, depth: int = sys.maxsize) -> List[Tuple[int, List[int]]]:
        """Returns the price and quantity of all limit orders on the ask side.

        Arguments:
            depth: If given, will only return data for the first N levels of the order book side.

        Returns:
            A list of tuples where the first element of the tuple is the price and the second
            element of the tuple is the list of order quantities at that price.

            The list of order quantities is given in order of priority and the overall list
            is given in order of price, with the centre of the book first.
        """

        return [
            (
                price_level.price,
                [order.quantity for order, _ in price_level.visible_orders],
            )
            for price_level in self.asks[:depth]
        ]

    def get_transacted_volume(self, lookback_period: str = "10min") -> Tuple[int, int]:
        """Method retrieves the total transacted volume for a symbol over a lookback
        period finishing at the current simulation time.

        Arguments:
            lookback_period: The period in time from the current time to calculate the
                transacted volume for.
        """

        window_start = self.owner.current_time - str_to_ns(lookback_period)

        buy_transacted_volume = 0
        sell_transacted_volume = 0

        for time, volume in reversed(self.buy_transactions):
            if time < window_start:
                break

            buy_transacted_volume += volume

        for time, volume in reversed(self.sell_transactions):
            if time < window_start:
                break

            sell_transacted_volume += volume

        return (buy_transacted_volume, sell_transacted_volume)

    def get_imbalance(self) -> Tuple[float, Optional[Side]]:
        """Returns a measure of book side total volume imbalance.

        Returns:
            A tuple containing the volume imbalance value and the side the order
            book is in imbalance to.

        Examples:
            - Both book sides have the exact same volume    --> (0.0, None)
            - 2x bid volume vs. ask volume                  --> (0.5, Side.BID)
            - 2x ask volume vs. bid volume                  --> (0.5, Side.ASK)
            - Ask has no volume                             --> (1.0, Side.BID)
            - Bid has no volume                             --> (1.0, Side.ASK)
        """
        bid_vol = sum(price_level.total_quantity for price_level in self.bids)
        ask_vol = sum(price_level.total_quantity for price_level in self.asks)

        if bid_vol == ask_vol:
            return (0, None)

        elif bid_vol == 0:
            return (1.0, Side.ASK)

        elif ask_vol == 0:
            return (1.0, Side.BID)

        elif bid_vol < ask_vol:
            return (1 - bid_vol / ask_vol, Side.ASK)

        else:
            return (1 - ask_vol / bid_vol, Side.BID)

    def get_L1_snapshots(self):
        best_bids = []
        best_asks = []

        def safe_first(x):
            return x[0] if len(x) > 0 else np.array([None, None])

        for d in self.book_log2:
            best_bids.append([d["QuoteTime"]] + safe_first(d["bids"]).tolist())
            best_asks.append([d["QuoteTime"]] + safe_first(d["asks"]).tolist())
        best_bids = np.array(best_bids)
        best_asks = np.array(best_asks)
        return {"best_bids": best_bids, "best_asks": best_asks}

    def bids_padding(self, book, nlevels):
        n = book.shape[0]
        if n == 0:
            return np.zeros((nlevels, 2), dtype=int)
        if n >= nlevels:
            return book[:nlevels, :]
        else:
            lowestprice = book[-1, 0] if len(book.shape) == 2 else book[0]
            npad = nlevels - n
            pad = np.transpose(
                np.array(
                    [
                        -1 + np.arange(lowestprice, lowestprice - npad, -1, dtype=int),
                        np.zeros(npad, dtype=int),
                    ]
                )
            )
            if len(pad.shape) == 1:
                pad = pad.reshape(1, 2)
            return np.concatenate([book, pad])

    def asks_padding(self, book, nlevels):
        n = book.shape[0]
        if n == 0:
            return np.zeros((nlevels, 2), dtype=int)
        if n >= nlevels:
            return book[:nlevels, :]
        else:
            highestprice = book[-1, 0] if len(book.shape) == 2 else book[0]
            npad = nlevels - n
            pad = np.transpose(
                np.array(
                    [
                        1 + np.arange(highestprice, highestprice + npad, 1, dtype=int),
                        np.zeros(npad, dtype=int),
                    ]
                )
            )
            if len(pad.shape) == 1:
                pad = pad.reshape(1, 2)
            return np.concatenate([book, pad])

    def get_L2_snapshots(self, nlevels):
        times, bids, asks = [], [], []
        for x in self.book_log2:
            times.append(x["QuoteTime"])
            bids.append(self.bids_padding(x["bids"], nlevels))
            asks.append(self.asks_padding(x["asks"], nlevels))
        bids = np.array(bids)
        asks = np.array(asks)
        times = np.array(times)
        return {"times": times, "bids": bids, "asks": asks}

    def get_l3_itch(self):
        history_l3 = pd.DataFrame(self.history)
        history_l3.loc[history_l3.tag == "auctionFill", "type"] = "EXEC"
        history_l3.loc[history_l3.tag == "auctionFill", "quantity"] = history_l3.loc[
            history_l3.tag == "auctionFill", "metadata"
        ].apply(lambda x: x["quantity"])
        history_l3.loc[history_l3.tag == "auctionFill", "price"] = history_l3.loc[
            history_l3.tag == "auctionFill", "metadata"
        ].apply(lambda x: x["price"])

        history_l3["printable"] = np.nan
        history_l3["stock"] = np.nan
        if not "REPLACE" in history_l3.type.unique():
            history_l3["new_order_id"] = np.nan
            history_l3["old_order_id"] = np.nan

        history_l3.loc[history_l3.type == "REPLACE", "order_id"] = history_l3.loc[
            history_l3.type == "REPLACE", "old_order_id"
        ]

        history_l3.loc[history_l3.type == "EXEC", "side"] = np.nan

        history_l3["type"] = history_l3["type"].replace(
            {
                "LIMIT": "ADD",
                "CANCEL_PARTIAL": "CANCEL",
                "CANCEL": "DELETE",
                "EXEC": "EXECUTE",
                # "MODIFY":"CANCEL"### not 100% sure, there might be actual order modifications
            }
        )
        history_l3["side"] = history_l3["side"].replace({"ASK": "S", "BID": "B"})
        history_l3["time"] = history_l3["time"] - ns_date(history_l3["time"])
        history_l3["price"] = history_l3["price"] * 100

        # history_l3 = history_l3.drop(["old_order_id","oppos_order_id","agent_id","oppos_agent_id","tag"],axis=1)
        history_l3 = history_l3[
            [
                "time",
                "stock",
                "type",
                "order_id",
                "side",
                "quantity",
                "price",
                "new_order_id",
                "printable",
            ]
        ]
        history_l3 = history_l3.rename(
            columns={
                "time": "timestamp",
                "order_id": "reference",
                "new_order_id": "new_reference",
                "quantity": "shares",
            }
        )
        return history_l3

    def pretty_print(self, silent: bool = True) -> Optional[str]:
        """Print a nicely-formatted view of the current order book.

        Arguments:
            silent:
        """

        # Start at the highest ask price and move down.  Then switch to the highest bid price and move down.
        # Show the total volume at each price.  If silent is True, return the accumulated string and print nothing.

        assert self.last_trade is not None

        book = "{} order book as of {}\n".format(self.symbol, self.owner.current_time)
        book += "Last trades: simulated {:d}, historical {:d}\n".format(
            self.last_trade,
            self.owner.oracle.observe_price(
                self.symbol,
                self.owner.current_time,
                sigma_n=0,
                random_state=self.owner.random_state,
            ),
        )

        book += "{:10s}{:10s}{:10s}\n".format("BID", "PRICE", "ASK")
        book += "{:10s}{:10s}{:10s}\n".format("---", "-----", "---")

        for quote, volume in self.get_l2_ask_data()[-1::-1]:
            book += "{:10s}{:10s}{:10s}\n".format(
                "", "{:d}".format(quote), "{:d}".format(volume)
            )

        for quote, volume in self.get_l2_bid_data():
            book += "{:10s}{:10s}{:10s}\n".format(
                "{:d}".format(volume), "{:d}".format(quote), ""
            )

        if silent:
            return book
        else:
            print(book)
            return None

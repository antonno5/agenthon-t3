"""Exact direct-row Python control for attributing the benefit of compilation."""

from operator import index


def dropout_totals(book):
    totals = [0, 0]
    starts = [None, None]
    for row in book:
        now = index(row["QuoteTime"])
        for side, key in enumerate(("bids", "asks")):
            size = len(row[key])
            if size == 0 and starts[side] is None:
                starts[side] = now
            elif size != 0 and starts[side] is not None:
                totals[side] += now - starts[side]
                starts[side] = None
    return tuple(totals)

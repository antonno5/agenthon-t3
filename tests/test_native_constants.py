"""native.py hard-codes config.build_config's clock constants; check they still agree."""
import pandas as pd
from abides_core.utils import str_to_ns

from abides_fork import native
from abides_fork.config import _DATE


def test_clock_constants():
    assert native.DATE_NS == int(pd.to_datetime(_DATE).value)
    assert native.OPEN_OFFSET_NS == str_to_ns("09:30:00")
    assert native.ORACLE_CLOSE_OFFSET_NS == str_to_ns("16:00:00")
    assert native.ONE_SECOND_NS == str_to_ns("1s")


if __name__ == "__main__":
    test_clock_constants()
    print("ok")

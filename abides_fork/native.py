"""Native (C++) execution path for ``simulate``.

``_t3engine`` re-implements, step for step, the ABIDES code path this adapter drives (kernel,
exchange/order book, the four ``agents.py`` traders, the sparse mean-reverting oracle, the
scenario latency model, and ``trace.py``'s extraction), including every numpy RandomState
draw. It produces byte-identical ``trace.parquet`` / ``message_trace.parquet``.

``build_native_config`` maps a scenario with exactly the rules ``config.build_config`` and
the agent constructors apply, and returns ``None`` for anything outside the envelope the
engine has been validated on; ``simulate`` then runs the Python ABIDES path instead. The
engine itself raises on any state the Python reference would have raised on, and
``simulate`` falls back the same way.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from abides_fork.scenario_params import (
    _agent_kwargs,
    _oracle_kappa_per_ns,
    _oracle_megashock_rate_per_ns,
)

try:
    from abides_fork import _t3engine
except ImportError:  # extension not built: always use the Python path
    _t3engine = None

# config.build_config's clock constants, precomputed so this path needs no pandas/ABIDES:
#   pd.to_datetime("20210205").value, str_to_ns("09:30:00"), str_to_ns("16:00:00"),
#   str_to_ns("1s").  tests/test_native_constants.py asserts they still agree.
DATE_NS = 1_612_483_200_000_000_000
OPEN_OFFSET_NS = 34_200_000_000_000
ORACLE_CLOSE_OFFSET_NS = 57_600_000_000_000
ONE_SECOND_NS = 1_000_000_000
DEFAULT_COMPUTATION_DELAY = 50

_KIND = {"NoiseTrader": 0, "MarketMaker": 1, "ValueTrader": 2, "MomentumTrader": 3}
_LATENCY_KIND = {"log_normal": 0, "uniform": 1, "pareto": 2}
_INT64_MAX = 2**63 - 1
# Keep every clock value far from int64 overflow.
_TIME_LIMIT = 2**62


def _finite(*xs: float) -> bool:
    return all(math.isfinite(x) for x in xs)


def _small_int(x: int, lo: int = -(2**40), hi: int = 2**40) -> bool:
    return lo <= x <= hi


def build_native_config(scenario: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Engine config for ``scenario``, or ``None`` if it must run on the Python path."""
    if _t3engine is None:
        return None
    try:
        return _build(scenario)
    except Exception:  # anything the mapping cannot express -> Python path decides
        return None


def _build(scenario: dict[str, Any]) -> Optional[dict[str, Any]]:
    seed = scenario["seed"]
    if type(seed) is not int or not (0 <= seed <= 0xFFFFFFFF):
        return None

    # --- exchange_config (config.build_config) ---
    exchange_cfg = scenario["exchange_config"]
    proto = bool(exchange_cfg.get("protocol_enforcement", False))
    stp_policy = (
        str(exchange_cfg["stp_policy"])
        if proto and exchange_cfg.get("stp_policy")
        else None
    )
    ack_delay = int(exchange_cfg.get("ack_delay_ns", 0)) if proto else 0
    compute_delay = int(exchange_cfg.get("compute_delay_ns", 0)) if proto else 0
    # Kernel.set_agent_compute_delay rejects negatives; keep delays in a sane range.
    if not (0 <= ack_delay <= 10**15 and 0 <= compute_delay <= 10**15):
        return None
    stp = 0 if stp_policy is None else (1 if stp_policy == "cancel_oldest" else 2)

    # --- oracle_config ---
    oracle_params = scenario["oracle_config"].get("params", {})
    reference_price = int(oracle_params.get("initial_price", 100_000))
    horizon_ns = int(scenario["horizon_ns"])
    if not (0 <= reference_price <= 10**12) or not (1 <= horizon_ns <= 10**15):
        return None
    mkt_open = DATE_NS + OPEN_OFFSET_NS
    mkt_close = mkt_open + horizon_ns
    oracle_close = DATE_NS + ORACLE_CLOSE_OFFSET_NS
    kappa = _oracle_kappa_per_ns(oracle_params)
    fund_vol = float(oracle_params.get("sigma", 5e-5))
    lam = _oracle_megashock_rate_per_ns(oracle_params)
    ms_mean = float(oracle_params.get("jump_sigma", 0.0)) or 1000.0
    if not _finite(kappa, fund_vol, lam, ms_mean) or not (kappa > 0 and lam > 0):
        return None
    jumps = []
    if oracle_params.get("scheduled_jump"):
        sj = oracle_params["scheduled_jump"]
        jt = mkt_open + int(sj["time_ns"])
        mag = int(sj["magnitude"])
        if not (abs(jt) < _TIME_LIMIT and _small_int(mag)):
            return None
        jumps.append((jt, mag))

    # --- latency_config (ScenarioLatencyModel); absent -> ABIDES default model (Python) ---
    latency_cfg = scenario.get("latency_config")
    if not latency_cfg:
        return None
    lparams = latency_cfg.get("params", {})
    lmodel = str(latency_cfg.get("model", "deterministic"))
    mean_ns = float(lparams.get("mean_ns", 0.0))
    lsigma = float(lparams.get("sigma", 0.0))
    lmin = float(lparams.get("min_ns", 0.0))
    lmax = float(lparams.get("max_ns", 1e12))
    alpha = float(lparams.get("alpha", 1.5))
    if not _finite(mean_ns, lsigma, lmin, lmax, alpha):
        return None
    kind = _LATENCY_KIND.get(lmodel, 3)
    if kind == 0 and lsigma < 0:  # numpy lognormal rejects sigma < 0
        return None
    if kind == 2 and not alpha > 0:  # numpy pareto rejects a <= 0
        return None
    # Latency is int(round(clip(value, min, max))): keep its range comfortably inside int64.
    if not (-1e15 <= lmin <= 1e15 and -1e15 <= lmax <= 1e15 and -1e15 <= mean_ns <= 1e15):
        return None
    if mean_ns > 0:
        # ScenarioLatencyModel: float(np.log(mean_ns)) -- numpy's log, not math.log, so the
        # value is whatever the Python path computes on this machine.
        import numpy as np

        lmu = float(np.log(mean_ns))
    else:
        lmu = 0.0

    # --- agents (config.build_config + agents.py constructors) ---
    agents = []
    for agent_cfg in scenario["agent_configs"]:
        agent_type = str(agent_cfg["agent_type"])
        if agent_type not in _KIND:
            return None
        params = agent_cfg.get("params", {})
        kw = _agent_kwargs(agent_type, params, reference_price)
        interval = int(max(1, kw["interval_ns"]))  # ScheduledAgent.__init__
        if not interval <= 10**15:
            return None
        if agent_type == "NoiseTrader":
            size_mean = float(kw["order_size_mean"])
            size_std = float(kw["order_size_std"])
            offset = int(kw["price_offset_ticks"])
            ref = int(kw["reference_price"])
            # numpy normal rejects scale < 0; randint(0, offset + 1) needs offset >= 0.
            if not (_finite(size_mean, size_std) and size_std >= 0 and 0 <= offset <= 10**9):
                return None
            if not (abs(size_mean) <= 1e12 and size_std <= 1e12):
                return None
            spec = (0, interval, size_mean, size_std, offset, ref, 0, 0)
        elif agent_type == "MarketMaker":
            spread = int(max(2, kw["spread_ticks"]))
            depth = int(max(1, kw["depth_levels"]))
            size = int(max(1, kw["size_per_level"]))
            ref = int(kw["reference_price"])
            if not (spread <= 10**9 and depth <= 10**4 and size <= 10**12):
                return None
            spec = (1, interval, 0.0, 0.0, spread, depth, size, ref)
        elif agent_type == "ValueTrader":
            size_mean = float(kw["order_size_mean"])
            threshold = int(kw["threshold_ticks"])
            if not (_finite(size_mean) and abs(size_mean) <= 1e12 and _small_int(threshold)):
                return None
            size = int(max(1, round(size_mean)))  # ValueTrader.act
            sigma_n = 1000.0  # ValueTrader default; _agent_kwargs never overrides it
            spec = (2, interval, sigma_n, 0.0, size, threshold, 0, 0)
        else:  # MomentumTrader
            size_mean = float(kw["order_size_mean"])
            threshold = int(kw["threshold_ticks"])
            lookback = int(max(1, kw["lookback"]))
            if not (_finite(size_mean) and abs(size_mean) <= 1e12 and _small_int(threshold)):
                return None
            if lookback > 10**6:
                return None
            size = int(max(1, round(size_mean)))  # MomentumTrader.act
            spec = (3, interval, 0.0, 0.0, size, threshold, lookback, 0)
        count = int(agent_cfg["count"])
        agents.extend([spec] * max(0, count))
    if len(agents) > 200_000:
        return None

    return {
        "seed": seed,
        "start_time": DATE_NS,
        "mkt_open": mkt_open,
        "mkt_close": mkt_close,
        "stop_time": mkt_close + ONE_SECOND_NS,
        "oracle_close": oracle_close,
        "default_delay": DEFAULT_COMPUTATION_DELAY,
        "r_bar": reference_price,
        "kappa": kappa,
        "fund_vol": fund_vol,
        "megashock_lambda_a": lam,
        "megashock_mean": ms_mean,
        "megashock_var": 50000.0,  # sqrt(s["megashock_var"]) of the int 50_000
        "jumps": jumps,
        "pipeline_delay": ack_delay,
        "computation_delay": compute_delay,
        "stp": stp,
        "lat_model": kind,
        "lat_mu": lmu,
        "lat_sigma": lsigma,
        "lat_min": lmin,
        "lat_max": lmax,
        "lat_alpha": alpha,
        "lat_mean": mean_ns,
        "agents": agents,
    }


# Schema metadata pandas' to_parquet(index=False) writes for trace.py's two frames. With no
# index it depends only on column names and dtypes, so it is a constant per file; writing it
# verbatim keeps the parquet output byte-identical to the pandas path (tests compare hashes).
def _pandas_meta(cols: list[tuple[str, str, str]]) -> bytes:
    import json

    return json.dumps(
        {
            "index_columns": [],
            "column_indexes": [],
            "columns": [
                {"name": n, "field_name": n, "pandas_type": pt, "numpy_type": nt, "metadata": None}
                for n, pt, nt in cols
            ],
            "creator": {"library": "pyarrow", "version": "15.0.2"},
            "pandas_version": "1.5.3",
        }
    ).encode()


_TRACE_META = _pandas_meta(
    [
        ("t_ns", "int64", "int64"),
        ("agent_id", "int32", "int32"),
        ("msg_type", "unicode", "string"),
        ("side", "unicode", "string"),
        ("price", "int64", "int64"),
        ("size", "int64", "int64"),
        ("order_id", "int64", "int64"),
    ]
)
_MSG_META = _pandas_meta(
    [
        ("seq", "int64", "int64"),
        ("t_recv_ns", "int64", "int64"),
        ("t_send_ns", "int64", "Int64"),
        ("latency_ns", "int64", "int64"),
        ("src_id", "int32", "int32"),
        ("dst_id", "int32", "int32"),
        ("message_id", "int64", "int64"),
        ("msg_type", "unicode", "string"),
        ("order_id", "int64", "Int64"),
        ("causal_parent", "int64", "Int64"),
    ]
)


def run_and_write(cfg: dict[str, Any], trace_path, msg_path) -> Optional[tuple[int, int, float]]:
    """Run the engine and write both parquet files with pyarrow directly (no pandas import).

    Returns ``(n_events, n_messages, engine_wall_clock_sec)``, or ``None`` -- before writing
    anything -- if the result is a shape the Python path builds differently (empty trace).
    """
    import time

    t0 = time.perf_counter()
    out = _t3engine.run(cfg)
    wall = time.perf_counter() - t0
    n = len(out["t_ns"]) // 8
    if n == 0:
        return None
    k = len(out["m_t_recv"]) // 8

    import pyarrow as pa
    import pyarrow.parquet as pq

    buf = pa.py_buffer

    def num(key: str, typ, rows: int):
        return pa.Array.from_buffers(typ, rows, [None, buf(out[key])])

    def text(key: str, rows: int):
        return pa.Array.from_buffers(
            pa.string(), rows, [None, buf(out[key + "_offsets"]), buf(out[key + "_data"])]
        )

    def nullable(key: str, valid: str, rows: int):
        nulls = out[valid + "_count"]
        return pa.Array.from_buffers(
            pa.int64(), rows, [buf(out[valid]) if nulls else None, buf(out[key])], null_count=nulls
        )

    trace = pa.Table.from_arrays(
        [
            num("t_ns", pa.int64(), n),
            num("agent_id", pa.int32(), n),
            text("msg_type_s", n),
            text("side_s", n),
            num("price", pa.int64(), n),
            num("size", pa.int64(), n),
            num("order_id", pa.int64(), n),
        ],
        schema=pa.schema(
            [
                ("t_ns", pa.int64()),
                ("agent_id", pa.int32()),
                ("msg_type", pa.string()),
                ("side", pa.string()),
                ("price", pa.int64()),
                ("size", pa.int64()),
                ("order_id", pa.int64()),
            ],
            metadata={b"pandas": _TRACE_META},
        ),
    )
    msgs = pa.Table.from_arrays(
        [
            num("m_seq", pa.int64(), k),
            num("m_t_recv", pa.int64(), k),
            nullable("m_t_send", "m_t_send_valid", k),
            num("m_latency", pa.int64(), k),
            num("m_src", pa.int32(), k),
            num("m_dst", pa.int32(), k),
            num("m_message_id", pa.int64(), k),
            text("m_msg_type_s", k),
            nullable("m_order_id", "m_order_id_valid", k),
            nullable("m_causal", "m_causal_valid", k),
        ],
        schema=pa.schema(
            [
                ("seq", pa.int64()),
                ("t_recv_ns", pa.int64()),
                ("t_send_ns", pa.int64()),
                ("latency_ns", pa.int64()),
                ("src_id", pa.int32()),
                ("dst_id", pa.int32()),
                ("message_id", pa.int64()),
                ("msg_type", pa.string()),
                ("order_id", pa.int64()),
                ("causal_parent", pa.int64()),
            ],
            metadata={b"pandas": _MSG_META},
        ),
    )
    # pandas' to_parquet(compression="snappy") is pq.write_table(table, handle, compression=...)
    pq.write_table(trace, str(trace_path), compression="snappy")
    pq.write_table(msgs, str(msg_path), compression="snappy")
    return n, k, wall

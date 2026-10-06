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


_TRACE_MSG_TYPES = (
    "ORDER_SUBMITTED",
    "ORDER_ACCEPTED",
    "ORDER_CANCELLED",
    "PARTIAL_FILL",
    "ORDER_FILLED",
    "QUOTE_UPDATE",
)
_SIDES = ("BID", "ASK")


def run_native(cfg: dict[str, Any]):
    """Run the engine; return ``(trace_df, message_trace_df)`` with trace.py's exact dtypes,
    or ``None`` if the result is a shape the Python path builds differently (empty trace)."""
    import numpy as np
    import pandas as pd

    from abides_fork.trace import MESSAGE_TRACE_COLUMNS, TRACE_COLUMNS, _MSG_DTYPES, _TRACE_DTYPES

    out = _t3engine.run(cfg)
    n = len(out["t_ns"]) // 8
    if n == 0:
        return None
    fb = np.frombuffer

    def strings(codes: bytes, names: tuple) -> Any:
        return pd.array(np.array(names, dtype=object)[fb(codes, dtype=np.uint8)], dtype="string")

    trace = pd.DataFrame(
        {
            "t_ns": fb(out["t_ns"], dtype=np.int64),
            "agent_id": fb(out["agent_id"], dtype=np.int32),
            "msg_type": strings(out["msg_type"], _TRACE_MSG_TYPES),
            "side": strings(out["side"], _SIDES),
            "price": fb(out["price"], dtype=np.int64),
            "size": fb(out["size"], dtype=np.int64),
            "order_id": fb(out["order_id"], dtype=np.int64),
        }
    )[TRACE_COLUMNS].astype(_TRACE_DTYPES)

    k = len(out["m_t_recv"]) // 8

    def nullable(values: bytes, nulls: bytes) -> Any:
        return pd.arrays.IntegerArray(
            fb(values, dtype=np.int64).copy(), fb(nulls, dtype=np.uint8).astype(bool)
        )

    msg = pd.DataFrame(
        {
            "seq": np.arange(k, dtype=np.int64),
            "t_recv_ns": fb(out["m_t_recv"], dtype=np.int64),
            "t_send_ns": nullable(out["m_t_send"], out["m_t_send_null"]),
            "latency_ns": fb(out["m_latency"], dtype=np.int64),
            "src_id": fb(out["m_src"], dtype=np.int32),
            "dst_id": fb(out["m_dst"], dtype=np.int32),
            "message_id": fb(out["m_message_id"], dtype=np.int64),
            "msg_type": strings(out["m_msg_type"], _t3engine.msg_type_names()),
            "order_id": nullable(out["m_order_id"], out["m_order_id_null"]),
            "causal_parent": nullable(out["m_causal"], out["m_causal_null"]),
        }
    ).astype(_MSG_DTYPES)[MESSAGE_TRACE_COLUMNS]
    return trace, msg

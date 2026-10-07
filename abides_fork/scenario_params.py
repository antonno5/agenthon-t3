"""Scenario-parameter rules shared by the ABIDES config (config.py) and the native engine
(native.py). Pure Python with no ABIDES/numpy/pandas imports, so the native path can use the
exact same mapping without paying for those imports.
"""

from __future__ import annotations

# Annotations stay unevaluated strings (`Any`, `Optional` from typing): this module is on the
# native fast path, which avoids importing typing at all.



def _oracle_kappa_per_ns(oracle_params: dict[str, Any]) -> float:
    """Convert the scenario's per-second OU mean-reversion rate to ABIDES's per-ns rate.

    ABIDES's ``SparseMeanRevertingOracle`` applies ``exp(-kappa * d)`` with ``d`` in
    nanoseconds, so a scenario ``kappa`` of e.g. 0.05 fed in directly would underflow and
    pin the fundamental to a constant. We read it as per-second and divide by 1e9. Absent
    kappa falls back to the gentle upstream rmsc04 default (already per-nanosecond).
    """
    kappa_per_s = float(oracle_params.get("kappa", 0.0))
    return kappa_per_s / 1e9 if kappa_per_s > 0 else 1.67e-16


def _oracle_megashock_rate_per_ns(oracle_params: dict[str, Any]) -> float:
    """Convert the scenario's per-second jump (megashock) intensity to ABIDES's per-ns rate.

    ABIDES draws megashock inter-arrivals at rate ``megashock_lambda_a`` per nanosecond, so a
    scenario ``jump_intensity`` (e.g. 2.0) fed in directly fires megashocks every ~0.5ns -- a
    runaway price process. We read it as a per-SECOND jump rate and divide by 1e9. Absent or
    zero jumps fall back to the gentle upstream rmsc04 default (effectively no megashocks).
    """
    rate_per_s = float(oracle_params.get("jump_intensity", 0.0))
    return rate_per_s / 1e9 if rate_per_s > 0 else 2.77778e-18


def _interval_ns(params: dict[str, Any]) -> int:
    """Per-wakeup interval: explicit rebalance interval, else 1 / arrival_rate_hz."""
    if "rebalance_interval_ns" in params:
        return int(params["rebalance_interval_ns"])
    hz = float(params.get("arrival_rate_hz", 1.0))
    return int(1e9 / hz) if hz > 0 else int(1e9)


def _agent_kwargs(
    agent_type: str, params: dict[str, Any], reference_price: int
) -> dict[str, Any]:
    """Translate scenario params into the custom agent's constructor kwargs."""
    common = {"interval_ns": _interval_ns(params)}
    if agent_type == "NoiseTrader":
        return {
            **common,
            "order_size_mean": params.get("order_size_mean", 10),
            "order_size_std": params.get("order_size_std", 2),
            "price_offset_ticks": params.get("price_offset_ticks", 5),
            "reference_price": reference_price,
        }
    if agent_type == "MarketMaker":
        return {
            **common,
            "spread_ticks": params.get("spread_ticks", 2),
            "depth_levels": params.get("depth_levels", 3),
            "size_per_level": params.get("size_per_level", 10),
            "reference_price": reference_price,
        }
    if agent_type == "ValueTrader":
        # fundamental_value_source is always the oracle in this baseline.
        return {
            **common,
            "order_size_mean": params.get("order_size_mean", 25),
            "threshold_ticks": params.get("threshold_ticks", 2),
        }
    if agent_type == "MomentumTrader":
        return {
            **common,
            "order_size_mean": params.get("order_size_mean", 15),
            "threshold_ticks": params.get("threshold_ticks", 2),
            "lookback": params.get("lookback", 5),
        }
    raise KeyError(f"unsupported agent_type: {agent_type!r}")

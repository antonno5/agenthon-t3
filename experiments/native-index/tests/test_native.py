"""Check dispatch, native repeatability, isolated state and exact numeric helpers."""

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest
from abides_fork import native


@pytest.fixture
def scenario():
    return json.loads(
        Path("/units/t3-s001-price-time-priority/scenario.json").read_text()
    )


def test_lazy_import():
    p = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from abides_fork import native; "
            'assert not ({"numpy","pandas","pyarrow"} & set(sys.modules)); '
            "assert native._t3engine is not None",
        ],
        capture_output=True,
    )
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("seed", [0, 1, 42, 2**32 - 1])
def test_independent_native_runs(scenario, seed):
    scenario["seed"] = seed
    cfg = native.build_native_config(scenario)
    assert cfg is not None
    first = native._t3engine.run(cfg)
    other = copy.deepcopy(scenario)
    other["seed"] = (seed + 1) % (2**32)
    native._t3engine.run(native.build_native_config(other))
    assert native._t3engine.run(cfg) == first


@pytest.mark.parametrize("seed", [-1, 2**32, 1.5, True])
def test_unsupported_seed_rejected(scenario, seed):
    scenario["seed"] = seed
    assert native.build_native_config(scenario) is None


def test_native_only_rejects_fallback(scenario, tmp_path):
    from abides_fork.simulate import simulate

    scenario.pop("latency_config")
    p = tmp_path / "scenario.json"
    p.write_text(json.dumps(scenario))
    with pytest.raises(RuntimeError, match="fallback"):
        simulate(p, tmp_path / "trace.parquet", engine="native")


def test_optimized_python_fallback(scenario, tmp_path):
    from abides_fork.simulate import simulate

    scenario.pop("latency_config")
    p = tmp_path / "scenario.json"
    p.write_text(json.dumps(scenario))
    ev = simulate(p, tmp_path / "trace.parquet", engine="auto")
    assert ev["engine"] == "python"
    from abides_markets.matching.state import _PriceLevels
    from abides_markets.orders import Side

    levels = _PriceLevels(Side.BID)
    assert levels._prices_start == 0


def test_native_matches_python_verify(scenario, tmp_path):
    from abides_fork.simulate import simulate
    import pandas as pd

    p = tmp_path / "scenario.json"
    p.write_text(json.dumps(scenario))
    a = simulate(p, tmp_path / "native/trace.parquet", engine="native")
    b = simulate(
        p, tmp_path / "python/trace.parquet", trace_mode="verify", engine="python"
    )
    assert a["n_events"] == b["n_events"]
    assert a["n_messages"] == b["n_messages"]
    for name in ["trace.parquet", "message_trace.parquet"]:
        pd.testing.assert_frame_equal(
            pd.read_parquet(tmp_path / "native" / name),
            pd.read_parquet(tmp_path / "python" / name),
        )


def test_book_state_machine():
    p = subprocess.run(["/opt/native-tests/book_test"], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "80,000" in p.stdout

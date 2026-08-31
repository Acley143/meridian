from decimal import Decimal

import pytest
from quant_core.simulation import PathParams, simulate_path

_PARAMS = PathParams(s0=Decimal(100), drift=0.05, volatility=0.2, dt=1.0 / 252)


def test_path_params_rejects_non_positive_s0() -> None:
    with pytest.raises(ValueError):
        PathParams(s0=Decimal(0), drift=0.05, volatility=0.2, dt=1.0 / 252)


def test_path_params_rejects_negative_volatility() -> None:
    with pytest.raises(ValueError):
        PathParams(s0=Decimal(100), drift=0.05, volatility=-0.1, dt=1.0 / 252)


def test_path_params_rejects_non_positive_dt() -> None:
    with pytest.raises(ValueError):
        PathParams(s0=Decimal(100), drift=0.05, volatility=0.2, dt=0.0)


def test_simulate_path_rejects_negative_n() -> None:
    with pytest.raises(ValueError):
        list(simulate_path(b"seed", _PARAMS, -1))


def test_simulate_path_same_seed_is_byte_identical() -> None:
    seed = b"instrument-1|2026-01-01|0.1.0"
    path_a = list(simulate_path(seed, _PARAMS, 50))
    path_b = list(simulate_path(seed, _PARAMS, 50))
    assert path_a == path_b
    assert all(isinstance(p, Decimal) for p in path_a)


def test_simulate_path_different_seeds_diverge() -> None:
    path_a = list(simulate_path(b"seed-a", _PARAMS, 50))
    path_b = list(simulate_path(b"seed-b", _PARAMS, 50))
    assert path_a != path_b


def test_simulate_path_yields_n_prices() -> None:
    assert len(list(simulate_path(b"seed", _PARAMS, 10))) == 10
    assert len(list(simulate_path(b"seed", _PARAMS, 0))) == 0


def test_simulate_path_prices_are_positive_decimal() -> None:
    for p in simulate_path(b"seed", _PARAMS, 100):
        assert p > 0
        assert p.as_tuple().exponent == -8


def test_simulate_path_does_not_mutate_global_numpy_rng_state() -> None:
    import numpy as np

    before = np.random.get_state()
    list(simulate_path(b"seed", _PARAMS, 20))
    after = np.random.get_state()
    assert before[1].tolist() == after[1].tolist()

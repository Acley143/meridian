"""Pure stochastic price-path generation (ADR-0011).

`simulate_path` is the one implementation of geometric Brownian motion
shared by `services/ingest` and anything else that wants to reproduce a
simulated market scenario. It is deterministic given its seed (ADR-0006):
same seed in, byte-identical `Decimal` price sequence out. It uses an
explicitly-constructed `numpy.random.Generator` seeded from a blake2b
digest of the caller-supplied seed bytes — it never touches NumPy's
module-level/global RNG, because global RNG state is how determinism dies
quietly (a second caller's draw would shift this generator's stream).
"""
import hashlib
import math
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from quant_core.numeric import to_model, to_money


@dataclass(frozen=True)
class PathParams:
    """Inputs to a single simulated GBM price path.

    `drift` and `volatility` are continuously compounded, annualised
    decimals (docs/conventions.md); `dt` is the fixed step size in years.
    """

    s0: Decimal
    drift: float
    volatility: float
    dt: float

    def __post_init__(self) -> None:
        if self.s0 <= 0:
            raise ValueError(f"s0 must be positive, got {self.s0}")
        if self.volatility < 0:
            raise ValueError(f"volatility must be non-negative, got {self.volatility}")
        if self.dt <= 0:
            raise ValueError(f"dt must be positive, got {self.dt}")


def _seed_generator(seed: bytes) -> np.random.Generator:
    digest = hashlib.blake2b(seed, digest_size=8).digest()
    seed_int = int.from_bytes(digest, byteorder="big", signed=False)
    return np.random.Generator(np.random.PCG64(seed_int))


def simulate_path(seed: bytes, params: PathParams, n: int) -> Iterator[Decimal]:
    """Yield `n` successive prices along one simulated GBM path, `params.dt`
    years apart, under the exact solution (not an Euler discretisation):

        S(t+dt) = S(t) * exp((mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z),  Z ~ N(0,1)

    Deterministic in `seed`: two calls with the same `seed` and `params`
    yield byte-identical `Decimal` sequences.
    """
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")

    rng = _seed_generator(seed)
    drift_term = (params.drift - 0.5 * params.volatility * params.volatility) * params.dt
    vol_term = params.volatility * math.sqrt(params.dt)

    price = to_model(params.s0)
    for _ in range(n):
        z = rng.standard_normal()
        price = price * math.exp(drift_term + vol_term * z)
        yield to_money(price)

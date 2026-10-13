"""American options on a forward-matched Jarrow-Rudd lattice (ADR-0031).

Every function here prices and computes Greeks **per single unit of
underlying**, with no contract multiplier applied (ADR-0014), in the same
sign/unit conventions as `quant_core.pricing.black_scholes`
(docs/conventions.md).

Evaluation order (ADR-0031 Decision 3):

1. T <= 0: Black-Scholes's at-expiry semantics.
2. sigma == 0: the deterministic branch (`_deterministic`).
3. sigma > 0 inside the validated domain D: the lattice.
4. sigma > 0 outside D: `ModelDomainError`.

The lattice is only trusted inside D; outside it the pricer refuses rather
than publish a number nobody has measured.
"""
import math
from typing import Final

import numpy as np
import numpy.typing as npt

from quant_core import PRICER_VERSION
from quant_core.numeric import to_model, to_money
from quant_core.pricing.black_scholes import _at_expiry, _time_to_expiry, _zero_vol
from quant_core.types import (
    AmericanOption,
    MarketState,
    OptionRight,
    PricingResult,
    validate_option_against_market,
)

STEP_COUNT: Final = 128  # ADR-0031 Decision 1: N is a model parameter; changing it needs a superseding ADR
LAMBDA_MAX: Final = 0.05  # ADR-0031 Decision 5: lambda = |r-q|*sqrt(T/N)/sigma < 0.05
SIGMA_ROOT_T_MAX: Final = 0.5  # ADR-0031 Decision 5: sigma*sqrt(T) < 0.5
STEP_SPREAD_MIN: Final = 1e-6  # ADR-0031 Decision 5: a = sigma*sqrt(T/N) >= 1e-6
VOL_MIN: Final = 1e-4  # ADR-0031 Decision 5: 1e-4 <= sigma
VOL_MAX: Final = 3.0  # ADR-0031 Decision 5: sigma <= 3
TIME_MAX: Final = 10.0  # ADR-0031 Decision 5: T <= 10
RATE_MIN: Final = -0.1  # ADR-0031 Decision 5: -0.1 <= r
RATE_MAX: Final = 0.3  # ADR-0031 Decision 5: r <= 0.3
DIVIDEND_MIN: Final = 0.0  # ADR-0031 Decision 5: 0 <= q
DIVIDEND_MAX: Final = 0.3  # ADR-0031 Decision 5: q <= 0.3
VEGA_BUMP_FRACTION: Final = 0.05  # ADR-0031 Decision 2: vega central difference, h = 0.05*sigma
RHO_BUMP: Final = 1e-4  # ADR-0031 Decision 2: rho central difference on the fixed grid, h = 1e-4

_LN2 = math.log(2.0)

_FloatArray = npt.NDArray[np.float64]


class ModelDomainError(ValueError):
    """The inputs lie outside ADR-0031's validated domain D, so no price is
    published. `violations` names each failed condition with its value."""

    def __init__(self, violations: tuple[str, ...]) -> None:
        self.violations = violations
        super().__init__("outside the ADR-0031 validated domain: " + "; ".join(violations))


def _ln_cosh(a: float) -> float:
    """ln cosh(a) as a + log1p(exp(-2a)) - ln 2: no overflow at large a.
    It cancels at small a (ADR-0031 Decision 2); kept as measured."""
    return a + math.log1p(math.exp(-2.0 * a)) - _LN2


def _spread_and_drift(r: float, q: float, vol: float, dt: float) -> tuple[float, float]:
    """(a, mu): half log-spread and per-step log drift of the forward-matched
    Jarrow-Rudd step, mu = (r-q)*dt - ln cosh(a), so that (u+d)/2 = e^((r-q)dt)."""
    a = vol * math.sqrt(dt)
    return a, (r - q) * dt - _ln_cosh(a)


def _step_parameters(r: float, q: float, vol: float, dt: float) -> tuple[float, float, float, float]:
    """(u, d, p, disc) for one forward-matched Jarrow-Rudd step (ADR-0031 Decision 1)."""
    a, mu = _spread_and_drift(r, q, vol, dt)
    return math.exp(mu + a), math.exp(mu - a), 0.5, math.exp(-r * dt)


def _fixed_grid_probability(r: float, vol: float, dt: float, rate_eval: float) -> float:
    """Method B up-probability (ADR-0031 Decision 2): nodes held at the base
    rate r, probability re-matched to the forward at rate_eval.

    p = (e^((rate_eval-q)dt) - d)/(u - d), divided through by e^mu so it
    needs no q: x = (rate_eval - r)*dt + ln cosh(a). Equals 1/2 at
    rate_eval = r up to ln cosh rounding."""
    a = vol * math.sqrt(dt)
    x = (rate_eval - r) * dt + _ln_cosh(a)
    return (math.expm1(x) - math.expm1(-a)) / (2.0 * math.sinh(a))


def _lattice(
    s: float,
    k: float,
    r: float,
    q: float,
    t: float,
    vol: float,
    is_call: bool,
    n_steps: int,
    american: bool = True,
    rate_eval: float | None = None,
) -> tuple[float, float, float, float]:
    """(price, delta, gamma, theta) from one backward pass of the lattice.

    rate_eval=None is the production lattice at r. A given rate_eval is
    rho Method B: the grid (dt, u, d) is built at r, and the probability and
    per-step discount are evaluated at rate_eval."""
    dt = t / n_steps
    a, mu = _spread_and_drift(r, q, vol, dt)
    if rate_eval is None:
        half_disc = 0.5 * math.exp(-r * dt)
        p_down = p_up = half_disc
    else:
        p = _fixed_grid_probability(r, vol, dt, rate_eval)
        disc = math.exp(-rate_eval * dt)
        p_up, p_down = disc * p, disc * (1.0 - p)

    # Node spot at step i, level j (j up-moves): s * e^(i*mu) * e^((2j-i)*a).
    spacing = np.exp(a * np.arange(-n_steps, n_steps + 1, dtype=np.float64))
    terminal = s * math.exp(n_steps * mu) * spacing[0 : 2 * n_steps + 1 : 2]
    values: _FloatArray = np.maximum(terminal - k, 0.0) if is_call else np.maximum(k - terminal, 0.0)
    kept: dict[int, _FloatArray] = {}
    for i in range(n_steps - 1, -1, -1):
        if rate_eval is None:
            values = p_down * (values[:-1] + values[1:])
        else:
            values = p_down * values[:-1] + p_up * values[1:]
        if american:
            spots = s * math.exp(i * mu) * spacing[n_steps - i : n_steps + i + 1 : 2]
            np.maximum(values, (spots - k) if is_call else (k - spots), out=values)
        if i <= 2:
            kept[i] = values.copy()

    v2, v1, v0 = kept[2], kept[1], kept[0]
    e1, e2 = math.exp(mu), math.exp(2.0 * mu)
    # Actual node spots: step 1 at s*e^mu*e^(+/-a); step 2 at s*e^(2mu)*e^(-2a, 0, +2a).
    ds1 = s * e1 * 2.0 * math.sinh(a)
    ds2_hi = s * e2 * math.expm1(2.0 * a)
    ds2_lo = -s * e2 * math.expm1(-2.0 * a)
    ds2_span = s * e2 * 2.0 * math.sinh(2.0 * a)
    price: float = v0[0].item()
    delta: float = ((v1[1] - v1[0]) / ds1).item()
    gamma: float = (((v2[2] - v2[1]) / ds2_hi - (v2[1] - v2[0]) / ds2_lo) / (0.5 * ds2_span)).item()
    # ADR-0031 Decision 2: the step-2 middle node sits at s*e^(2mu), not s;
    # dS = s*(e^(2mu) - 1) and the delta*dS term removes that bias.
    d_s = s * math.expm1(2.0 * mu)
    theta: float = ((v2[1] - v0[0] - delta * d_s) / (2.0 * dt)).item()
    return price, delta, gamma, theta


def _exercise_date(s: float, k: float, r: float, q: float, t: float, is_call: bool, n_steps: int) -> tuple[int, float]:
    """(i*, value) for sigma = 0: the earliest grid index maximising the
    discounted deterministic payoff e^(-r*t_i) * payoff(s*e^((r-q)*t_i))."""
    best_i, best = 0, -math.inf
    for i in range(n_steps + 1):
        t_i = i * t / n_steps
        forward = s * math.exp((r - q) * t_i)
        value = math.exp(-r * t_i) * max((forward - k) if is_call else (k - forward), 0.0)
        if value > best:
            best_i, best = i, value
    return best_i, best


def _deterministic(
    s: float, k: float, r: float, q: float, t: float, is_call: bool, n_steps: int
) -> tuple[float, float, float, float, float, float]:
    """(price, delta, gamma, theta, vega, rho) at sigma = 0 (ADR-0031 Decision 4).

    Delta and rho are exact derivatives with the exercise date t* held
    fixed; theta is 0 unless exercise is at expiry, where it is
    Black-Scholes's zero-volatility theta; gamma and vega are 0."""
    i_star, value = _exercise_date(s, k, r, q, t, is_call, n_steps)
    if value <= 0.0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    t_star = i_star * t / n_steps
    sign = 1.0 if is_call else -1.0
    delta = sign * math.exp(-q * t_star)
    rho = sign * t_star * k * math.exp(-r * t_star)
    theta = 0.0 if i_star < n_steps else _zero_vol(s, k, r, q, t, is_call).theta
    return value, delta, 0.0, theta, 0.0, rho


def _domain_violations(r: float, q: float, t: float, vol: float, n_steps: int) -> tuple[str, ...]:
    """Each ADR-0031 Decision 5 condition that (r, q, t, vol) violates, keyed
    and with its value and bound. D applies only for t > 0 and vol > 0."""
    if t <= 0.0 or vol <= 0.0:
        return ()
    lam = abs(r - q) * math.sqrt(t / n_steps) / vol
    sigma_root_t = vol * math.sqrt(t)
    step_spread = vol * math.sqrt(t / n_steps)
    violations = []
    if not lam < LAMBDA_MAX:
        violations.append(f"lambda={lam} >= {LAMBDA_MAX}")
    if not sigma_root_t < SIGMA_ROOT_T_MAX:
        violations.append(f"sigma_root_t={sigma_root_t} >= {SIGMA_ROOT_T_MAX}")
    if not step_spread >= STEP_SPREAD_MIN:
        violations.append(f"step_spread={step_spread} < {STEP_SPREAD_MIN}")
    if not RATE_MIN <= r <= RATE_MAX:
        violations.append(f"rate={r} outside [{RATE_MIN}, {RATE_MAX}]")
    if not DIVIDEND_MIN <= q <= DIVIDEND_MAX:
        violations.append(f"dividend_yield={q} outside [{DIVIDEND_MIN}, {DIVIDEND_MAX}]")
    if not VOL_MIN <= vol <= VOL_MAX:
        violations.append(f"vol={vol} outside [{VOL_MIN}, {VOL_MAX}]")
    if not t <= TIME_MAX:
        violations.append(f"time_to_expiry={t} > {TIME_MAX}")
    return tuple(violations)


def _price_float(
    s: float, k: float, r: float, q: float, t: float, vol: float, is_call: bool
) -> tuple[float, float, float, float, float, float]:
    """(price, delta, gamma, theta, vega, rho) in ADR-0031 Decision 3's
    evaluation order. Raises ModelDomainError outside D."""
    if t <= 0.0:
        expired = _at_expiry(s, k, is_call)
        return to_model(expired.price), expired.delta, 0.0, 0.0, 0.0, 0.0
    if vol == 0.0:
        return _deterministic(s, k, r, q, t, is_call, STEP_COUNT)
    violations = _domain_violations(r, q, t, vol, STEP_COUNT)
    if violations:
        raise ModelDomainError(violations)
    price, delta, gamma, theta = _lattice(s, k, r, q, t, vol, is_call, STEP_COUNT)
    h = VEGA_BUMP_FRACTION * vol
    vega = (
        _lattice(s, k, r, q, t, vol + h, is_call, STEP_COUNT)[0]
        - _lattice(s, k, r, q, t, vol - h, is_call, STEP_COUNT)[0]
    ) / (2.0 * h)
    rho = (
        _lattice(s, k, r, q, t, vol, is_call, STEP_COUNT, rate_eval=r + RHO_BUMP)[0]
        - _lattice(s, k, r, q, t, vol, is_call, STEP_COUNT, rate_eval=r - RHO_BUMP)[0]
    ) / (2.0 * RHO_BUMP)
    return price, delta, gamma, theta, vega, rho


def american_domain_violations(option: AmericanOption, market: MarketState) -> tuple[str, ...]:
    """The ADR-0031 validated-domain conditions this option and market
    violate, each named with its value. Empty means `price` will not raise
    ModelDomainError."""
    t = _time_to_expiry(option, market)
    return _domain_violations(market.risk_free_rate, market.dividend_yield, t, market.volatility, STEP_COUNT)


def price(option: AmericanOption, market: MarketState) -> PricingResult:
    """Price and all five Greeks for a vanilla American option, per unit of
    underlying (ADR-0014). Raises ModelDomainError outside ADR-0031's
    validated domain."""
    validate_option_against_market(option, market)

    s = to_model(market.spot)
    k = to_model(option.strike)
    vol = market.volatility
    r = market.risk_free_rate
    q = market.dividend_yield
    t = _time_to_expiry(option, market)
    is_call = option.right is OptionRight.CALL

    if t <= 0.0:
        return _at_expiry(s, k, is_call)
    pr, delta, gamma, theta, vega, rho = _price_float(s, k, r, q, t, vol, is_call)
    return PricingResult(
        price=to_money(pr),
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        pricer_version=PRICER_VERSION,
    )

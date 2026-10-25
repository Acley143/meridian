# ADR-0031: American options on a forward-matched Jarrow-Rudd lattice with a validated domain

## Status

Accepted

## Context

Q2 adds American exercise. American options have no closed form and there are no published reference values to test against, and no independent pricing library (QuantLib, py_vollib) is available. Verification therefore rests on four things:
- agreement with a second lattice parameterisation (CRR);
- the Black-Scholes closed form where American and European values coincide;
- convergence at large step counts;
- property tests.

The project rule is that a wrong number is worse than no number. Every figure below is measured. The scripts and outputs are in [evidence/0031](evidence/0031/README.md), reproducible at commit f07d530.

## Decision

1. Method. Binomial lattice with forward-matched Jarrow-Rudd steps:
   - dt = T/N, a = σ√dt
   - μ = (r−q)·dt − ln cosh(a)
   - u = e^(μ+a), d = e^(μ−a), p = 1/2
   - discount e^(−r·dt) per step
   - exercise checked at every node from step N−1 down to step 0

   The expected forward, ½(u+d), equals e^((r−q)·dt) by construction. N = 128. N is a model parameter: changing it changes published prices and the validated domain, and requires a PRICER_VERSION bump and a superseding ADR.

   Rejected alternatives:
   - CRR: its up-probability leaves (0,1) at 262 of 1,296 grid points.
   - Plain Jarrow-Rudd: its forward error compounds, pricing an American call at vol 3, T 10 34.5% below its European value.
   - A Hull-White control variate: it went below intrinsic in 380 of 2,592 in-the-money cases; left the worst-case price error unchanged (5.305e-2·K with and without it); failed monotonicity in vol 58 times against 2; and cost 46% more.

2. Greeks.
   - Delta and gamma come from the step-1 and step-2 nodes, using actual node spots.
   - Theta is (V₂ − V₀ − Δ·dS)/(2·dt), where V₂ and dS are the step-2 middle node's value and its spot minus S, in black_scholes.py's convention. The middle node does not sit at S (u·d ≠ 1), and the Δ·dS term removes the bias that would otherwise not shrink with N. The ½Γ·dS² term is of order dt, the same order as the lattice's own discretisation error, and is omitted.
   - Vega is a central difference with h = 0.05σ.
   - Rho is a central difference with h = 1e-4 on a fixed grid: dt, u and d are held, p(r′) = (e^((r′−q)·dt) − d)/(u − d), and the per-step discount is e^(−r′·dt). At r′ = r this equals 1/2 within 5.122e-10; the residual is rounding in ln cosh(a) at small a, and the central difference cancels it. Rebuilding the grid at the bumped rate moves nodes relative to the strike; holding it fixed cut the median rho error from 2.671e-2 to 7.930e-4 on calls and from 1.106e-2 to 8.224e-4 on puts. The bump moves p by roughly h·√dt/(2σ): over σ ≥ 1e-4 and T ≤ 10 the bumped p stays within [0.360, 0.640], but at σ = 1e-6 it reaches 8.2 and the lattice diverges. This is one reason D bounds σ from below.

   A full priced result is five lattice builds.

3. Evaluation order.
   1. T ≤ 0: price is intrinsic, delta is the strict indicator, all else 0 (Black-Scholes's at-expiry semantics).
   2. σ = 0: the deterministic branch.
   3. σ > 0 inside D: the lattice.
   4. σ > 0 outside D: ModelDomainError.

4. Deterministic branch (σ = 0).
   - Price is the maximum, over grid dates tᵢ = i·T/N for i = 0..N, of e^(−r·tᵢ)·payoff(S·e^((r−q)·tᵢ)), taking the earliest index on ties. This is the limit the lattice reaches as σ → 0.
   - Delta and rho are exact derivatives with the exercise date held fixed.
   - Theta is 0 when exercise happens before expiry, otherwise Black-Scholes's zero-volatility theta.
   - Gamma and vega are 0.
   - When the value is 0, all Greeks are 0.

   The lattice's own limit is a secant across neighbouring exercise dates. At σ = 1e-6 it differs from these derivatives by up to 1.08e-3 in delta, and by up to 1.89e-3 relative in rho when rho is computed by rebuilding the grid; the fixed-grid rho is undefined at that σ, which lies outside D. These are differences between two definitions of the derivative, not pricing errors.

5. Validated domain D, for σ > 0, all required:
   - λ = |r−q|·√(T/N)/σ < 0.05
   - σ√T < 0.5
   - a = σ√(T/N) ≥ 1e-6
   - 1e-4 ≤ σ ≤ 3
   - T ≤ 10
   - −0.1 ≤ r ≤ 0.3
   - 0 ≤ q ≤ 0.3

   σ√T governs price error. λ measures drift against the tree's spread: as λ approaches 1, both step-1 nodes fall on the same side of the strike, and the lattice returns delta 0 where the reference is 0.35, and vega 0 where the reference is 6.7 to 9.9. The a floor bounds gamma rounding noise, which first exceeds 1e-6 at a ≈ 2.8e-7. The bounds on σ, T, r and q are the sampled ranges: D claims only what was measured.

   The accuracy budget, against N = 4096:
   - price within max(1e-2·|P|, 1e-3·K)
   - delta within 2e-2
   - vega within max(5e-2·|ref|, 1e-3·K·√T)
   - rho within max(5e-2·|ref|, 1e-3·K·T)

   D was chosen by a rule fixed before measuring: the first of four nested candidates on which price and delta meet the budget at every sampled point. On 16,352 sampled points in D, price and delta meet it everywhere, including points where the reference's own error is significant, with that error added. D covers 81.6% of a realistic box (vol 0.05–1, T 0.01–5, r −0.01 to 0.1, q 0–0.1, S/K 0.5–2).

   σ = 0 is priced exactly, while 0 < σ < 1e-4, and small σ with dominant drift, are outside D. That unpriceable band is deliberate.

6. Interface.
   - quant-core exposes american_domain_violations(), a pure function that names each violated condition with its value.
   - The American pricer raises ModelDomainError, a ValueError subclass, outside D.
   - The pricer service maps it to a new unpriceable reason, OUTSIDE_MODEL_DOMAIN, in a later change, after the uncaught-ValueError hazard in the tick loop is fixed.
   - Shipping this pricer bumps PRICER_VERSION from 0.2.0 to 0.3.0.

## Verification

Measured tolerances sit at about twice the measured value. Rows marked as round-off guards bound floating-point noise rather than a measured error.

| Check | Tolerance | Measured |
|---|---|---|
| ½(u+d) = e^((r−q)·dt), including vol 3, T 10 | 1e-14 relative (round-off guard) | — |
| p(r′ = r) = 1/2 for Method B, where a ≥ 1e-6 | 1.1e-9 | 5.122e-10 |
| Method B bumped p at σ = 1e-4, T up to 10 | within [0.3, 0.7] | [0.360, 0.640] |
| American = European on the same tree, q = 0 calls, r ≥ 0 | 1e-12 (round-off guard) | 0 |
| N = 4096 against the Black-Scholes closed form | 1e-4 relative | 3.86e-5 |
| Price against CRR at N = 128, 15 golden cases | 8e-3 relative or 1e-2 absolute | 3.79e-3 relative |
| Delta against CRR | 3e-3 relative or 2e-3 absolute | 1.53e-3 / 9.57e-4 |
| Gamma against CRR | 1.2e-2 relative or 4e-4 absolute | 5.99e-3 / 1.93e-4 |
| Theta against CRR | 5e-2 relative or 8e-2 absolute | 2.18e-2 / 3.63e-2 |
| Vega against the closed form, 3 golden cases | 4.4e-2 relative | 2.168e-2 |
| Rho against the closed form, 3 golden cases | 2.1e-3 relative | 1.049e-3 |
| Budget at 2,000 fixed points in D, through the public API | budget above | all pass |
| \|P(256) − P(128)\|, at-the-money put | 3.6e-3 | 1.76e-3; N = 64 gives 1.86e-2 |
| N pinned to 128 by assertion (regression guard) | exact | — |
| American ≥ European on the same tree; American ≥ intrinsic | exact | 0 failures |
| Delta within its bounds | 3e-10 | 1.359e-10 |
| Gamma·S ≥ 0 | −1.6e-4 | −7.617e-5 |
| Monotonic in volatility | 1e-12·K (round-off guard) | 6.196e-14·K |
| Deterministic branch against the lattice at σ = 1e-6: price | 1e-10 absolute (round-off guard) | 1.361e-12 |
| Same: delta / theta | 2.5e-3 / 4e-3 absolute | 1.08e-3 / 1.858e-3 |
| Same: rho, lattice rho by rebuilding the grid | 4e-3 relative; 1e-9 absolute where branch rho is 0 (round-off guard) | 1.89e-3; 0 |
| T = 0 against Black-Scholes at expiry, calls and puts | exact | — |
| Fixtures match their generator | 1e-12 relative (round-off guard) | — |

The convergence check is a measurement, not a proof: convergence in N is not monotonic.

## Known limitations

- At r = 0 with q = 0, the American price has a kink in r. The published rho is the central secant, and the one-sided derivatives differ by up to twice its value.
- Inside D, vega misses the budget at 4 of 2,828 resolved points (largest absolute error 1.05) and rho at 7 of 3,299 (largest absolute error 2.44), against CRR at N = 4096.
- Price is not monotonic in T at fixed N. This was not measured inside D.
- S/K outside [0.25, 4] and T below 1e-4 lie inside D but outside the sampled region. The T → 0 limits were checked separately down to T = 1e-8.

## Performance

A full priced result takes a median of 1,617 µs (p99 1,865 µs), about 620 per second per consumer. A book of American options cannot sustain 1,000 ticks per second on one pricer consumer. This is recorded now for Q4 against docs/nfr-budget.md.

## Consequences

- One out-of-domain American position makes its portfolio unpriceable for that tick.
- Unpriceable reasons are not yet surfaced beyond logs and counters.
- The route to a wider domain is BBSR (Black-Scholes smoothing at the final step, plus Richardson extrapolation), planned for Q3.

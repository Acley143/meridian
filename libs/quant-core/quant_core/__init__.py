"""quant_core — pure pricing and risk-analytics library (ADR-0010).

No I/O, ever. See the package docstrings of `quant_core.numeric`,
`quant_core.types`, `quant_core.pricing.black_scholes`, and
`quant_core.simulation` for the rest of the public surface.
"""

PRICER_VERSION = "0.1.0"
"""Manually-bumped semver identifying pricing-model behavior (ADR-0007).

Part of a `RiskSnapshot`'s identity tuple `(portfolio_id, as_of_event_time,
pricer_version)`. This is a **manual, deliberate** version, not a hash of
the source: a source hash changes on a comment edit or a reformat, forking
snapshot identity with no modelling change behind it, which destroys the
ability to diff risk history across model versions — the entire reason
ADR-0007 exists.

Bump this only in a PR that changes model behavior, and say in that PR's
description what changed about the model. A PR that doesn't change pricing
behavior must not bump this.

Q1 ships 0.1.0.
"""

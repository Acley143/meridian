"""Deterministic per-instrument seed derivation (ADR-0006, ADR-0011).

Mirrors ADR-0006's pattern (`blake2b` over the fields that should
distinguish one reproducible run from another) for the ingest side: a
scenario's `seed` plus each instrument gets its own independent RNG stream,
so two instruments in the same scenario never draw correlated paths, and
nothing about the derivation touches the wall clock, process id, or any
other non-reproducible input.
"""
from __future__ import annotations

import hashlib


def derive_path_seed(*, scenario_id: str, scenario_seed: int, instrument_id: str) -> bytes:
    digest_input = f"{scenario_id}|{scenario_seed}|{instrument_id}".encode()
    return hashlib.blake2b(digest_input, digest_size=16).digest()

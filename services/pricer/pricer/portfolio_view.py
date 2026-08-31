"""The pricer's local materialized view of `portfolio.state` (ADR-0003),
plus the derived reverse index a tick needs to find affected portfolios.

Each `PortfolioState` message is the full current state of one portfolio,
not a delta (docs/domain-model.md#portfoliostate) -- `apply` always
replaces a portfolio's positions wholesale, never patches them.

The reverse index is keyed by **underlying_id**, not raw `Position.
instrument_id`. `market.ticks` only ever carries prices for underlyings
(services/ingest/PLAN.md: "options are quoted derivatively, not simulated
directly in Q1") -- a position on a derivative (e.g. a European option)
never itself receives a tick, only its underlying does. For a non-derivative
instrument, `underlying_id == instrument_id` by definition
(docs/domain-model.md#Instrument), so this is a strict generalization of
"instrument_id -> portfolios holding it," not a different index.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from meridian_contracts.portfolio_state import Position

from pricer.reference_data import ReferenceData


@dataclass
class _PortfolioRecord:
    positions: list[Position]
    event_time: datetime


@dataclass
class PortfolioView:
    reference_data: ReferenceData
    _portfolios: dict[str, _PortfolioRecord] = field(default_factory=dict, init=False)
    _reverse_index: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set), init=False)

    def _underlyings(self, positions: list[Position]) -> set[str]:
        result = set()
        for position in positions:
            if position.instrument_id in self.reference_data:
                result.add(self.reference_data.get(position.instrument_id).underlying_id)
        return result

    def apply(self, portfolio_id: str, positions: list[Position], event_time: datetime) -> None:
        """Replace `portfolio_id`'s positions wholesale and update the
        reverse index for exactly the underlyings that changed -- added,
        removed, or unchanged."""
        old_underlyings = (
            self._underlyings(self._portfolios[portfolio_id].positions)
            if portfolio_id in self._portfolios
            else set()
        )
        self._portfolios[portfolio_id] = _PortfolioRecord(
            positions=list(positions), event_time=event_time
        )
        new_underlyings = self._underlyings(positions)
        self._reindex(portfolio_id, old_underlyings, new_underlyings)

    def remove(self, portfolio_id: str) -> bool:
        """Tombstone: delete a portfolio and clear it from the reverse
        index. Returns False if the portfolio wasn't in the view (a
        tombstone for a portfolio never seen, or already removed)."""
        record = self._portfolios.pop(portfolio_id, None)
        if record is None:
            return False
        self._reindex(portfolio_id, self._underlyings(record.positions), set())
        return True

    def _reindex(self, portfolio_id: str, old: set[str], new: set[str]) -> None:
        for underlying_id in old - new:
            self._reverse_index[underlying_id].discard(portfolio_id)
            if not self._reverse_index[underlying_id]:
                del self._reverse_index[underlying_id]
        for underlying_id in new - old:
            self._reverse_index[underlying_id].add(portfolio_id)

    def portfolios_for_underlying(self, underlying_id: str) -> set[str]:
        return set(self._reverse_index.get(underlying_id, ()))

    def positions(self, portfolio_id: str) -> list[Position]:
        return self._portfolios[portfolio_id].positions

    def portfolio_ids(self) -> set[str]:
        return set(self._portfolios)

    def __len__(self) -> int:
        return len(self._portfolios)

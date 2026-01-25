"""Data classes for EdgeFinder."""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Odds:
    """Represents odds from a single sportsbook."""
    bookmaker: str
    american: int
    decimal: float = field(init=False)
    implied_prob: float = field(init=False)

    def __post_init__(self):
        self.decimal = self._american_to_decimal(self.american)
        self.implied_prob = 1 / self.decimal

    @staticmethod
    def _american_to_decimal(american: int) -> float:
        if american > 0:
            return (american / 100) + 1
        else:
            return (100 / abs(american)) + 1


@dataclass
class Market:
    """Represents a betting market (e.g., moneyline, spread)."""
    sport: str
    event: str
    market_type: str  # moneyline, spread, total
    selection: str    # Team name or Over/Under
    point: Optional[float] = None  # Spread or total line
    odds_list: list[Odds] = field(default_factory=list)
    commence_time: Optional[datetime] = None

    def best_odds(self) -> Optional[Odds]:
        """Return the best available odds."""
        if not self.odds_list:
            return None
        return max(self.odds_list, key=lambda o: o.decimal)

    def get_odds_by_book(self, bookmaker: str) -> Optional[Odds]:
        """Get odds from a specific bookmaker."""
        for odds in self.odds_list:
            if odds.bookmaker.lower() == bookmaker.lower():
                return odds
        return None


@dataclass
class Bet:
    """Represents a recommended bet."""
    market: Market
    best_odds: Odds
    fair_prob: float
    ev_percent: float
    kelly_fraction: float
    recommended_stake: float

    @property
    def fair_decimal(self) -> float:
        return 1 / self.fair_prob if self.fair_prob > 0 else 0

    @property
    def fair_american(self) -> int:
        if self.fair_prob <= 0 or self.fair_prob >= 1:
            return 0
        decimal = self.fair_decimal
        if decimal >= 2:
            return int((decimal - 1) * 100)
        else:
            return int(-100 / (decimal - 1))


@dataclass
class ArbitrageOpportunity:
    """Represents an arbitrage opportunity."""
    sport: str
    event: str
    market_type: str
    selections: list[tuple[str, Odds]]  # (selection_name, best_odds)
    total_implied: float  # Sum of implied probs (< 1 means arb exists)
    profit_percent: float
    stakes: list[tuple[str, str, float]]  # (selection, bookmaker, stake)


@dataclass
class DevigResult:
    """Result from de-vigging odds."""
    fair_probs: list[float]
    method: str
    original_implied: list[float]
    vig_removed: float

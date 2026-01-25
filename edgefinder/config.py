"""Configuration settings for EdgeFinder."""

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Application configuration."""

    # API settings
    odds_api_key: str = field(default_factory=lambda: os.environ.get("ODDS_API_KEY", ""))
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"

    # Bankroll settings
    bankroll: float = 1000.0

    # Kelly settings
    kelly_fraction: float = 0.25  # Quarter Kelly by default
    max_bet_percent: float = 0.05  # Max 5% of bankroll per bet
    max_total_exposure: float = 0.25  # Max 25% total exposure

    # EV settings
    min_ev_percent: float = 1.0  # Minimum EV% to show

    # Sportsbook sharpness weights (higher = sharper)
    book_weights: dict[str, float] = field(default_factory=lambda: {
        "pinnacle": 1.0,
        "circa": 0.95,
        "bookmaker": 0.9,
        "betcris": 0.85,
        "bovada": 0.7,
        "betonlineag": 0.7,
        "draftkings": 0.6,
        "fanduel": 0.6,
        "betmgm": 0.55,
        "pointsbetus": 0.5,
        "caesars": 0.5,
        "wynnbet": 0.45,
        "superbook": 0.8,
        "betrivers": 0.5,
        "unibet": 0.5,
    })

    # Sports available on The Odds API
    available_sports: dict[str, str] = field(default_factory=lambda: {
        "nfl": "americanfootball_nfl",
        "ncaaf": "americanfootball_ncaaf",
        "nba": "basketball_nba",
        "ncaab": "basketball_ncaab",
        "mlb": "baseball_mlb",
        "nhl": "icehockey_nhl",
        "mls": "soccer_usa_mls",
        "epl": "soccer_epl",
        "ufc": "mma_mixed_martial_arts",
    })

    # Default bookmakers to fetch
    default_bookmakers: list[str] = field(default_factory=lambda: [
        "pinnacle", "draftkings", "fanduel", "betmgm",
        "caesars", "pointsbetus", "bovada", "betonlineag"
    ])

    # Cache settings
    cache_ttl_seconds: int = 300  # 5 minutes

    def get_sport_key(self, sport: str) -> str:
        """Get API sport key from friendly name."""
        return self.available_sports.get(sport.lower(), sport)

    def get_book_weight(self, bookmaker: str) -> float:
        """Get sharpness weight for a bookmaker."""
        return self.book_weights.get(bookmaker.lower(), 0.5)


# Global config instance
config = Config()

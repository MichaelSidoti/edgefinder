"""Fetch odds from The Odds API with caching."""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from models import Market, Odds
from config import config


# Cache directory
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def fetch_odds(
    sport: str,
    markets: list[str] | None = None,
    bookmakers: list[str] | None = None,
    use_cache: bool = True,
) -> list[tuple[Market, Market | None]]:
    """
    Fetch odds from The Odds API.

    Args:
        sport: Sport key (e.g., 'nfl', 'nba')
        markets: Market types to fetch (default: ['h2h'] for moneyline)
        bookmakers: List of bookmakers to include
        use_cache: Whether to use cached data

    Returns:
        List of (market, opposing_market) tuples
    """
    if not config.odds_api_key:
        print("No API key found. Using sample data.")
        return _get_sample_data(sport)

    if requests is None:
        print("requests library not installed. Using sample data.")
        return _get_sample_data(sport)

    if markets is None:
        markets = ["h2h"]  # Moneyline

    if bookmakers is None:
        bookmakers = config.default_bookmakers

    sport_key = config.get_sport_key(sport)

    # Check cache
    if use_cache:
        cached = _get_cached(sport_key, markets)
        if cached:
            return cached

    # Fetch from API
    try:
        data = _api_request(sport_key, markets, bookmakers)
        result = _parse_response(data, sport)
        _save_cache(sport_key, markets, result)
        return result
    except Exception as e:
        print(f"API error: {e}. Using sample data.")
        return _get_sample_data(sport)


def _api_request(
    sport_key: str,
    markets: list[str],
    bookmakers: list[str],
) -> list[dict[str, Any]]:
    """Make request to The Odds API."""
    url = f"{config.odds_api_base_url}/sports/{sport_key}/odds"

    params = {
        "apiKey": config.odds_api_key,
        "regions": "us",
        "markets": ",".join(markets),
        "bookmakers": ",".join(bookmakers),
        "oddsFormat": "american",
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    # Log remaining requests
    remaining = response.headers.get("x-requests-remaining", "unknown")
    print(f"API requests remaining: {remaining}")

    return response.json()


def _parse_response(
    data: list[dict[str, Any]],
    sport: str,
) -> list[tuple[Market, Market | None]]:
    """Parse API response into Market objects."""
    result = []

    for event in data:
        event_name = f"{event['away_team']} @ {event['home_team']}"
        commence_time = datetime.fromisoformat(
            event["commence_time"].replace("Z", "+00:00")
        )

        for bookmaker in event.get("bookmakers", []):
            book_name = bookmaker["key"]

            for market_data in bookmaker.get("markets", []):
                market_key = market_data["key"]
                outcomes = market_data.get("outcomes", [])

                if len(outcomes) < 2:
                    continue

                # Create markets for each outcome
                markets_by_selection: dict[str, Market] = {}

                for outcome in outcomes:
                    selection = outcome["name"]
                    american_odds = outcome["price"]
                    point = outcome.get("point")

                    if selection not in markets_by_selection:
                        markets_by_selection[selection] = Market(
                            sport=sport,
                            event=event_name,
                            market_type=market_key,
                            selection=selection,
                            point=point,
                            odds_list=[],
                            commence_time=commence_time,
                        )

                    markets_by_selection[selection].odds_list.append(
                        Odds(bookmaker=book_name, american=american_odds)
                    )

        # Pair up markets (home vs away, over vs under)
        selections = list(markets_by_selection.keys())
        if len(selections) >= 2:
            # For 2-way markets, pair them up
            market1 = markets_by_selection[selections[0]]
            market2 = markets_by_selection[selections[1]]
            result.append((market1, market2))
            result.append((market2, market1))

    return result


def _get_cached(
    sport_key: str,
    markets: list[str],
) -> list[tuple[Market, Market | None]] | None:
    """Get cached data if still valid."""
    cache_file = CACHE_DIR / f"{sport_key}_{'_'.join(markets)}.json"

    if not cache_file.exists():
        return None

    try:
        with open(cache_file) as f:
            cached = json.load(f)

        # Check if cache is still valid
        cached_time = cached.get("timestamp", 0)
        if time.time() - cached_time > config.cache_ttl_seconds:
            return None

        # Reconstruct Market objects
        return _deserialize_markets(cached.get("data", []))
    except Exception:
        return None


def _save_cache(
    sport_key: str,
    markets: list[str],
    data: list[tuple[Market, Market | None]],
) -> None:
    """Save data to cache."""
    cache_file = CACHE_DIR / f"{sport_key}_{'_'.join(markets)}.json"

    try:
        serialized = _serialize_markets(data)
        with open(cache_file, "w") as f:
            json.dump({
                "timestamp": time.time(),
                "data": serialized,
            }, f)
    except Exception:
        pass  # Caching is best-effort


def _serialize_markets(
    markets: list[tuple[Market, Market | None]],
) -> list[dict]:
    """Serialize markets to JSON-compatible format."""
    result = []
    for market, opposing in markets:
        item = {
            "market": {
                "sport": market.sport,
                "event": market.event,
                "market_type": market.market_type,
                "selection": market.selection,
                "point": market.point,
                "odds_list": [
                    {"bookmaker": o.bookmaker, "american": o.american}
                    for o in market.odds_list
                ],
                "commence_time": market.commence_time.isoformat() if market.commence_time else None,
            },
            "opposing": None,
        }
        if opposing:
            item["opposing"] = {
                "sport": opposing.sport,
                "event": opposing.event,
                "market_type": opposing.market_type,
                "selection": opposing.selection,
                "point": opposing.point,
                "odds_list": [
                    {"bookmaker": o.bookmaker, "american": o.american}
                    for o in opposing.odds_list
                ],
                "commence_time": opposing.commence_time.isoformat() if opposing.commence_time else None,
            }
        result.append(item)
    return result


def _deserialize_markets(
    data: list[dict],
) -> list[tuple[Market, Market | None]]:
    """Deserialize markets from JSON format."""
    result = []
    for item in data:
        market_data = item["market"]
        market = Market(
            sport=market_data["sport"],
            event=market_data["event"],
            market_type=market_data["market_type"],
            selection=market_data["selection"],
            point=market_data.get("point"),
            odds_list=[
                Odds(bookmaker=o["bookmaker"], american=o["american"])
                for o in market_data["odds_list"]
            ],
            commence_time=datetime.fromisoformat(market_data["commence_time"])
                if market_data.get("commence_time") else None,
        )

        opposing = None
        if item.get("opposing"):
            opp_data = item["opposing"]
            opposing = Market(
                sport=opp_data["sport"],
                event=opp_data["event"],
                market_type=opp_data["market_type"],
                selection=opp_data["selection"],
                point=opp_data.get("point"),
                odds_list=[
                    Odds(bookmaker=o["bookmaker"], american=o["american"])
                    for o in opp_data["odds_list"]
                ],
                commence_time=datetime.fromisoformat(opp_data["commence_time"])
                    if opp_data.get("commence_time") else None,
            )

        result.append((market, opposing))

    return result


def _get_sample_data(sport: str) -> list[tuple[Market, Market | None]]:
    """Return sample data for testing without API key."""

    if sport.lower() in ["nfl", "americanfootball_nfl"]:
        return _nfl_sample_data()
    elif sport.lower() in ["nba", "basketball_nba"]:
        return _nba_sample_data()
    else:
        return _nfl_sample_data()  # Default to NFL


def _nfl_sample_data() -> list[tuple[Market, Market | None]]:
    """Sample NFL data."""
    games = [
        {
            "event": "Buffalo Bills @ Kansas City Chiefs",
            "home": "Kansas City Chiefs",
            "away": "Buffalo Bills",
            "odds": {
                "Kansas City Chiefs": [
                    ("pinnacle", -145),
                    ("draftkings", -150),
                    ("fanduel", -148),
                    ("betmgm", -140),  # +EV: BetMGM offering better than fair
                    ("caesars", -152),
                ],
                "Buffalo Bills": [
                    ("pinnacle", 125),
                    ("draftkings", 130),
                    ("fanduel", 126),
                    ("betmgm", 135),
                    ("caesars", 138),  # +EV: Caesars offering better than fair
                ],
            },
        },
        {
            "event": "Philadelphia Eagles @ San Francisco 49ers",
            "home": "San Francisco 49ers",
            "away": "Philadelphia Eagles",
            "odds": {
                "San Francisco 49ers": [
                    ("pinnacle", -115),
                    ("draftkings", -112),  # +EV: DK offering better than fair
                    ("fanduel", -118),
                    ("betmgm", -125),
                ],
                "Philadelphia Eagles": [
                    ("pinnacle", -105),
                    ("draftkings", 100),
                    ("fanduel", 102),  # +EV: FanDuel offering +102
                    ("betmgm", 105),
                ],
            },
        },
        {
            "event": "Detroit Lions @ Dallas Cowboys",
            "home": "Dallas Cowboys",
            "away": "Detroit Lions",
            "odds": {
                "Detroit Lions": [
                    ("pinnacle", -180),
                    ("draftkings", -175),
                    ("fanduel", -165),  # +EV: FanDuel way off
                    ("betmgm", -170),
                    ("bovada", -168),
                ],
                "Dallas Cowboys": [
                    ("pinnacle", 155),
                    ("draftkings", 150),
                    ("fanduel", 156),
                    ("betmgm", 165),  # +EV: BetMGM offering better
                    ("bovada", 148),
                ],
            },
        },
    ]

    return _create_markets_from_sample(games, "nfl")


def _nba_sample_data() -> list[tuple[Market, Market | None]]:
    """Sample NBA data."""
    games = [
        {
            "event": "Boston Celtics @ Milwaukee Bucks",
            "home": "Milwaukee Bucks",
            "away": "Boston Celtics",
            "odds": {
                "Milwaukee Bucks": [
                    ("pinnacle", 105),
                    ("draftkings", 110),
                    ("fanduel", 108),
                    ("betmgm", 115),
                ],
                "Boston Celtics": [
                    ("pinnacle", -125),
                    ("draftkings", -130),
                    ("fanduel", -128),
                    ("betmgm", -135),
                ],
            },
        },
        {
            "event": "Denver Nuggets @ Phoenix Suns",
            "home": "Phoenix Suns",
            "away": "Denver Nuggets",
            "odds": {
                "Phoenix Suns": [
                    ("pinnacle", 140),
                    ("draftkings", 145),
                    ("fanduel", 142),
                    ("betmgm", 150),
                ],
                "Denver Nuggets": [
                    ("pinnacle", -165),
                    ("draftkings", -175),
                    ("fanduel", -168),
                    ("betmgm", -180),
                ],
            },
        },
    ]

    return _create_markets_from_sample(games, "nba")


def _create_markets_from_sample(
    games: list[dict],
    sport: str,
) -> list[tuple[Market, Market | None]]:
    """Create Market objects from sample data."""
    result = []

    for game in games:
        markets_by_team: dict[str, Market] = {}

        for team, odds_list in game["odds"].items():
            market = Market(
                sport=sport,
                event=game["event"],
                market_type="h2h",
                selection=team,
                point=None,
                odds_list=[Odds(bookmaker=book, american=odds) for book, odds in odds_list],
            )
            markets_by_team[team] = market

        teams = list(markets_by_team.keys())
        if len(teams) >= 2:
            result.append((markets_by_team[teams[0]], markets_by_team[teams[1]]))
            result.append((markets_by_team[teams[1]], markets_by_team[teams[0]]))

    return result


def get_available_sports() -> list[dict[str, str]]:
    """Get list of available sports from the API."""
    if not config.odds_api_key or requests is None:
        return [
            {"key": v, "title": k.upper()}
            for k, v in config.available_sports.items()
        ]

    try:
        url = f"{config.odds_api_base_url}/sports"
        response = requests.get(
            url,
            params={"apiKey": config.odds_api_key},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return [
            {"key": v, "title": k.upper()}
            for k, v in config.available_sports.items()
        ]

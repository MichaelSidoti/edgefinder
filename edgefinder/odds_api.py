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


def fetch_player_props(
    sport: str,
    event_id: str | None = None,
    prop_markets: list[str] | None = None,
    bookmakers: list[str] | None = None,
    use_cache: bool = True,
) -> list[tuple[Market, Market | None]]:
    """
    Fetch player prop odds from The Odds API.

    Args:
        sport: Sport key (e.g., 'nfl', 'nba')
        event_id: Specific event ID (if None, fetches all events)
        prop_markets: Player prop markets to fetch
        bookmakers: List of bookmakers to include
        use_cache: Whether to use cached data

    Returns:
        List of (market, opposing_market) tuples for player props
    """
    if not config.odds_api_key:
        print("No API key found. Using sample data.")
        return _get_sample_props_data(sport)

    if requests is None:
        print("requests library not installed. Using sample data.")
        return _get_sample_props_data(sport)

    if prop_markets is None:
        prop_markets = config.get_player_prop_markets(sport)

    if not prop_markets:
        print(f"No player prop markets configured for {sport}")
        return []

    if bookmakers is None:
        bookmakers = config.default_bookmakers

    sport_key = config.get_sport_key(sport)

    # Check cache
    cache_key = f"{sport_key}_props"
    if use_cache:
        cached = _get_cached(cache_key, prop_markets)
        if cached:
            return cached

    # First get list of events
    try:
        events = _get_events(sport_key)
        if not events:
            print("No events found")
            return _get_sample_props_data(sport)

        all_props: list[tuple[Market, Market | None]] = []

        # Fetch props for each event (or specific event)
        events_to_fetch = events[:5]  # Limit to 5 events to conserve API calls
        if event_id:
            events_to_fetch = [e for e in events if e["id"] == event_id]

        for event in events_to_fetch:
            props = _fetch_event_props(
                sport_key, event["id"], prop_markets, bookmakers, sport
            )
            all_props.extend(props)

        _save_cache(cache_key, prop_markets, all_props)
        return all_props

    except Exception as e:
        print(f"API error fetching props: {e}. Using sample data.")
        return _get_sample_props_data(sport)


def _get_events(sport_key: str) -> list[dict]:
    """Get list of upcoming events for a sport."""
    url = f"{config.odds_api_base_url}/sports/{sport_key}/events"
    params = {"apiKey": config.odds_api_key}

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def _fetch_event_props(
    sport_key: str,
    event_id: str,
    prop_markets: list[str],
    bookmakers: list[str],
    sport: str,
) -> list[tuple[Market, Market | None]]:
    """Fetch player props for a specific event."""
    url = f"{config.odds_api_base_url}/sports/{sport_key}/events/{event_id}/odds"

    params = {
        "apiKey": config.odds_api_key,
        "regions": "us",
        "markets": ",".join(prop_markets),
        "bookmakers": ",".join(bookmakers),
        "oddsFormat": "american",
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    remaining = response.headers.get("x-requests-remaining", "unknown")
    print(f"API requests remaining: {remaining}")

    data = response.json()
    return _parse_props_response(data, sport)


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

        # Create markets for each outcome - OUTSIDE bookmaker loop to aggregate all books
        markets_by_selection: dict[str, Market] = {}

        for bookmaker in event.get("bookmakers", []):
            book_name = bookmaker["key"]

            for market_data in bookmaker.get("markets", []):
                market_key = market_data["key"]
                outcomes = market_data.get("outcomes", [])

                if len(outcomes) < 2:
                    continue

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


def _parse_props_response(
    data: dict,
    sport: str,
) -> list[tuple[Market, Market | None]]:
    """Parse player props API response into Market objects."""
    result = []

    if not data:
        return result

    event_name = f"{data.get('away_team', 'Away')} @ {data.get('home_team', 'Home')}"
    commence_time = None
    if data.get("commence_time"):
        commence_time = datetime.fromisoformat(
            data["commence_time"].replace("Z", "+00:00")
        )

    # Group props by player + market type + point
    props_by_key: dict[str, dict[str, Market]] = {}

    for bookmaker in data.get("bookmakers", []):
        book_name = bookmaker["key"]

        for market_data in bookmaker.get("markets", []):
            market_key = market_data["key"]
            outcomes = market_data.get("outcomes", [])

            for outcome in outcomes:
                player_name = outcome.get("description", "Unknown")
                selection = outcome["name"]  # Over/Under
                american_odds = outcome["price"]
                point = outcome.get("point")

                # Create unique key for this prop line
                prop_key = f"{player_name}_{market_key}_{point}"

                if prop_key not in props_by_key:
                    props_by_key[prop_key] = {}

                if selection not in props_by_key[prop_key]:
                    props_by_key[prop_key][selection] = Market(
                        sport=sport,
                        event=event_name,
                        market_type=market_key,
                        selection=selection,
                        point=point,
                        odds_list=[],
                        commence_time=commence_time,
                        player=player_name,
                    )

                props_by_key[prop_key][selection].odds_list.append(
                    Odds(bookmaker=book_name, american=american_odds)
                )

    # Pair up Over/Under markets
    for prop_key, selections in props_by_key.items():
        selection_list = list(selections.keys())
        if len(selection_list) >= 2:
            market1 = selections[selection_list[0]]
            market2 = selections[selection_list[1]]
            result.append((market1, market2))
            result.append((market2, market1))
        elif len(selection_list) == 1:
            # Single selection (like anytime TD scorer)
            result.append((selections[selection_list[0]], None))

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
                "player": market.player,
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
                "player": opposing.player,
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
            player=market_data.get("player"),
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
                player=opp_data.get("player"),
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


def _get_sample_props_data(sport: str) -> list[tuple[Market, Market | None]]:
    """Return sample player props data for testing without API key."""

    if sport.lower() in ["nba", "basketball_nba"]:
        return _nba_sample_props()
    elif sport.lower() in ["nfl", "americanfootball_nfl"]:
        return _nfl_sample_props()
    else:
        return _nba_sample_props()


def _nba_sample_props() -> list[tuple[Market, Market | None]]:
    """Sample NBA player props data."""
    props = [
        {
            "event": "Boston Celtics @ Milwaukee Bucks",
            "player": "Giannis Antetokounmpo",
            "market_type": "player_points",
            "point": 32.5,
            "odds": {
                "Over": [
                    ("pinnacle", -115),
                    ("draftkings", -110),
                    ("fanduel", -108),
                    ("betmgm", -105),  # +EV
                ],
                "Under": [
                    ("pinnacle", -105),
                    ("draftkings", -110),
                    ("fanduel", -112),
                    ("betmgm", -115),
                ],
            },
        },
        {
            "event": "Boston Celtics @ Milwaukee Bucks",
            "player": "Jayson Tatum",
            "market_type": "player_points",
            "point": 28.5,
            "odds": {
                "Over": [
                    ("pinnacle", -108),
                    ("draftkings", -115),
                    ("fanduel", -110),
                    ("betmgm", -120),
                ],
                "Under": [
                    ("pinnacle", -112),
                    ("draftkings", -105),
                    ("fanduel", -110),
                    ("betmgm", 100),  # +EV
                ],
            },
        },
        {
            "event": "Boston Celtics @ Milwaukee Bucks",
            "player": "Damian Lillard",
            "market_type": "player_assists",
            "point": 7.5,
            "odds": {
                "Over": [
                    ("pinnacle", 105),
                    ("draftkings", 110),
                    ("fanduel", 115),  # +EV
                    ("betmgm", 100),
                ],
                "Under": [
                    ("pinnacle", -125),
                    ("draftkings", -130),
                    ("fanduel", -135),
                    ("betmgm", -120),
                ],
            },
        },
        {
            "event": "Denver Nuggets @ Phoenix Suns",
            "player": "Nikola Jokic",
            "market_type": "player_rebounds",
            "point": 12.5,
            "odds": {
                "Over": [
                    ("pinnacle", -120),
                    ("draftkings", -115),
                    ("fanduel", -110),  # +EV
                    ("betmgm", -125),
                ],
                "Under": [
                    ("pinnacle", 100),
                    ("draftkings", -105),
                    ("fanduel", -110),
                    ("betmgm", 105),
                ],
            },
        },
    ]

    return _create_props_from_sample(props, "nba")


def _nfl_sample_props() -> list[tuple[Market, Market | None]]:
    """Sample NFL player props data."""
    props = [
        {
            "event": "Buffalo Bills @ Kansas City Chiefs",
            "player": "Patrick Mahomes",
            "market_type": "player_pass_yds",
            "point": 275.5,
            "odds": {
                "Over": [
                    ("pinnacle", -115),
                    ("draftkings", -110),
                    ("fanduel", -105),  # +EV
                    ("betmgm", -120),
                ],
                "Under": [
                    ("pinnacle", -105),
                    ("draftkings", -110),
                    ("fanduel", -115),
                    ("betmgm", 100),
                ],
            },
        },
        {
            "event": "Buffalo Bills @ Kansas City Chiefs",
            "player": "Josh Allen",
            "market_type": "player_pass_tds",
            "point": 1.5,
            "odds": {
                "Over": [
                    ("pinnacle", -145),
                    ("draftkings", -150),
                    ("fanduel", -140),  # +EV
                    ("betmgm", -155),
                ],
                "Under": [
                    ("pinnacle", 125),
                    ("draftkings", 130),
                    ("fanduel", 120),
                    ("betmgm", 135),
                ],
            },
        },
        {
            "event": "Buffalo Bills @ Kansas City Chiefs",
            "player": "Travis Kelce",
            "market_type": "player_reception_yds",
            "point": 65.5,
            "odds": {
                "Over": [
                    ("pinnacle", -110),
                    ("draftkings", -105),
                    ("fanduel", -115),
                    ("betmgm", -100),  # +EV
                ],
                "Under": [
                    ("pinnacle", -110),
                    ("draftkings", -115),
                    ("fanduel", -105),
                    ("betmgm", -120),
                ],
            },
        },
    ]

    return _create_props_from_sample(props, "nfl")


def _create_props_from_sample(
    props: list[dict],
    sport: str,
) -> list[tuple[Market, Market | None]]:
    """Create Market objects from sample props data."""
    result = []

    for prop in props:
        markets_by_selection: dict[str, Market] = {}

        for selection, odds_list in prop["odds"].items():
            market = Market(
                sport=sport,
                event=prop["event"],
                market_type=prop["market_type"],
                selection=selection,
                point=prop["point"],
                odds_list=[Odds(bookmaker=book, american=odds) for book, odds in odds_list],
                player=prop["player"],
            )
            markets_by_selection[selection] = market

        selections = list(markets_by_selection.keys())
        if len(selections) >= 2:
            result.append((markets_by_selection[selections[0]], markets_by_selection[selections[1]]))
            result.append((markets_by_selection[selections[1]], markets_by_selection[selections[0]]))

    return result


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

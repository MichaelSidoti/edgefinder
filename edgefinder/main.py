#!/usr/bin/env python3
"""EdgeFinder - Sports Betting Analytics CLI."""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import config
from odds_api import fetch_odds, get_available_sports
from ev_calculator import find_ev_bets
from arbitrage import find_arbitrage
from kelly import scale_exposure
from display import (
    display_bets,
    display_arbitrage,
    display_devig_comparison,
    print_header,
    print_error,
    print_info,
)
from devig import DEVIG_METHODS, devig
from models import Market


def main():
    parser = argparse.ArgumentParser(
        description="EdgeFinder - Sports Betting Analytics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Show +EV bets for NFL (default)
  python main.py --sport nba        # Show +EV bets for NBA
  python main.py --min-ev 3.0       # Only show bets with 3%+ EV
  python main.py --bankroll 5000    # Set bankroll for Kelly sizing
  python main.py --arb              # Show arbitrage opportunities
  python main.py --devig -150 130   # De-vig specific odds
  python main.py --sports           # List available sports

Set ODDS_API_KEY environment variable for live odds.
        """,
    )

    parser.add_argument(
        "--sport", "-s",
        default="nfl",
        help="Sport to analyze (default: nfl)",
    )

    parser.add_argument(
        "--min-ev",
        type=float,
        default=1.0,
        help="Minimum EV%% threshold (default: 1.0)",
    )

    parser.add_argument(
        "--bankroll", "-b",
        type=float,
        default=1000.0,
        help="Bankroll for Kelly sizing (default: 1000)",
    )

    parser.add_argument(
        "--kelly",
        type=float,
        choices=[0.25, 0.5, 1.0],
        default=0.25,
        help="Kelly fraction (default: 0.25 = quarter Kelly)",
    )

    parser.add_argument(
        "--arb",
        action="store_true",
        help="Show arbitrage opportunities instead of +EV bets",
    )

    parser.add_argument(
        "--arb-stake",
        type=float,
        default=1000.0,
        help="Total stake per arbitrage opportunity (default: 1000)",
    )

    parser.add_argument(
        "--devig",
        nargs="+",
        type=int,
        metavar="ODDS",
        help="De-vig specific American odds (e.g., --devig -150 130)",
    )

    parser.add_argument(
        "--method",
        choices=list(DEVIG_METHODS.keys()),
        default="weighted",
        help="De-vig method (default: weighted)",
    )

    parser.add_argument(
        "--sports",
        action="store_true",
        help="List available sports",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Don't use cached odds data",
    )

    args = parser.parse_args()

    # List sports
    if args.sports:
        print_header("Available Sports")
        sports = get_available_sports()
        for sport in sports:
            print(f"  {sport.get('key', sport.get('title', 'Unknown'))}")
        return 0

    # De-vig specific odds
    if args.devig:
        return handle_devig(args.devig, args.method)

    # Update config
    config.bankroll = args.bankroll
    config.kelly_fraction = args.kelly
    config.min_ev_percent = args.min_ev

    # Fetch odds
    print_info(f"Fetching {args.sport.upper()} odds...")
    markets = fetch_odds(args.sport, use_cache=not args.no_cache)

    if not markets:
        print_error(f"No odds data available for {args.sport}")
        return 1

    print_info(f"Found {len(markets)} markets")

    # Show arbitrage or +EV bets
    if args.arb:
        return handle_arbitrage(markets, args.arb_stake)
    else:
        return handle_ev_bets(markets, args)


def handle_devig(odds_list: list[int], method: str) -> int:
    """Handle de-vig command for specific odds."""
    from models import Odds

    print_header("De-Vig Analysis")

    # Convert American odds to implied probabilities
    implied_probs = []
    for american in odds_list:
        odds = Odds(bookmaker="input", american=american)
        implied_probs.append(odds.implied_prob)

    print(f"\nInput odds: {' / '.join(str(o) for o in odds_list)}")
    print(f"Implied probs: {' / '.join(f'{p*100:.2f}%' for p in implied_probs)}")
    print(f"Total implied: {sum(implied_probs)*100:.2f}% (vig: {(sum(implied_probs)-1)*100:.2f}%)")

    # Calculate all methods
    results = {}
    for name, func in DEVIG_METHODS.items():
        if name == "weighted":
            results[name] = func(implied_probs)
        else:
            results[name] = func(implied_probs)

    display_devig_comparison(implied_probs, results)

    # Show fair odds
    print("\nFair American odds:")
    for method_name, probs in results.items():
        fair_odds = []
        for p in probs:
            if p >= 0.5:
                fair_odds.append(int(-100 * p / (1 - p)))
            else:
                fair_odds.append(int(100 * (1 - p) / p))
        print(f"  {method_name.title()}: {' / '.join(f'{o:+d}' for o in fair_odds)}")

    return 0


def handle_arbitrage(markets: list[tuple[Market, Market | None]], total_stake: float) -> int:
    """Handle arbitrage detection."""
    print_header("Arbitrage Detection")

    # Extract unique markets for arb detection
    all_markets = []
    seen = set()
    for market, _ in markets:
        key = f"{market.event}_{market.selection}"
        if key not in seen:
            all_markets.append(market)
            seen.add(key)

    opportunities = find_arbitrage(all_markets, min_profit=0.5, total_stake=total_stake)
    display_arbitrage(opportunities, total_stake)

    return 0


def handle_ev_bets(markets: list[tuple[Market, Market | None]], args) -> int:
    """Handle +EV bet finding."""
    print_header(f"+EV Analysis ({args.sport.upper()})")

    bets = find_ev_bets(
        markets=markets,
        bankroll=args.bankroll,
        min_ev=args.min_ev,
        kelly_fraction=args.kelly,
        devig_method=args.method,
    )

    # Scale exposure if needed
    if bets:
        from kelly import kelly_criterion
        kelly_results = [
            kelly_criterion(
                b.fair_prob,
                b.best_odds.decimal,
                args.bankroll,
                args.kelly,
            )
            for b in bets
        ]
        scaled_stakes = scale_exposure(kelly_results, args.bankroll, config.max_total_exposure)

        # Update bets with scaled stakes
        for bet, stake in zip(bets, scaled_stakes):
            bet.recommended_stake = stake

    display_bets(bets, args.bankroll)

    return 0


if __name__ == "__main__":
    sys.exit(main())

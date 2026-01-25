"""Arbitrage opportunity detection across sportsbooks."""

from models import Market, Odds, ArbitrageOpportunity


def find_arbitrage(
    markets: list[Market],
    min_profit: float = 0.5,
    total_stake: float = 1000.0,
) -> list[ArbitrageOpportunity]:
    """
    Find arbitrage opportunities across a set of related markets.

    An arbitrage exists when the sum of best implied probabilities
    across all outcomes is less than 1.0.

    Args:
        markets: List of markets representing all outcomes of an event
                 (e.g., [home_ml, away_ml] or [home, draw, away])
        min_profit: Minimum profit percentage to report
        total_stake: Total amount to stake across all outcomes

    Returns:
        List of ArbitrageOpportunity objects
    """
    opportunities = []

    # Group markets by event
    events = _group_by_event(markets)

    for event_key, event_markets in events.items():
        arb = _check_arbitrage(event_markets, min_profit, total_stake)
        if arb:
            opportunities.append(arb)

    # Sort by profit descending
    opportunities.sort(key=lambda a: a.profit_percent, reverse=True)

    return opportunities


def _group_by_event(markets: list[Market]) -> dict[str, list[Market]]:
    """Group markets by event and market type."""
    events: dict[str, list[Market]] = {}

    for market in markets:
        # Create key from event + market type + point (if applicable)
        point_str = f"_{market.point}" if market.point is not None else ""
        key = f"{market.event}_{market.market_type}{point_str}"

        if key not in events:
            events[key] = []
        events[key].append(market)

    return events


def _check_arbitrage(
    markets: list[Market],
    min_profit: float,
    total_stake: float,
) -> ArbitrageOpportunity | None:
    """Check if arbitrage exists for a set of outcome markets."""
    if len(markets) < 2:
        return None

    # Get best odds for each outcome
    best_odds_per_outcome: list[tuple[str, Odds]] = []

    for market in markets:
        best = market.best_odds()
        if not best:
            return None
        best_odds_per_outcome.append((market.selection, best))

    # Calculate total implied probability
    total_implied = sum(odds.implied_prob for _, odds in best_odds_per_outcome)

    # Arbitrage exists if total < 1.0
    if total_implied >= 1.0:
        return None

    profit_percent = ((1.0 / total_implied) - 1) * 100

    if profit_percent < min_profit:
        return None

    # Calculate optimal stakes
    stakes = _calculate_arb_stakes(best_odds_per_outcome, total_stake)

    return ArbitrageOpportunity(
        sport=markets[0].sport,
        event=markets[0].event,
        market_type=markets[0].market_type,
        selections=best_odds_per_outcome,
        total_implied=total_implied,
        profit_percent=profit_percent,
        stakes=stakes,
    )


def _calculate_arb_stakes(
    selections: list[tuple[str, Odds]],
    total_stake: float,
) -> list[tuple[str, str, float]]:
    """
    Calculate optimal stake distribution for arbitrage.

    Stakes are distributed so that profit is equal regardless
    of which outcome wins.

    stake_i = total_stake / (decimal_i * sum(1/decimal_j for all j))
    """
    total_inverse = sum(1 / odds.decimal for _, odds in selections)

    stakes = []
    for selection, odds in selections:
        stake = total_stake / (odds.decimal * total_inverse)
        stakes.append((selection, odds.bookmaker, round(stake, 2)))

    return stakes


def calculate_arb_profit(
    stakes: list[tuple[str, str, float]],
    odds_list: list[tuple[str, Odds]],
) -> dict[str, float]:
    """
    Calculate profit for each possible outcome.

    Returns dict mapping outcome to profit amount.
    Useful for verifying arb calculations.
    """
    # Create lookup for stakes
    stake_lookup = {selection: stake for selection, _, stake in stakes}

    total_staked = sum(stake for _, _, stake in stakes)
    profits = {}

    for selection, odds in odds_list:
        stake = stake_lookup.get(selection, 0)
        payout = stake * odds.decimal
        profit = payout - total_staked
        profits[selection] = round(profit, 2)

    return profits


def find_middles(
    spread_markets: list[Market],
    min_gap: float = 0.5,
) -> list[dict]:
    """
    Find middle opportunities in spread betting.

    A middle exists when you can bet both sides of a spread
    at different books where the spreads don't overlap.

    Example: Team A -2.5 at Book1, Team B +3.5 at Book2
    If Team A wins by exactly 3, both bets win.

    Args:
        spread_markets: List of spread markets
        min_gap: Minimum point gap to consider

    Returns:
        List of middle opportunities
    """
    middles = []

    # Group by event
    events = _group_by_event(spread_markets)

    for event_key, markets in events.items():
        if len(markets) < 2:
            continue

        # Find all spread combinations
        for i, market1 in enumerate(markets):
            for market2 in markets[i + 1:]:
                if market1.point is None or market2.point is None:
                    continue

                # Check if they're opposite sides
                if market1.selection == market2.selection:
                    continue

                # Calculate gap (accounting for which side is favorite)
                # Positive spread = underdog, negative = favorite
                gap = abs(market1.point) + abs(market2.point)

                # Check if there's a middle
                # For a middle: favorite spread + underdog spread > 0
                if market1.point < 0 and market2.point > 0:
                    middle_size = market2.point + market1.point
                elif market1.point > 0 and market2.point < 0:
                    middle_size = market1.point + market2.point
                else:
                    continue

                if middle_size >= min_gap:
                    best1 = market1.best_odds()
                    best2 = market2.best_odds()

                    if best1 and best2:
                        middles.append({
                            "event": market1.event,
                            "side1": f"{market1.selection} {market1.point:+.1f}",
                            "book1": best1.bookmaker,
                            "odds1": best1.american,
                            "side2": f"{market2.selection} {market2.point:+.1f}",
                            "book2": best2.bookmaker,
                            "odds2": best2.american,
                            "middle_size": middle_size,
                        })

    # Sort by middle size descending
    middles.sort(key=lambda m: m["middle_size"], reverse=True)

    return middles

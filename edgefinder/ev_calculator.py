"""Expected Value calculations with sharp book weighting."""

from models import Market, Odds, Bet
from devig import devig
from kelly import kelly_criterion
from config import config


def calculate_fair_probability(
    market: Market,
    opposing_market: Market | None = None,
    method: str = "weighted",
) -> float:
    """
    Calculate fair probability for a market using sharp book weighting.

    Uses weighted average of de-vigged probabilities from multiple books,
    with sharper books weighted more heavily.

    Args:
        market: The market to calculate fair prob for
        opposing_market: The opposing side (e.g., other team's moneyline)
        method: De-vig method to use

    Returns:
        Fair probability for the selection
    """
    if not market.odds_list:
        return 0.0

    # If we have opposing market, use paired de-vig for more accuracy
    if opposing_market and opposing_market.odds_list:
        return _paired_fair_probability(market, opposing_market, method)

    # Otherwise, estimate from single side
    return _single_side_fair_probability(market)


def _paired_fair_probability(
    market: Market,
    opposing_market: Market,
    method: str,
) -> float:
    """Calculate fair prob using both sides of the market."""
    weighted_prob = 0.0
    total_weight = 0.0

    for odds in market.odds_list:
        # Find matching odds from opposing market
        opposing_odds = opposing_market.get_odds_by_book(odds.bookmaker)
        if not opposing_odds:
            continue

        # De-vig this book's line
        implied_probs = [odds.implied_prob, opposing_odds.implied_prob]
        result = devig(implied_probs, method=method)

        # Weight by book sharpness
        weight = config.get_book_weight(odds.bookmaker)
        weighted_prob += result.fair_probs[0] * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return weighted_prob / total_weight


def _single_side_fair_probability(market: Market) -> float:
    """Estimate fair prob from single side using weighted average."""
    weighted_prob = 0.0
    total_weight = 0.0

    for odds in market.odds_list:
        # Without opposing side, we can only use implied prob
        # Apply a rough vig adjustment (assume ~5% total vig)
        estimated_fair = odds.implied_prob / 1.025

        weight = config.get_book_weight(odds.bookmaker)
        weighted_prob += estimated_fair * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return weighted_prob / total_weight


def calculate_ev(fair_prob: float, decimal_odds: float) -> float:
    """
    Calculate Expected Value percentage.

    EV% = (Fair Probability × Decimal Odds) - 1

    Args:
        fair_prob: Fair/true probability of winning
        decimal_odds: Decimal odds being offered

    Returns:
        EV as a percentage (e.g., 5.0 means +5% EV)
    """
    if fair_prob <= 0 or decimal_odds <= 1:
        return 0.0

    ev = (fair_prob * decimal_odds) - 1
    return ev * 100  # Convert to percentage


def find_ev_bets(
    markets: list[tuple[Market, Market | None]],
    bankroll: float = 1000.0,
    min_ev: float = 1.0,
    kelly_fraction: float = 0.25,
    devig_method: str = "weighted",
) -> list[Bet]:
    """
    Find all +EV betting opportunities.

    Args:
        markets: List of (market, opposing_market) tuples
        bankroll: Total bankroll for sizing
        min_ev: Minimum EV% to include
        kelly_fraction: Kelly fraction to use
        devig_method: De-vig method to use

    Returns:
        List of Bet objects sorted by EV% descending
    """
    bets = []

    for market, opposing in markets:
        if not market.odds_list:
            continue

        # Calculate fair probability
        fair_prob = calculate_fair_probability(market, opposing, devig_method)
        if fair_prob <= 0:
            continue

        # Get best available odds
        best = market.best_odds()
        if not best:
            continue

        # Calculate EV
        ev_percent = calculate_ev(fair_prob, best.decimal)

        if ev_percent < min_ev:
            continue

        # Calculate Kelly sizing
        kelly_result = kelly_criterion(
            win_prob=fair_prob,
            decimal_odds=best.decimal,
            bankroll=bankroll,
            fraction=kelly_fraction,
        )

        bet = Bet(
            market=market,
            best_odds=best,
            fair_prob=fair_prob,
            ev_percent=ev_percent,
            kelly_fraction=kelly_result.recommended_fraction,
            recommended_stake=kelly_result.recommended_stake,
        )
        bets.append(bet)

    # Sort by EV descending
    bets.sort(key=lambda b: b.ev_percent, reverse=True)

    return bets


def calculate_clv(
    bet_odds: float,
    closing_odds: float,
) -> float:
    """
    Calculate Closing Line Value.

    CLV measures how much better your odds were compared to
    the closing line (final odds before event starts).

    Args:
        bet_odds: Decimal odds when bet was placed
        closing_odds: Decimal odds at close

    Returns:
        CLV as a percentage
    """
    if closing_odds <= 1:
        return 0.0

    # Convert to implied probabilities
    bet_implied = 1 / bet_odds
    close_implied = 1 / closing_odds

    # CLV = (closing implied - bet implied) / bet implied
    clv = (close_implied - bet_implied) / bet_implied
    return clv * 100

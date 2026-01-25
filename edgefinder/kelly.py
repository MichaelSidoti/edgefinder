"""Kelly Criterion bet sizing calculations."""

from dataclasses import dataclass


@dataclass
class KellyResult:
    """Result from Kelly sizing calculation."""
    full_kelly: float
    recommended_fraction: float
    recommended_stake: float
    edge: float
    odds_decimal: float


def kelly_criterion(
    win_prob: float,
    decimal_odds: float,
    bankroll: float,
    fraction: float = 0.25,
    max_bet_percent: float = 0.05,
) -> KellyResult:
    """
    Calculate optimal bet size using Kelly Criterion.

    Formula: f* = (bp - q) / b
    where:
        b = decimal odds - 1 (net odds)
        p = probability of winning
        q = probability of losing (1 - p)

    Args:
        win_prob: Estimated probability of winning (0-1)
        decimal_odds: Decimal odds offered
        bankroll: Total bankroll
        fraction: Kelly fraction to use (0.25 = quarter Kelly)
        max_bet_percent: Maximum bet as percentage of bankroll

    Returns:
        KellyResult with sizing information
    """
    if win_prob <= 0 or win_prob >= 1:
        return KellyResult(
            full_kelly=0,
            recommended_fraction=0,
            recommended_stake=0,
            edge=0,
            odds_decimal=decimal_odds,
        )

    b = decimal_odds - 1  # Net odds
    p = win_prob
    q = 1 - p

    # Full Kelly formula
    full_kelly = (b * p - q) / b if b > 0 else 0

    # If negative (no edge), don't bet
    if full_kelly <= 0:
        return KellyResult(
            full_kelly=0,
            recommended_fraction=0,
            recommended_stake=0,
            edge=(b * p - q),
            odds_decimal=decimal_odds,
        )

    # Apply fractional Kelly
    fractional_kelly = full_kelly * fraction

    # Cap at max bet percent
    capped_fraction = min(fractional_kelly, max_bet_percent)

    # Calculate stake
    stake = bankroll * capped_fraction

    return KellyResult(
        full_kelly=full_kelly,
        recommended_fraction=capped_fraction,
        recommended_stake=round(stake, 2),
        edge=(b * p - q),
        odds_decimal=decimal_odds,
    )


def scale_exposure(
    kelly_results: list[KellyResult],
    bankroll: float,
    max_total_exposure: float = 0.25,
) -> list[float]:
    """
    Scale bet sizes if total exposure exceeds threshold.

    Args:
        kelly_results: List of Kelly calculation results
        bankroll: Total bankroll
        max_total_exposure: Maximum total exposure as fraction of bankroll

    Returns:
        List of scaled stake amounts
    """
    total_fraction = sum(r.recommended_fraction for r in kelly_results)

    if total_fraction <= max_total_exposure:
        return [r.recommended_stake for r in kelly_results]

    # Scale down proportionally
    scale_factor = max_total_exposure / total_fraction

    return [
        round(r.recommended_stake * scale_factor, 2)
        for r in kelly_results
    ]


def kelly_with_correlation(
    win_prob: float,
    decimal_odds: float,
    bankroll: float,
    correlation: float = 0.0,
    num_correlated_bets: int = 1,
    fraction: float = 0.25,
) -> KellyResult:
    """
    Kelly sizing adjusted for correlated bets.

    When bets are correlated (e.g., same game parlays,
    multiple bets on same team), we should reduce exposure.

    Args:
        win_prob: Probability of winning
        decimal_odds: Decimal odds
        bankroll: Total bankroll
        correlation: Correlation coefficient with other bets (0-1)
        num_correlated_bets: Number of correlated bets
        fraction: Base Kelly fraction

    Returns:
        KellyResult with adjusted sizing
    """
    # Adjust fraction based on correlation
    # Higher correlation = smaller bets
    correlation_factor = 1 / (1 + correlation * (num_correlated_bets - 1))
    adjusted_fraction = fraction * correlation_factor

    return kelly_criterion(
        win_prob=win_prob,
        decimal_odds=decimal_odds,
        bankroll=bankroll,
        fraction=adjusted_fraction,
    )

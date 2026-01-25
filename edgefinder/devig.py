"""De-vig algorithms to extract fair probabilities from bookmaker odds."""

from dataclasses import dataclass
from typing import Callable
import math

from models import DevigResult


def multiplicative_devig(implied_probs: list[float]) -> list[float]:
    """
    Multiplicative de-vig: Remove vig proportionally.
    Each probability is divided by the sum to normalize to 1.0.
    """
    total = sum(implied_probs)
    if total == 0:
        return implied_probs
    return [p / total for p in implied_probs]


def additive_devig(implied_probs: list[float]) -> list[float]:
    """
    Additive de-vig: Remove vig equally from each side.
    Subtract (total - 1) / n from each probability.
    """
    n = len(implied_probs)
    if n == 0:
        return implied_probs
    total = sum(implied_probs)
    vig_per_side = (total - 1) / n
    fair_probs = [max(0.001, p - vig_per_side) for p in implied_probs]
    # Normalize to ensure sum is exactly 1
    total_fair = sum(fair_probs)
    return [p / total_fair for p in fair_probs]


def power_devig(implied_probs: list[float]) -> list[float]:
    """
    Power de-vig: Find exponent k such that sum(p^k) = 1.
    Uses binary search to find the correct power.
    """
    if len(implied_probs) < 2:
        return implied_probs

    def sum_of_powers(probs: list[float], k: float) -> float:
        return sum(p ** k for p in probs)

    # Binary search for k
    low, high = 0.5, 2.0
    for _ in range(50):  # Enough iterations for convergence
        mid = (low + high) / 2
        total = sum_of_powers(implied_probs, mid)
        if total < 1:
            high = mid
        else:
            low = mid

    k = (low + high) / 2
    fair_probs = [p ** k for p in implied_probs]
    # Normalize
    total = sum(fair_probs)
    return [p / total for p in fair_probs]


def shin_devig(implied_probs: list[float]) -> list[float]:
    """
    Shin method: Account for insider trading (favorite-longshot bias).
    Assumes a proportion z of bets come from informed bettors.
    More accurate for markets with large favorites.
    """
    if len(implied_probs) != 2:
        # Shin is designed for 2-way markets, fall back to multiplicative
        return multiplicative_devig(implied_probs)

    p1, p2 = implied_probs
    total = p1 + p2

    # Calculate Shin's z (proportion of insider money)
    # z = (sum - 1) / (n - 1) simplified for 2 outcomes
    # Using the quadratic formula solution
    discriminant = (total - 1) ** 2 + 4 * (total - 1) * p1 * p2 / total
    if discriminant < 0:
        return multiplicative_devig(implied_probs)

    z = (total - 1 - math.sqrt(discriminant)) / (2 * (total - 1)) if total != 1 else 0
    z = max(0, min(z, 0.5))  # Bound z between 0 and 0.5

    # Calculate fair probabilities
    if z == 0 or total == 1:
        return multiplicative_devig(implied_probs)

    # Shin formula: fair_p = (sqrt(z^2 + 4*(1-z)*implied^2/total) - z) / (2*(1-z))
    fair_probs = []
    for p in implied_probs:
        inner = z ** 2 + 4 * (1 - z) * (p ** 2) / total
        fair_p = (math.sqrt(inner) - z) / (2 * (1 - z)) if (1 - z) != 0 else p
        fair_probs.append(max(0.001, fair_p))

    # Normalize
    total_fair = sum(fair_probs)
    return [p / total_fair for p in fair_probs]


def weighted_devig(
    implied_probs: list[float],
    weights: list[float] | None = None
) -> list[float]:
    """
    Weighted de-vig: Combine multiple methods based on weights.
    Default weights favor Shin for 2-way and Power for multi-way.
    """
    if weights is None:
        if len(implied_probs) == 2:
            # For 2-way markets, weight Shin higher
            weights = [0.2, 0.1, 0.3, 0.4, 0.0]  # mult, add, power, shin, weighted(ignored)
        else:
            # For multi-way, weight Power higher
            weights = [0.3, 0.1, 0.5, 0.1, 0.0]

    methods = [
        multiplicative_devig,
        additive_devig,
        power_devig,
        shin_devig,
    ]

    # Calculate fair probs from each method
    results = [method(implied_probs) for method in methods[:4]]

    # Weighted average
    n = len(implied_probs)
    fair_probs = [0.0] * n
    total_weight = sum(weights[:4])

    for i in range(n):
        for j, result in enumerate(results):
            fair_probs[i] += result[i] * weights[j] / total_weight

    # Normalize
    total = sum(fair_probs)
    return [p / total for p in fair_probs]


DEVIG_METHODS: dict[str, Callable[[list[float]], list[float]]] = {
    "multiplicative": multiplicative_devig,
    "additive": additive_devig,
    "power": power_devig,
    "shin": shin_devig,
    "weighted": weighted_devig,
}


def devig(
    implied_probs: list[float],
    method: str = "weighted"
) -> DevigResult:
    """
    De-vig implied probabilities using the specified method.

    Args:
        implied_probs: List of implied probabilities from bookmaker odds
        method: De-vig method to use

    Returns:
        DevigResult with fair probabilities and metadata
    """
    if method not in DEVIG_METHODS:
        raise ValueError(f"Unknown de-vig method: {method}. Available: {list(DEVIG_METHODS.keys())}")

    devig_func = DEVIG_METHODS[method]
    fair_probs = devig_func(implied_probs)

    original_total = sum(implied_probs)
    vig_removed = original_total - 1 if original_total > 1 else 0

    return DevigResult(
        fair_probs=fair_probs,
        method=method,
        original_implied=implied_probs,
        vig_removed=vig_removed,
    )

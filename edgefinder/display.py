"""Terminal output formatting with rich tables and colors."""

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from models import Bet, ArbitrageOpportunity


def get_console():
    """Get rich Console or None if not available."""
    if RICH_AVAILABLE:
        return Console()
    return None


def format_american_odds(odds: int) -> str:
    """Format American odds with +/- sign."""
    if odds > 0:
        return f"+{odds}"
    return str(odds)


def format_ev(ev: float) -> str:
    """Format EV percentage with color indicator."""
    return f"+{ev:.2f}%"


def format_probability(prob: float) -> str:
    """Format probability as percentage."""
    return f"{prob * 100:.1f}%"


def format_stake(stake: float) -> str:
    """Format stake as currency."""
    return f"${stake:.2f}"


def display_bets(bets: list[Bet], bankroll: float) -> None:
    """Display list of +EV bets in a formatted table."""
    if not bets:
        print("\nNo +EV bets found matching your criteria.")
        return

    if RICH_AVAILABLE:
        _display_bets_rich(bets, bankroll)
    else:
        _display_bets_plain(bets, bankroll)


def _display_bets_rich(bets: list[Bet], bankroll: float) -> None:
    """Display bets using rich library."""
    console = Console()

    table = Table(
        title=f"[bold green]+EV Betting Opportunities[/bold green]\nBankroll: ${bankroll:,.2f}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Event", style="white", width=35)
    table.add_column("Selection", style="yellow", width=20)
    table.add_column("Best Odds", justify="right", style="green")
    table.add_column("Book", style="blue")
    table.add_column("Fair Odds", justify="right", style="dim")
    table.add_column("EV%", justify="right", style="bold green")
    table.add_column("Stake", justify="right", style="cyan")

    for bet in bets:
        ev_style = "bold green" if bet.ev_percent >= 5 else "green"

        table.add_row(
            bet.market.event[:33] + ".." if len(bet.market.event) > 35 else bet.market.event,
            bet.market.selection[:18] + ".." if len(bet.market.selection) > 20 else bet.market.selection,
            format_american_odds(bet.best_odds.american),
            bet.best_odds.bookmaker.title(),
            format_american_odds(bet.fair_american),
            f"[{ev_style}]+{bet.ev_percent:.2f}%[/{ev_style}]",
            format_stake(bet.recommended_stake),
        )

    console.print()
    console.print(table)

    # Summary
    total_stake = sum(b.recommended_stake for b in bets)
    avg_ev = sum(b.ev_percent for b in bets) / len(bets)

    summary = Panel(
        f"[bold]Total Bets:[/bold] {len(bets)}  |  "
        f"[bold]Total Stake:[/bold] ${total_stake:.2f}  |  "
        f"[bold]Avg EV:[/bold] +{avg_ev:.2f}%  |  "
        f"[bold]Exposure:[/bold] {total_stake/bankroll*100:.1f}%",
        title="Summary",
        border_style="green",
    )
    console.print(summary)


def _display_bets_plain(bets: list[Bet], bankroll: float) -> None:
    """Display bets without rich library."""
    print(f"\n{'='*80}")
    print(f"+EV BETTING OPPORTUNITIES | Bankroll: ${bankroll:,.2f}")
    print(f"{'='*80}")

    print(f"\n{'Event':<35} {'Selection':<20} {'Odds':>8} {'Book':<12} {'EV%':>8} {'Stake':>10}")
    print("-" * 95)

    for bet in bets:
        event = bet.market.event[:33] + ".." if len(bet.market.event) > 35 else bet.market.event
        selection = bet.market.selection[:18] + ".." if len(bet.market.selection) > 20 else bet.market.selection

        print(
            f"{event:<35} "
            f"{selection:<20} "
            f"{format_american_odds(bet.best_odds.american):>8} "
            f"{bet.best_odds.bookmaker:<12} "
            f"+{bet.ev_percent:>6.2f}% "
            f"{format_stake(bet.recommended_stake):>10}"
        )

    # Summary
    total_stake = sum(b.recommended_stake for b in bets)
    avg_ev = sum(b.ev_percent for b in bets) / len(bets)

    print("-" * 95)
    print(f"Total: {len(bets)} bets | Stake: ${total_stake:.2f} | Avg EV: +{avg_ev:.2f}% | Exposure: {total_stake/bankroll*100:.1f}%")


def display_arbitrage(opportunities: list[ArbitrageOpportunity], total_stake: float) -> None:
    """Display arbitrage opportunities."""
    if not opportunities:
        print("\nNo arbitrage opportunities found.")
        return

    if RICH_AVAILABLE:
        _display_arb_rich(opportunities, total_stake)
    else:
        _display_arb_plain(opportunities, total_stake)


def _display_arb_rich(opportunities: list[ArbitrageOpportunity], total_stake: float) -> None:
    """Display arbitrage using rich library."""
    console = Console()

    table = Table(
        title=f"[bold yellow]Arbitrage Opportunities[/bold yellow]\nStake per arb: ${total_stake:,.2f}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Event", style="white", width=35)
    table.add_column("Selection 1", style="yellow")
    table.add_column("Book 1", style="blue")
    table.add_column("Stake 1", justify="right")
    table.add_column("Selection 2", style="yellow")
    table.add_column("Book 2", style="blue")
    table.add_column("Stake 2", justify="right")
    table.add_column("Profit", justify="right", style="bold green")

    for arb in opportunities:
        if len(arb.stakes) >= 2:
            profit = total_stake * (arb.profit_percent / 100)
            table.add_row(
                arb.event[:33] + ".." if len(arb.event) > 35 else arb.event,
                arb.stakes[0][0][:15],
                arb.stakes[0][1].title(),
                f"${arb.stakes[0][2]:.2f}",
                arb.stakes[1][0][:15],
                arb.stakes[1][1].title(),
                f"${arb.stakes[1][2]:.2f}",
                f"+${profit:.2f} ({arb.profit_percent:.2f}%)",
            )

    console.print()
    console.print(table)


def _display_arb_plain(opportunities: list[ArbitrageOpportunity], total_stake: float) -> None:
    """Display arbitrage without rich library."""
    print(f"\n{'='*90}")
    print(f"ARBITRAGE OPPORTUNITIES | Stake per arb: ${total_stake:,.2f}")
    print(f"{'='*90}")

    for arb in opportunities:
        profit = total_stake * (arb.profit_percent / 100)
        print(f"\n{arb.event}")
        print(f"  Profit: +${profit:.2f} ({arb.profit_percent:.2f}%)")
        for selection, book, stake in arb.stakes:
            print(f"  - {selection}: ${stake:.2f} @ {book}")


def display_devig_comparison(implied_probs: list[float], results: dict) -> None:
    """Display comparison of different de-vig methods."""
    if RICH_AVAILABLE:
        _display_devig_rich(implied_probs, results)
    else:
        _display_devig_plain(implied_probs, results)


def _display_devig_rich(implied_probs: list[float], results: dict) -> None:
    """Display de-vig comparison using rich."""
    console = Console()

    table = Table(
        title="[bold]De-Vig Method Comparison[/bold]",
        box=box.ROUNDED,
    )

    table.add_column("Method", style="cyan")
    table.add_column("Side 1", justify="right")
    table.add_column("Side 2", justify="right")
    table.add_column("Total", justify="right")

    # Original implied
    table.add_row(
        "Original (with vig)",
        f"{implied_probs[0]*100:.2f}%",
        f"{implied_probs[1]*100:.2f}%" if len(implied_probs) > 1 else "-",
        f"{sum(implied_probs)*100:.2f}%",
        style="dim",
    )

    for method, probs in results.items():
        table.add_row(
            method.title(),
            f"{probs[0]*100:.2f}%",
            f"{probs[1]*100:.2f}%" if len(probs) > 1 else "-",
            f"{sum(probs)*100:.2f}%",
        )

    console.print()
    console.print(table)


def _display_devig_plain(implied_probs: list[float], results: dict) -> None:
    """Display de-vig comparison without rich."""
    print("\nDe-Vig Method Comparison")
    print("-" * 50)
    print(f"{'Method':<20} {'Side 1':>10} {'Side 2':>10} {'Total':>10}")
    print("-" * 50)

    print(f"{'Original (vig)':<20} {implied_probs[0]*100:>9.2f}% {implied_probs[1]*100 if len(implied_probs) > 1 else 0:>9.2f}% {sum(implied_probs)*100:>9.2f}%")

    for method, probs in results.items():
        p2 = probs[1]*100 if len(probs) > 1 else 0
        print(f"{method.title():<20} {probs[0]*100:>9.2f}% {p2:>9.2f}% {sum(probs)*100:>9.2f}%")


def print_header(text: str) -> None:
    """Print a styled header."""
    if RICH_AVAILABLE:
        console = Console()
        console.print(Panel(text, style="bold blue"))
    else:
        print(f"\n{'='*60}")
        print(f"  {text}")
        print(f"{'='*60}")


def print_error(text: str) -> None:
    """Print an error message."""
    if RICH_AVAILABLE:
        console = Console()
        console.print(f"[bold red]Error:[/bold red] {text}")
    else:
        print(f"Error: {text}")


def print_success(text: str) -> None:
    """Print a success message."""
    if RICH_AVAILABLE:
        console = Console()
        console.print(f"[bold green]{text}[/bold green]")
    else:
        print(text)


def print_info(text: str) -> None:
    """Print an info message."""
    if RICH_AVAILABLE:
        console = Console()
        console.print(f"[dim]{text}[/dim]")
    else:
        print(text)

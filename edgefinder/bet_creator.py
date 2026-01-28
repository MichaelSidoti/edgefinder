"""Interactive Kelly bet creator for manual bet sizing."""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from kelly import kelly_criterion, KellyResult
from models import Odds


BETS_FILE = Path(__file__).parent / "my_bets.json"


@dataclass
class Bet:
    """A manually created bet."""
    id: int
    event: str
    selection: str
    american_odds: int
    win_prob: float
    stake: float
    kelly_fraction: float
    ev_percent: float
    created_at: str
    status: str = "pending"  # pending, won, lost, void
    result_amount: float = 0.0
    notes: str = ""


def american_to_decimal(american: int) -> float:
    """Convert American odds to decimal."""
    if american > 0:
        return 1 + american / 100
    else:
        return 1 + 100 / abs(american)


def decimal_to_american(decimal: float) -> int:
    """Convert decimal odds to American."""
    if decimal >= 2.0:
        return int((decimal - 1) * 100)
    else:
        return int(-100 / (decimal - 1))


def calc_ev(win_prob: float, decimal_odds: float) -> float:
    """Calculate expected value percentage."""
    ev = (win_prob * (decimal_odds - 1)) - (1 - win_prob)
    return ev * 100


def load_bets() -> list[dict]:
    """Load saved bets from file."""
    if not BETS_FILE.exists():
        return []
    try:
        with open(BETS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save_bets(bets: list[dict]) -> None:
    """Save bets to file."""
    with open(BETS_FILE, "w") as f:
        json.dump(bets, f, indent=2)


def get_next_id(bets: list[dict]) -> int:
    """Get next available bet ID."""
    if not bets:
        return 1
    return max(b["id"] for b in bets) + 1


def create_bet(
    event: str,
    selection: str,
    american_odds: int,
    win_prob: float,
    bankroll: float,
    kelly_frac: float = 0.25,
    max_bet_pct: float = 0.05,
    notes: str = "",
) -> Bet:
    """Create a new bet with Kelly sizing."""
    decimal_odds = american_to_decimal(american_odds)

    result = kelly_criterion(
        win_prob=win_prob,
        decimal_odds=decimal_odds,
        bankroll=bankroll,
        fraction=kelly_frac,
        max_bet_percent=max_bet_pct,
    )

    ev_pct = calc_ev(win_prob, decimal_odds)

    bets = load_bets()
    bet = Bet(
        id=get_next_id(bets),
        event=event,
        selection=selection,
        american_odds=american_odds,
        win_prob=win_prob,
        stake=result.recommended_stake,
        kelly_fraction=result.recommended_fraction,
        ev_percent=ev_pct,
        created_at=datetime.now().isoformat(),
        notes=notes,
    )

    bets.append(asdict(bet))
    save_bets(bets)

    return bet


def quick_size(
    american_odds: int,
    win_prob: float,
    bankroll: float,
    kelly_frac: float = 0.25,
) -> dict:
    """Quick Kelly sizing without saving - just returns the math."""
    decimal_odds = american_to_decimal(american_odds)

    result = kelly_criterion(
        win_prob=win_prob,
        decimal_odds=decimal_odds,
        bankroll=bankroll,
        fraction=kelly_frac,
    )

    ev_pct = calc_ev(win_prob, decimal_odds)
    implied_prob = Odds(bookmaker="calc", american=american_odds).implied_prob

    return {
        "american_odds": american_odds,
        "decimal_odds": round(decimal_odds, 3),
        "implied_prob": round(implied_prob * 100, 2),
        "your_prob": round(win_prob * 100, 2),
        "edge": round((win_prob - implied_prob) * 100, 2),
        "ev_percent": round(ev_pct, 2),
        "full_kelly": round(result.full_kelly * 100, 2),
        "recommended_fraction": round(result.recommended_fraction * 100, 2),
        "recommended_stake": result.recommended_stake,
    }


def list_pending_bets() -> list[dict]:
    """Get all pending bets."""
    bets = load_bets()
    return [b for b in bets if b["status"] == "pending"]


def mark_bet_result(bet_id: int, won: bool, void: bool = False) -> dict | None:
    """Mark a bet as won, lost, or void."""
    bets = load_bets()

    for bet in bets:
        if bet["id"] == bet_id:
            if void:
                bet["status"] = "void"
                bet["result_amount"] = 0
            elif won:
                bet["status"] = "won"
                decimal = american_to_decimal(bet["american_odds"])
                bet["result_amount"] = round(bet["stake"] * (decimal - 1), 2)
            else:
                bet["status"] = "lost"
                bet["result_amount"] = -bet["stake"]

            save_bets(bets)
            return bet

    return None


def get_stats() -> dict:
    """Get betting statistics."""
    bets = load_bets()

    if not bets:
        return {"total_bets": 0}

    settled = [b for b in bets if b["status"] in ("won", "lost")]
    pending = [b for b in bets if b["status"] == "pending"]

    total_staked = sum(b["stake"] for b in settled)
    total_won = sum(b["result_amount"] for b in settled)
    wins = len([b for b in settled if b["status"] == "won"])
    losses = len([b for b in settled if b["status"] == "lost"])

    return {
        "total_bets": len(bets),
        "pending": len(pending),
        "settled": len(settled),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(settled) * 100, 1) if settled else 0,
        "total_staked": round(total_staked, 2),
        "total_profit": round(total_won, 2),
        "roi": round(total_won / total_staked * 100, 2) if total_staked > 0 else 0,
        "pending_exposure": round(sum(b["stake"] for b in pending), 2),
    }


def interactive():
    """Run interactive bet creator."""
    print("\n" + "=" * 50)
    print("  KELLY BET CREATOR")
    print("=" * 50)

    # Get bankroll
    try:
        bankroll = float(input("\nBankroll [$1000]: ").strip() or "1000")
    except ValueError:
        bankroll = 1000

    try:
        kelly_frac = float(input("Kelly fraction [0.25]: ").strip() or "0.25")
    except ValueError:
        kelly_frac = 0.25

    while True:
        print("\n" + "-" * 40)
        print("Commands: [n]ew bet, [q]uick size, [l]ist pending, [s]tats, [r]esult, [e]xit")
        cmd = input("> ").strip().lower()

        if cmd in ("e", "exit", "quit"):
            break

        elif cmd in ("n", "new"):
            print("\n--- New Bet ---")
            event = input("Event (e.g., 'Lakers vs Celtics'): ").strip()
            selection = input("Selection (e.g., 'Lakers ML'): ").strip()

            try:
                odds = int(input("American odds (e.g., -150 or +200): ").strip())
                prob = float(input("Your estimated win probability (0-100): ").strip()) / 100
            except ValueError:
                print("Invalid input")
                continue

            if prob <= 0 or prob >= 1:
                print("Probability must be between 0 and 100")
                continue

            notes = input("Notes (optional): ").strip()

            bet = create_bet(
                event=event,
                selection=selection,
                american_odds=odds,
                win_prob=prob,
                bankroll=bankroll,
                kelly_frac=kelly_frac,
                notes=notes,
            )

            print(f"\n  Bet #{bet.id} created!")
            print(f"  EV: +{bet.ev_percent:.2f}%")
            print(f"  Recommended stake: ${bet.stake:.2f}")

        elif cmd in ("q", "quick"):
            print("\n--- Quick Size ---")
            try:
                odds = int(input("American odds: ").strip())
                prob = float(input("Your win probability (0-100): ").strip()) / 100
            except ValueError:
                print("Invalid input")
                continue

            result = quick_size(odds, prob, bankroll, kelly_frac)

            print(f"\n  Odds: {result['american_odds']} ({result['decimal_odds']})")
            print(f"  Implied prob: {result['implied_prob']}%")
            print(f"  Your prob: {result['your_prob']}%")
            print(f"  Edge: {result['edge']}%")
            print(f"  EV: +{result['ev_percent']:.2f}%")
            print(f"  Full Kelly: {result['full_kelly']}%")
            print(f"  Recommended: {result['recommended_fraction']}% = ${result['recommended_stake']:.2f}")

        elif cmd in ("l", "list"):
            pending = list_pending_bets()
            if not pending:
                print("\nNo pending bets")
            else:
                print(f"\n--- Pending Bets ({len(pending)}) ---")
                for b in pending:
                    odds_str = f"+{b['american_odds']}" if b['american_odds'] > 0 else str(b['american_odds'])
                    print(f"  #{b['id']}: {b['selection']} {odds_str} - ${b['stake']:.2f} (EV: +{b['ev_percent']:.2f}%)")
                    print(f"       {b['event']}")

        elif cmd in ("s", "stats"):
            stats = get_stats()
            if stats["total_bets"] == 0:
                print("\nNo bets recorded yet")
            else:
                print("\n--- Stats ---")
                print(f"  Total bets: {stats['total_bets']}")
                print(f"  Record: {stats['wins']}-{stats['losses']} ({stats['win_rate']}%)")
                print(f"  Total staked: ${stats['total_staked']:.2f}")
                print(f"  Profit/Loss: ${stats['total_profit']:.2f}")
                print(f"  ROI: {stats['roi']}%")
                print(f"  Pending exposure: ${stats['pending_exposure']:.2f}")

        elif cmd in ("r", "result"):
            try:
                bet_id = int(input("Bet ID: ").strip())
                outcome = input("Result [w]on/[l]ost/[v]oid: ").strip().lower()
            except ValueError:
                print("Invalid input")
                continue

            if outcome in ("w", "won"):
                bet = mark_bet_result(bet_id, won=True)
            elif outcome in ("l", "lost"):
                bet = mark_bet_result(bet_id, won=False)
            elif outcome in ("v", "void"):
                bet = mark_bet_result(bet_id, won=False, void=True)
            else:
                print("Invalid outcome")
                continue

            if bet:
                print(f"  Bet #{bet_id} marked as {bet['status']}: ${bet['result_amount']:+.2f}")
            else:
                print(f"  Bet #{bet_id} not found")

        else:
            print("Unknown command")

    print("\nGoodbye!")


if __name__ == "__main__":
    interactive()

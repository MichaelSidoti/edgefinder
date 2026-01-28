"""FastAPI web app for EdgeFinder."""

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import config
from odds_api import fetch_odds, fetch_player_props, get_available_sports
from ev_calculator import find_ev_bets
from arbitrage import find_arbitrage
from devig import devig, DEVIG_METHODS
from models import Odds
from bet_creator import quick_size, create_bet, list_pending_bets, mark_bet_result, get_stats, load_bets

app = FastAPI(
    title="EdgeFinder",
    description="Sports Betting Analytics API",
    version="1.0.0",
)


class BetResponse(BaseModel):
    event: str
    selection: str
    best_odds: int
    bookmaker: str
    fair_odds: int
    ev_percent: float
    recommended_stake: float
    player: str | None = None
    point: float | None = None
    market_type: str = "h2h"


class ArbitrageResponse(BaseModel):
    event: str
    profit_percent: float
    stakes: list[dict]


class DevigResponse(BaseModel):
    method: str
    original_implied: list[float]
    fair_probs: list[float]
    fair_odds: list[int]
    vig_removed: float


class KellySizeRequest(BaseModel):
    american_odds: int
    win_prob: float
    bankroll: float = 1000
    kelly_fraction: float = 0.25


class KellySizeResponse(BaseModel):
    american_odds: int
    decimal_odds: float
    implied_prob: float
    your_prob: float
    edge: float
    ev_percent: float
    full_kelly: float
    recommended_fraction: float
    recommended_stake: float


class CreateBetRequest(BaseModel):
    event: str
    selection: str
    american_odds: int
    win_prob: float
    bankroll: float = 1000
    kelly_fraction: float = 0.25
    notes: str = ""


class BetRecord(BaseModel):
    id: int
    event: str
    selection: str
    american_odds: int
    win_prob: float
    stake: float
    kelly_fraction: float
    ev_percent: float
    created_at: str
    status: str
    result_amount: float
    notes: str


class BetStatsResponse(BaseModel):
    total_bets: int
    pending: int = 0
    settled: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0
    total_staked: float = 0
    total_profit: float = 0
    roi: float = 0
    pending_exposure: float = 0


@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the main dashboard."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EdgeFinder - Sports Betting Analytics</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1419; color: #e7e9ea; line-height: 1.6; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        h1 { color: #1d9bf0; margin-bottom: 10px; }
        .subtitle { color: #71767b; margin-bottom: 30px; }
        .controls { display: flex; gap: 15px; margin-bottom: 25px; flex-wrap: wrap; align-items: center; }
        select, input, button { padding: 10px 15px; border-radius: 8px; border: 1px solid #333; background: #16181c; color: #e7e9ea; font-size: 14px; }
        button { background: #1d9bf0; border: none; cursor: pointer; font-weight: 600; }
        button:hover { background: #1a8cd8; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab { padding: 10px 20px; background: #16181c; border: 1px solid #333; border-radius: 8px; cursor: pointer; }
        .tab.active { background: #1d9bf0; border-color: #1d9bf0; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #2f3336; }
        th { background: #16181c; color: #71767b; font-weight: 600; text-transform: uppercase; font-size: 12px; }
        tr:hover { background: #16181c; }
        .positive { color: #00ba7c; font-weight: 600; }
        .negative { color: #f4212e; }
        .loading { text-align: center; padding: 40px; color: #71767b; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px; }
        .stat-card { background: #16181c; padding: 20px; border-radius: 12px; border: 1px solid #2f3336; }
        .stat-value { font-size: 28px; font-weight: 700; color: #1d9bf0; }
        .stat-label { color: #71767b; font-size: 14px; }
        .no-data { text-align: center; padding: 40px; color: #71767b; }
    </style>
</head>
<body>
    <div class="container">
        <h1>EdgeFinder</h1>
        <p class="subtitle">Sports Betting Analytics Dashboard</p>

        <div class="tabs">
            <div class="tab active" onclick="showTab('ev')">+EV Bets</div>
            <div class="tab" onclick="showTab('props')">Player Props</div>
            <div class="tab" onclick="showTab('arb')">Arbitrage</div>
            <div class="tab" onclick="showTab('devig')">De-Vig Calculator</div>
            <div class="tab" onclick="showTab('kelly')">Bet Creator</div>
        </div>

        <div id="ev-section">
            <div class="controls">
                <select id="sport">
                    <option value="nfl">NFL</option>
                    <option value="nba">NBA</option>
                    <option value="mlb">MLB</option>
                    <option value="nhl">NHL</option>
                </select>
                <input type="number" id="bankroll" value="1000" min="100" step="100" style="width: 120px;">
                <label style="color: #71767b;">Bankroll</label>
                <input type="number" id="min-ev" value="1.0" min="0" step="0.5" style="width: 80px;">
                <label style="color: #71767b;">Min EV%</label>
                <button onclick="loadBets()">Find +EV Bets</button>
            </div>

            <div class="stats" id="stats"></div>
            <div id="bets-table"></div>
        </div>

        <div id="props-section" style="display: none;">
            <div class="controls">
                <select id="props-sport">
                    <option value="nba">NBA</option>
                    <option value="nfl">NFL</option>
                    <option value="mlb">MLB</option>
                    <option value="nhl">NHL</option>
                </select>
                <input type="number" id="props-bankroll" value="1000" min="100" step="100" style="width: 120px;">
                <label style="color: #71767b;">Bankroll</label>
                <input type="number" id="props-min-ev" value="2.0" min="0" step="0.5" style="width: 80px;">
                <label style="color: #71767b;">Min EV%</label>
                <button onclick="loadProps()">Find +EV Props</button>
            </div>

            <div class="stats" id="props-stats"></div>
            <div id="props-table"></div>
        </div>

        <div id="arb-section" style="display: none;">
            <div class="controls">
                <select id="arb-sport">
                    <option value="nfl">NFL</option>
                    <option value="nba">NBA</option>
                    <option value="mlb">MLB</option>
                    <option value="nhl">NHL</option>
                </select>
                <input type="number" id="arb-stake" value="1000" min="100" step="100" style="width: 120px;">
                <label style="color: #71767b;">Total Stake</label>
                <button onclick="loadArbitrage()">Find Arbitrage</button>
            </div>
            <div id="arb-table"></div>
        </div>

        <div id="devig-section" style="display: none;">
            <div class="controls">
                <input type="number" id="odds1" value="-150" style="width: 100px;">
                <label style="color: #71767b;">Side 1</label>
                <input type="number" id="odds2" value="130" style="width: 100px;">
                <label style="color: #71767b;">Side 2</label>
                <select id="devig-method">
                    <option value="weighted">Weighted</option>
                    <option value="multiplicative">Multiplicative</option>
                    <option value="power">Power</option>
                    <option value="shin">Shin</option>
                    <option value="additive">Additive</option>
                </select>
                <button onclick="calculateDevig()">Calculate Fair Odds</button>
            </div>
            <div id="devig-result"></div>
        </div>

        <div id="kelly-section" style="display: none;">
            <div class="stats" id="kelly-stats"></div>

            <h3 style="color: #71767b; margin-bottom: 15px;">Quick Size Calculator</h3>
            <div class="controls">
                <input type="number" id="kelly-odds" value="+150" style="width: 100px;">
                <label style="color: #71767b;">Odds</label>
                <input type="number" id="kelly-prob" value="45" min="1" max="99" style="width: 80px;">
                <label style="color: #71767b;">Win %</label>
                <input type="number" id="kelly-bankroll" value="1000" min="100" style="width: 120px;">
                <label style="color: #71767b;">Bankroll</label>
                <input type="number" id="kelly-frac" value="0.25" min="0.1" max="1" step="0.05" style="width: 80px;">
                <label style="color: #71767b;">Kelly Frac</label>
                <button onclick="calculateKelly()">Calculate</button>
            </div>
            <div id="kelly-result"></div>

            <h3 style="color: #71767b; margin: 30px 0 15px;">Create New Bet</h3>
            <div class="controls" style="flex-wrap: wrap;">
                <input type="text" id="bet-event" placeholder="Event (e.g., Lakers vs Celtics)" style="width: 250px;">
                <input type="text" id="bet-selection" placeholder="Selection (e.g., Lakers ML)" style="width: 200px;">
                <input type="number" id="bet-odds" placeholder="Odds" style="width: 100px;">
                <input type="number" id="bet-prob" placeholder="Win %" min="1" max="99" style="width: 80px;">
                <input type="text" id="bet-notes" placeholder="Notes (optional)" style="width: 200px;">
                <button onclick="createBet()">Save Bet</button>
            </div>

            <h3 style="color: #71767b; margin: 30px 0 15px;">Pending Bets</h3>
            <div id="pending-bets"></div>

            <h3 style="color: #71767b; margin: 30px 0 15px;">Bet History</h3>
            <div id="bet-history"></div>
        </div>
    </div>

    <script>
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('[id$="-section"]').forEach(s => s.style.display = 'none');
            event.target.classList.add('active');
            document.getElementById(tab + '-section').style.display = 'block';
            if (tab === 'kelly') loadKellyData();
        }

        async function loadBets() {
            const sport = document.getElementById('sport').value;
            const bankroll = document.getElementById('bankroll').value;
            const minEv = document.getElementById('min-ev').value;

            document.getElementById('bets-table').innerHTML = '<div class="loading">Loading...</div>';

            const res = await fetch(`/api/bets?sport=${sport}&bankroll=${bankroll}&min_ev=${minEv}`);
            const bets = await res.json();

            if (bets.length === 0) {
                document.getElementById('stats').innerHTML = '';
                document.getElementById('bets-table').innerHTML = '<div class="no-data">No +EV bets found matching your criteria</div>';
                return;
            }

            const totalStake = bets.reduce((sum, b) => sum + b.recommended_stake, 0);
            const avgEv = bets.reduce((sum, b) => sum + b.ev_percent, 0) / bets.length;

            document.getElementById('stats').innerHTML = `
                <div class="stat-card"><div class="stat-value">${bets.length}</div><div class="stat-label">+EV Bets Found</div></div>
                <div class="stat-card"><div class="stat-value">$${totalStake.toFixed(2)}</div><div class="stat-label">Total Stake</div></div>
                <div class="stat-card"><div class="stat-value">+${avgEv.toFixed(2)}%</div><div class="stat-label">Average EV</div></div>
                <div class="stat-card"><div class="stat-value">${(totalStake/bankroll*100).toFixed(1)}%</div><div class="stat-label">Exposure</div></div>
            `;

            let html = `<table>
                <tr><th>Event</th><th>Selection</th><th>Best Odds</th><th>Book</th><th>Fair Odds</th><th>EV%</th><th>Stake</th></tr>`;
            bets.forEach(b => {
                const oddsStr = b.best_odds > 0 ? '+' + b.best_odds : b.best_odds;
                const fairStr = b.fair_odds > 0 ? '+' + b.fair_odds : b.fair_odds;
                html += `<tr>
                    <td>${b.event}</td>
                    <td>${b.selection}</td>
                    <td class="positive">${oddsStr}</td>
                    <td>${b.bookmaker}</td>
                    <td>${fairStr}</td>
                    <td class="positive">+${b.ev_percent.toFixed(2)}%</td>
                    <td>$${b.recommended_stake.toFixed(2)}</td>
                </tr>`;
            });
            html += '</table>';
            document.getElementById('bets-table').innerHTML = html;
        }

        async function loadProps() {
            const sport = document.getElementById('props-sport').value;
            const bankroll = document.getElementById('props-bankroll').value;
            const minEv = document.getElementById('props-min-ev').value;

            document.getElementById('props-table').innerHTML = '<div class="loading">Loading player props...</div>';

            const res = await fetch(`/api/props?sport=${sport}&bankroll=${bankroll}&min_ev=${minEv}`);
            const props = await res.json();

            if (props.length === 0) {
                document.getElementById('props-stats').innerHTML = '';
                document.getElementById('props-table').innerHTML = '<div class="no-data">No +EV player props found matching your criteria</div>';
                return;
            }

            const totalStake = props.reduce((sum, b) => sum + b.recommended_stake, 0);
            const avgEv = props.reduce((sum, b) => sum + b.ev_percent, 0) / props.length;

            document.getElementById('props-stats').innerHTML = `
                <div class="stat-card"><div class="stat-value">${props.length}</div><div class="stat-label">+EV Props Found</div></div>
                <div class="stat-card"><div class="stat-value">$${totalStake.toFixed(2)}</div><div class="stat-label">Total Stake</div></div>
                <div class="stat-card"><div class="stat-value">+${avgEv.toFixed(2)}%</div><div class="stat-label">Average EV</div></div>
            `;

            let html = `<table>
                <tr><th>Player</th><th>Prop</th><th>Line</th><th>Pick</th><th>Best Odds</th><th>Book</th><th>Fair Odds</th><th>EV%</th><th>Stake</th></tr>`;
            props.forEach(p => {
                const oddsStr = p.best_odds > 0 ? '+' + p.best_odds : p.best_odds;
                const fairStr = p.fair_odds > 0 ? '+' + p.fair_odds : p.fair_odds;
                const propType = p.market_type.replace('player_', '').replace('_', ' ');
                html += `<tr>
                    <td>${p.player || 'N/A'}</td>
                    <td>${propType}</td>
                    <td>${p.point || '-'}</td>
                    <td>${p.selection}</td>
                    <td class="positive">${oddsStr}</td>
                    <td>${p.bookmaker}</td>
                    <td>${fairStr}</td>
                    <td class="positive">+${p.ev_percent.toFixed(2)}%</td>
                    <td>$${p.recommended_stake.toFixed(2)}</td>
                </tr>`;
            });
            html += '</table>';
            document.getElementById('props-table').innerHTML = html;
        }

        async function loadArbitrage() {
            const sport = document.getElementById('arb-sport').value;
            const stake = document.getElementById('arb-stake').value;

            document.getElementById('arb-table').innerHTML = '<div class="loading">Loading...</div>';

            const res = await fetch(`/api/arbitrage?sport=${sport}&stake=${stake}`);
            const arbs = await res.json();

            if (arbs.length === 0) {
                document.getElementById('arb-table').innerHTML = '<div class="no-data">No arbitrage opportunities found</div>';
                return;
            }

            let html = '<table><tr><th>Event</th><th>Profit</th><th>Stakes</th></tr>';
            arbs.forEach(a => {
                const stakesStr = a.stakes.map(s => `${s.selection}: $${s.stake.toFixed(2)} @ ${s.bookmaker}`).join('<br>');
                html += `<tr><td>${a.event}</td><td class="positive">+${a.profit_percent.toFixed(2)}%</td><td>${stakesStr}</td></tr>`;
            });
            html += '</table>';
            document.getElementById('arb-table').innerHTML = html;
        }

        async function calculateDevig() {
            const odds1 = document.getElementById('odds1').value;
            const odds2 = document.getElementById('odds2').value;
            const method = document.getElementById('devig-method').value;

            const res = await fetch(`/api/devig?odds=${odds1}&odds=${odds2}&method=${method}`);
            const result = await res.json();

            const fair1 = result.fair_odds[0] > 0 ? '+' + result.fair_odds[0] : result.fair_odds[0];
            const fair2 = result.fair_odds[1] > 0 ? '+' + result.fair_odds[1] : result.fair_odds[1];

            document.getElementById('devig-result').innerHTML = `
                <div class="stats" style="margin-top: 20px;">
                    <div class="stat-card">
                        <div class="stat-value">${(result.original_implied[0] * 100).toFixed(1)}%</div>
                        <div class="stat-label">Side 1 Implied</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${(result.original_implied[1] * 100).toFixed(1)}%</div>
                        <div class="stat-label">Side 2 Implied</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${(result.vig_removed * 100).toFixed(2)}%</div>
                        <div class="stat-label">Vig Removed</div>
                    </div>
                </div>
                <table style="margin-top: 20px;">
                    <tr><th>Side</th><th>Input Odds</th><th>Fair Probability</th><th>Fair Odds</th></tr>
                    <tr><td>Side 1</td><td>${odds1}</td><td>${(result.fair_probs[0] * 100).toFixed(2)}%</td><td class="positive">${fair1}</td></tr>
                    <tr><td>Side 2</td><td>${odds2}</td><td>${(result.fair_probs[1] * 100).toFixed(2)}%</td><td class="positive">${fair2}</td></tr>
                </table>
            `;
        }

        async function calculateKelly() {
            const odds = parseInt(document.getElementById('kelly-odds').value);
            const prob = parseFloat(document.getElementById('kelly-prob').value) / 100;
            const bankroll = parseFloat(document.getElementById('kelly-bankroll').value);
            const frac = parseFloat(document.getElementById('kelly-frac').value);

            const res = await fetch(`/api/kelly/size?odds=${odds}&prob=${prob}&bankroll=${bankroll}&kelly_frac=${frac}`);
            const r = await res.json();

            const oddsStr = r.american_odds > 0 ? '+' + r.american_odds : r.american_odds;
            const edgeClass = r.edge > 0 ? 'positive' : 'negative';

            document.getElementById('kelly-result').innerHTML = `
                <div class="stats" style="margin-top: 20px;">
                    <div class="stat-card">
                        <div class="stat-value">${r.implied_prob}%</div>
                        <div class="stat-label">Implied Prob</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${r.your_prob}%</div>
                        <div class="stat-label">Your Prob</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value ${edgeClass}">${r.edge > 0 ? '+' : ''}${r.edge}%</div>
                        <div class="stat-label">Edge</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value ${r.ev_percent > 0 ? 'positive' : 'negative'}">${r.ev_percent > 0 ? '+' : ''}${r.ev_percent}%</div>
                        <div class="stat-label">EV</div>
                    </div>
                </div>
                <table style="margin-top: 20px;">
                    <tr><th>Metric</th><th>Value</th></tr>
                    <tr><td>Odds</td><td>${oddsStr} (${r.decimal_odds})</td></tr>
                    <tr><td>Full Kelly</td><td>${r.full_kelly}% of bankroll</td></tr>
                    <tr><td>Recommended (${frac}x Kelly)</td><td>${r.recommended_fraction}% of bankroll</td></tr>
                    <tr><td>Bet Size</td><td class="positive">$${r.recommended_stake.toFixed(2)}</td></tr>
                </table>
            `;
        }

        async function createBet() {
            const event = document.getElementById('bet-event').value;
            const selection = document.getElementById('bet-selection').value;
            const odds = parseInt(document.getElementById('bet-odds').value);
            const prob = parseFloat(document.getElementById('bet-prob').value) / 100;
            const notes = document.getElementById('bet-notes').value;
            const bankroll = parseFloat(document.getElementById('kelly-bankroll').value) || 1000;
            const kelly = parseFloat(document.getElementById('kelly-frac').value) || 0.25;

            if (!event || !selection || isNaN(odds) || isNaN(prob)) {
                alert('Please fill in all required fields');
                return;
            }

            const res = await fetch('/api/kelly/bet', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({event, selection, american_odds: odds, win_prob: prob, bankroll, kelly_fraction: kelly, notes})
            });
            const bet = await res.json();

            alert(`Bet #${bet.id} created! Stake: $${bet.stake.toFixed(2)}`);
            document.getElementById('bet-event').value = '';
            document.getElementById('bet-selection').value = '';
            document.getElementById('bet-odds').value = '';
            document.getElementById('bet-prob').value = '';
            document.getElementById('bet-notes').value = '';
            loadKellyData();
        }

        async function markResult(betId, result) {
            await fetch(`/api/kelly/bet/${betId}/result?result=${result}`, {method: 'POST'});
            loadKellyData();
        }

        async function loadKellyData() {
            // Load stats
            const statsRes = await fetch('/api/kelly/stats');
            const stats = await statsRes.json();

            if (stats.total_bets > 0) {
                const profitClass = stats.total_profit >= 0 ? 'positive' : 'negative';
                document.getElementById('kelly-stats').innerHTML = `
                    <div class="stat-card"><div class="stat-value">${stats.wins}-${stats.losses}</div><div class="stat-label">Record (${stats.win_rate}%)</div></div>
                    <div class="stat-card"><div class="stat-value">$${stats.total_staked.toFixed(2)}</div><div class="stat-label">Total Staked</div></div>
                    <div class="stat-card"><div class="stat-value ${profitClass}">$${stats.total_profit >= 0 ? '+' : ''}${stats.total_profit.toFixed(2)}</div><div class="stat-label">Profit/Loss</div></div>
                    <div class="stat-card"><div class="stat-value ${profitClass}">${stats.roi >= 0 ? '+' : ''}${stats.roi}%</div><div class="stat-label">ROI</div></div>
                `;
            } else {
                document.getElementById('kelly-stats').innerHTML = '';
            }

            // Load pending bets
            const pendingRes = await fetch('/api/kelly/bets/pending');
            const pending = await pendingRes.json();

            if (pending.length === 0) {
                document.getElementById('pending-bets').innerHTML = '<div class="no-data">No pending bets</div>';
            } else {
                let html = `<table>
                    <tr><th>ID</th><th>Event</th><th>Selection</th><th>Odds</th><th>Win %</th><th>Stake</th><th>EV</th><th>Actions</th></tr>`;
                pending.forEach(b => {
                    const oddsStr = b.american_odds > 0 ? '+' + b.american_odds : b.american_odds;
                    html += `<tr>
                        <td>#${b.id}</td>
                        <td>${b.event}</td>
                        <td>${b.selection}</td>
                        <td>${oddsStr}</td>
                        <td>${(b.win_prob * 100).toFixed(1)}%</td>
                        <td>$${b.stake.toFixed(2)}</td>
                        <td class="positive">+${b.ev_percent.toFixed(2)}%</td>
                        <td>
                            <button onclick="markResult(${b.id}, 'won')" style="padding: 5px 10px; background: #00ba7c;">W</button>
                            <button onclick="markResult(${b.id}, 'lost')" style="padding: 5px 10px; background: #f4212e;">L</button>
                            <button onclick="markResult(${b.id}, 'void')" style="padding: 5px 10px; background: #71767b;">V</button>
                        </td>
                    </tr>`;
                });
                html += '</table>';
                document.getElementById('pending-bets').innerHTML = html;
            }

            // Load bet history
            const historyRes = await fetch('/api/kelly/bets');
            const history = await historyRes.json();
            const settled = history.filter(b => b.status !== 'pending');

            if (settled.length === 0) {
                document.getElementById('bet-history').innerHTML = '<div class="no-data">No settled bets yet</div>';
            } else {
                let html = `<table>
                    <tr><th>ID</th><th>Event</th><th>Selection</th><th>Odds</th><th>Stake</th><th>Result</th><th>P/L</th></tr>`;
                settled.slice(0, 20).forEach(b => {
                    const oddsStr = b.american_odds > 0 ? '+' + b.american_odds : b.american_odds;
                    const statusClass = b.status === 'won' ? 'positive' : (b.status === 'lost' ? 'negative' : '');
                    const plClass = b.result_amount >= 0 ? 'positive' : 'negative';
                    html += `<tr>
                        <td>#${b.id}</td>
                        <td>${b.event}</td>
                        <td>${b.selection}</td>
                        <td>${oddsStr}</td>
                        <td>$${b.stake.toFixed(2)}</td>
                        <td class="${statusClass}">${b.status.toUpperCase()}</td>
                        <td class="${plClass}">$${b.result_amount >= 0 ? '+' : ''}${b.result_amount.toFixed(2)}</td>
                    </tr>`;
                });
                html += '</table>';
                document.getElementById('bet-history').innerHTML = html;
            }
        }

        // Load initial data
        loadBets();
    </script>
</body>
</html>
"""


@app.get("/api/bets", response_model=list[BetResponse])
async def get_bets(
    sport: str = Query("nfl", description="Sport to analyze"),
    bankroll: float = Query(1000, description="Bankroll for Kelly sizing"),
    min_ev: float = Query(1.0, description="Minimum EV%"),
    kelly: float = Query(0.25, description="Kelly fraction"),
):
    """Get +EV betting opportunities."""
    markets = fetch_odds(sport, use_cache=True)
    bets = find_ev_bets(
        markets=markets,
        bankroll=bankroll,
        min_ev=min_ev,
        kelly_fraction=kelly,
    )

    return [
        BetResponse(
            event=b.market.event,
            selection=b.market.selection,
            best_odds=b.best_odds.american,
            bookmaker=b.best_odds.bookmaker,
            fair_odds=b.fair_american,
            ev_percent=round(b.ev_percent, 2),
            recommended_stake=round(b.recommended_stake, 2),
        )
        for b in bets
    ]


@app.get("/api/props", response_model=list[BetResponse])
async def get_props(
    sport: str = Query("nba", description="Sport to analyze"),
    bankroll: float = Query(1000, description="Bankroll for Kelly sizing"),
    min_ev: float = Query(2.0, description="Minimum EV%"),
    kelly: float = Query(0.25, description="Kelly fraction"),
):
    """Get +EV player prop betting opportunities."""
    markets = fetch_player_props(sport, use_cache=True)
    bets = find_ev_bets(
        markets=markets,
        bankroll=bankroll,
        min_ev=min_ev,
        kelly_fraction=kelly,
    )

    return [
        BetResponse(
            event=b.market.event,
            selection=b.market.selection,
            best_odds=b.best_odds.american,
            bookmaker=b.best_odds.bookmaker,
            fair_odds=b.fair_american,
            ev_percent=round(b.ev_percent, 2),
            recommended_stake=round(b.recommended_stake, 2),
            player=b.market.player,
            point=b.market.point,
            market_type=b.market.market_type,
        )
        for b in bets
    ]


@app.get("/api/arbitrage", response_model=list[ArbitrageResponse])
async def get_arbitrage(
    sport: str = Query("nfl", description="Sport to analyze"),
    stake: float = Query(1000, description="Total stake per arb"),
):
    """Get arbitrage opportunities."""
    markets = fetch_odds(sport, use_cache=True)

    all_markets = []
    seen = set()
    for market, _ in markets:
        key = f"{market.event}_{market.selection}"
        if key not in seen:
            all_markets.append(market)
            seen.add(key)

    opportunities = find_arbitrage(all_markets, min_profit=0.5, total_stake=stake)

    return [
        ArbitrageResponse(
            event=arb.event,
            profit_percent=round(arb.profit_percent, 2),
            stakes=[
                {"selection": s[0], "bookmaker": s[1], "stake": s[2]}
                for s in arb.stakes
            ],
        )
        for arb in opportunities
    ]


@app.get("/api/devig", response_model=DevigResponse)
async def devig_odds(
    odds: list[int] = Query(..., description="American odds to de-vig"),
    method: str = Query("weighted", description="De-vig method"),
):
    """De-vig American odds to get fair probabilities."""
    implied_probs = []
    for american in odds:
        o = Odds(bookmaker="input", american=american)
        implied_probs.append(o.implied_prob)

    result = devig(implied_probs, method=method)

    fair_odds = []
    for p in result.fair_probs:
        if p >= 0.5:
            fair_odds.append(int(-100 * p / (1 - p)))
        else:
            fair_odds.append(int(100 * (1 - p) / p))

    return DevigResponse(
        method=result.method,
        original_implied=result.original_implied,
        fair_probs=result.fair_probs,
        fair_odds=fair_odds,
        vig_removed=result.vig_removed,
    )


@app.get("/api/sports")
async def list_sports():
    """List available sports."""
    return get_available_sports()


# Kelly Bet Creator Endpoints

@app.get("/api/kelly/size", response_model=KellySizeResponse)
async def kelly_size(
    odds: int = Query(..., description="American odds"),
    prob: float = Query(..., description="Win probability (0-1)"),
    bankroll: float = Query(1000, description="Bankroll"),
    kelly_frac: float = Query(0.25, description="Kelly fraction"),
):
    """Calculate Kelly bet size."""
    result = quick_size(odds, prob, bankroll, kelly_frac)
    return KellySizeResponse(**result)


@app.post("/api/kelly/bet", response_model=BetRecord)
async def create_kelly_bet(req: CreateBetRequest):
    """Create and save a new bet."""
    bet = create_bet(
        event=req.event,
        selection=req.selection,
        american_odds=req.american_odds,
        win_prob=req.win_prob,
        bankroll=req.bankroll,
        kelly_frac=req.kelly_fraction,
        notes=req.notes,
    )
    return BetRecord(
        id=bet.id,
        event=bet.event,
        selection=bet.selection,
        american_odds=bet.american_odds,
        win_prob=bet.win_prob,
        stake=bet.stake,
        kelly_fraction=bet.kelly_fraction,
        ev_percent=bet.ev_percent,
        created_at=bet.created_at,
        status=bet.status,
        result_amount=bet.result_amount,
        notes=bet.notes,
    )


@app.get("/api/kelly/bets", response_model=list[BetRecord])
async def get_all_bets():
    """Get all bets."""
    bets = load_bets()
    return [BetRecord(**b) for b in bets]


@app.get("/api/kelly/bets/pending", response_model=list[BetRecord])
async def get_pending_bets():
    """Get pending bets."""
    bets = list_pending_bets()
    return [BetRecord(**b) for b in bets]


@app.post("/api/kelly/bet/{bet_id}/result")
async def set_bet_result(
    bet_id: int,
    result: str = Query(..., description="Result: won, lost, or void"),
):
    """Mark a bet as won, lost, or void."""
    if result == "won":
        bet = mark_bet_result(bet_id, won=True)
    elif result == "lost":
        bet = mark_bet_result(bet_id, won=False)
    elif result == "void":
        bet = mark_bet_result(bet_id, won=False, void=True)
    else:
        return {"error": "Invalid result. Use won, lost, or void."}

    if bet:
        return {"success": True, "bet": bet}
    return {"error": "Bet not found"}


@app.get("/api/kelly/stats", response_model=BetStatsResponse)
async def get_bet_stats():
    """Get betting statistics."""
    stats = get_stats()
    return BetStatsResponse(**stats)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

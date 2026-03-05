#!/usr/bin/env python3
"""
Polymarket Weekly Dashboard Generator.

Runs the full pipeline and produces a self-contained HTML dashboard.
Usage:
    python generate_dashboard.py          # Generate and open in browser
    python generate_dashboard.py --no-open  # Generate only
"""
import re
import sys
import io
import json
import base64
import webbrowser
import requests
import logging
from dataclasses import asdict
from pathlib import Path
from datetime import datetime

TRADES_FILE          = Path(__file__).parent / "data" / "portfolio" / "trades.json"
PRIORITY_TOPICS_FILE = Path(__file__).parent / "data" / "priority_topics.json"


# ── Priority Topics ────────────────────────────────────────────────────────────
def load_priority_topics() -> list:
    """Load user-defined priority topics from data/priority_topics.json."""
    if not PRIORITY_TOPICS_FILE.exists():
        return []
    try:
        data = json.loads(PRIORITY_TOPICS_FILE.read_text())
        return data.get("topics", [])
    except Exception:
        return []


def match_priority_topic(text: str, priority_topics: list) -> tuple:
    """
    Check if text matches any priority topic keyword.

    Returns:
        (matched: bool, topic_name: str)
    """
    text_lower = text.lower()
    for topic in priority_topics:
        for keyword in topic.get("keywords", []):
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            if re.search(pattern, text_lower):
                return True, topic["name"]
    return False, ""


def load_trades() -> list:
    if TRADES_FILE.exists():
        try:
            return json.loads(TRADES_FILE.read_text())
        except Exception:
            pass
    return []


def fetch_current_price(ticker: str):
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="2d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return None


def fetch_current_prices_batch(tickers: list) -> dict:
    """Fetch current price and 1-day delta for a list of tickers."""
    result = {}
    if not tickers:
        return result
    try:
        import yfinance as yf
        for t in tickers:
            try:
                hist = yf.Ticker(t).history(period="5d")
                if not hist.empty and len(hist) >= 1:
                    price = round(float(hist["Close"].iloc[-1]), 2)
                    delta = round(float(hist["Close"].iloc[-1] - hist["Close"].iloc[-2]), 2) if len(hist) >= 2 else 0.0
                    result[t] = {"price": price, "delta_1d": delta}
            except Exception:
                pass
    except Exception as e:
        print(f"  Warning: batch price fetch failed: {e}")
    return result


# ── Portfolio / Buy-button HTML & JS constants ─────────────────────────────────
PORTFOLIO_SECTION_HTML = """
<div id="pm-portfolio-section" style="display:none">
  <div class="section" style="border:2px solid #27ae60">
    <div class="section-header" style="background:linear-gradient(135deg,#1a1a2e,#0f3460);color:white">
      \U0001f4bc Mi Portfolio \u2014 Performance en Tiempo Real
    </div>
    <div class="section-body" id="pm-portfolio-body"></div>
  </div>
</div>"""

BUY_MODAL_HTML = """
<div id="pm-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);z-index:9999;align-items:center;justify-content:center">
  <div style="background:white;border-radius:16px;padding:32px;min-width:360px;max-width:460px;box-shadow:0 20px 60px rgba(0,0,0,0.3)">
    <h3 style="margin-bottom:16px;color:#2c3e50">\U0001f6d2 Registrar Posici\u00f3n</h3>
    <div style="background:#f8f9fa;border-radius:8px;padding:14px;margin-bottom:16px">
      <div style="font-size:1.3rem;font-weight:700;color:#1e8449" id="pm-modal-ticker"></div>
      <div style="font-size:.85rem;color:#555;margin-top:2px" id="pm-modal-name"></div>
      <div style="font-size:.76rem;color:#7f8c8d;margin-top:6px" id="pm-modal-source"></div>
      <div style="font-size:.85rem;font-weight:600;margin-top:8px;color:#2c3e50">
        Precio de mercado actual: <span id="pm-modal-price" style="color:#3498db"></span>
      </div>
    </div>
    <label style="font-weight:600;font-size:.9rem;color:#2c3e50">Monto a invertir (USD):</label>
    <input type="number" id="pm-modal-amount" min="1" placeholder="ej: 500"
           style="width:100%;padding:12px;margin:8px 0 20px;border:2px solid #ddd;border-radius:8px;font-size:1rem;outline:none"
           onkeydown="if(event.key==='Enter')confirmBuy()">
    <div style="display:flex;gap:12px;justify-content:flex-end">
      <button onclick="closeBuyModal()"
              style="padding:10px 20px;border:1px solid #ddd;border-radius:8px;background:white;cursor:pointer;font-size:.9rem;color:#555">
        Cancelar
      </button>
      <button onclick="confirmBuy()"
              style="padding:10px 24px;border:none;border-radius:8px;background:#27ae60;color:white;cursor:pointer;font-weight:700;font-size:.9rem">
        \u2713 Confirmar Compra
      </button>
    </div>
  </div>
</div>"""

PORTFOLIO_CSS = """
  .buy-btn { background: #27ae60; color: white; border: none; border-radius: 6px;
             padding: 5px 12px; cursor: pointer; font-size: .75rem; font-weight: 700;
             transition: background .15s; }
  .buy-btn:hover { background: #1e8449; }
  .pm-summary-cards { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
  .pm-card { background: #f8f9fa; border-radius: 10px; padding: 14px 20px; flex: 1; min-width: 150px; }
  .pm-card-pnl { border-left: 4px solid #27ae60; }
  .pm-card-label { font-size: .72rem; text-transform: uppercase; letter-spacing: .5px; color: #7f8c8d; font-weight: 600; }
  .pm-card-value { font-size: 1.5rem; font-weight: 700; margin-top: 4px; }
  .pm-remove-btn { background: none; border: 1px solid #e0e0e0; border-radius: 50%; width: 24px; height: 24px;
                   cursor: pointer; color: #e74c3c; font-size: 1rem; line-height: 1; padding: 0; }
  .pm-remove-btn:hover { background: #fadbd8; }"""

PORTFOLIO_JS = """<script>
const _PF_KEY = 'pmadv_portfolio_v1';
let _buySignal = null;

function _getPF() {
  try { return JSON.parse(localStorage.getItem(_PF_KEY) || '[]'); }
  catch(e) { return []; }
}
function _savePF(p) { localStorage.setItem(_PF_KEY, JSON.stringify(p)); }

function openBuyModal(btn) {
  const tr = btn.closest('tr');
  const d = tr.dataset;
  const pd = (window.DASHBOARD_DATA && window.DASHBOARD_DATA.current_prices || {})[d.ticker];
  _buySignal = {
    ticker: d.ticker, name: d.name || '',
    yesPrice: parseFloat(d.yesPrice || 0),
    source: d.source || '', action: d.action || 'BUY',
    currentPrice: pd ? pd.price : null
  };
  document.getElementById('pm-modal-ticker').textContent = d.ticker;
  document.getElementById('pm-modal-name').textContent = d.name || '';
  document.getElementById('pm-modal-source').textContent = (d.source || '').slice(0, 80);
  document.getElementById('pm-modal-price').textContent =
    pd ? '$' + pd.price.toFixed(2) : 'N/A \u2014 se guardar\u00e1 sin precio de referencia';
  document.getElementById('pm-modal-amount').value = '';
  document.getElementById('pm-modal-amount').style.borderColor = '#ddd';
  document.getElementById('pm-modal').style.display = 'flex';
  setTimeout(() => document.getElementById('pm-modal-amount').focus(), 50);
}

function closeBuyModal() {
  document.getElementById('pm-modal').style.display = 'none';
  _buySignal = null;
}

function confirmBuy() {
  const amt = parseFloat(document.getElementById('pm-modal-amount').value);
  const inp = document.getElementById('pm-modal-amount');
  if (!amt || amt <= 0) { inp.style.borderColor = '#e74c3c'; inp.focus(); return; }
  if (!_buySignal) return;
  const pf = _getPF();
  pf.push({
    id: Date.now().toString(),
    ticker: _buySignal.ticker,
    instrument_name: _buySignal.name,
    usd_amount: amt,
    price_at_buy: _buySignal.currentPrice,
    date_bought: new Date().toISOString(),
    signal_source: _buySignal.source,
    action: _buySignal.action
  });
  _savePF(pf);
  closeBuyModal();
  renderPortfolio();
}

function removePosition(id) {
  if (!confirm('Eliminar esta posicion del portfolio?')) return;
  _savePF(_getPF().filter(p => p.id !== id));
  renderPortfolio();
}

function renderPortfolio() {
  const pf = _getPF();
  const section = document.getElementById('pm-portfolio-section');
  if (!section) return;
  if (pf.length === 0) { section.style.display = 'none'; return; }

  const prices = (window.DASHBOARD_DATA && window.DASHBOARD_DATA.current_prices) || {};
  let totalInv = 0, totalVal = 0;

  const rows = pf.map(p => {
    const pd = prices[p.ticker];
    const cur = pd ? pd.price : null;
    const d1d = pd ? pd.delta_1d : null;
    let pnlHTML = '<td>&#8212;</td><td>&#8212;</td>';
    let curHTML = '<td style="color:#7f8c8d">N/A</td>';
    let dHTML = '<td>&#8212;</td>';
    let curVal = p.usd_amount;

    if (cur !== null && p.price_at_buy !== null && p.price_at_buy > 0) {
      const pct = (cur - p.price_at_buy) / p.price_at_buy;
      const pnl = pct * p.usd_amount;
      curVal = p.usd_amount + pnl;
      const sign = pnl >= 0 ? '+' : '';
      const col = pnl >= 0 ? '#27ae60' : '#e74c3c';
      pnlHTML = '<td style="color:' + col + ';font-weight:700">' + sign + '$' + Math.abs(pnl).toFixed(0) + '</td>' +
                '<td style="color:' + col + ';font-weight:700">' + sign + (pct*100).toFixed(1) + '%</td>';
      curHTML = '<td><strong>$' + cur.toFixed(2) + '</strong></td>';
    } else if (cur !== null) {
      curHTML = '<td><strong>$' + cur.toFixed(2) + '</strong></td>';
    }

    if (d1d !== null) {
      const s2 = d1d >= 0 ? '+' : '';
      const c2 = d1d >= 0 ? '#27ae60' : '#e74c3c';
      dHTML = '<td style="color:' + c2 + ';font-weight:600">' + s2 + '$' + d1d.toFixed(2) + '</td>';
    }

    totalInv += p.usd_amount;
    totalVal += curVal;

    const buyP = (p.price_at_buy !== null && p.price_at_buy > 0) ? '$' + p.price_at_buy.toFixed(2) : '&#8212;';
    const dt = p.date_bought ? p.date_bought.slice(0, 10) : '&#8212;';
    const src = (p.signal_source || '').slice(0, 50);

    return '<tr>' +
      '<td><strong>' + p.ticker + '</strong></td>' +
      '<td style="font-size:.8rem">' + (p.instrument_name || '') + '</td>' +
      '<td>$' + p.usd_amount.toLocaleString(undefined, {maximumFractionDigits:0}) + '</td>' +
      '<td>' + buyP + '</td>' +
      curHTML + pnlHTML + dHTML +
      '<td style="font-size:.75rem;color:#7f8c8d">' + dt + '</td>' +
      '<td style="font-size:.72rem;color:#7f8c8d;max-width:120px">' + src + '</td>' +
      '<td><button class="pm-remove-btn" onclick="removePosition(\'' + p.id + '\')" title="Eliminar">&#215;</button></td>' +
      '</tr>';
  }).join('');

  const totalPnL = totalVal - totalInv;
  const totalPct = totalInv > 0 ? totalPnL / totalInv * 100 : 0;
  const tSign = totalPnL >= 0 ? '+' : '';
  const tColor = totalPnL >= 0 ? '#27ae60' : '#e74c3c';

  document.getElementById('pm-portfolio-body').innerHTML =
    '<div class="pm-summary-cards">' +
      '<div class="pm-card">' +
        '<div class="pm-card-label">Invertido Total</div>' +
        '<div class="pm-card-value">$' + totalInv.toLocaleString(undefined, {maximumFractionDigits:0}) + '</div>' +
      '</div>' +
      '<div class="pm-card">' +
        '<div class="pm-card-label">Valor Actual</div>' +
        '<div class="pm-card-value">$' + totalVal.toFixed(0) + '</div>' +
      '</div>' +
      '<div class="pm-card pm-card-pnl" style="border-left-color:' + tColor + '">' +
        '<div class="pm-card-label">P&amp;L Total</div>' +
        '<div class="pm-card-value" style="color:' + tColor + '">' + tSign + '$' + Math.abs(totalPnL).toFixed(0) + ' (' + tSign + totalPct.toFixed(1) + '%)</div>' +
      '</div>' +
    '</div>' +
    '<table>' +
      '<thead><tr>' +
        '<th>Ticker</th><th>Instrumento</th><th>Invertido</th>' +
        '<th>Precio Compra</th><th>Precio Actual</th>' +
        '<th>P&amp;L $</th><th>P&amp;L %</th><th>Delta 1d</th>' +
        '<th>Fecha</th><th>Se\u00f1al</th><th></th>' +
      '</tr></thead>' +
      '<tbody>' + rows + '</tbody>' +
    '</table>' +
    '<p style="margin-top:12px;font-size:.75rem;color:#7f8c8d">&#128161; Precios se actualizan al regenerar el dashboard.</p>';

  section.style.display = 'block';
}

document.addEventListener('DOMContentLoaded', renderPortfolio);
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeBuyModal(); });
</script>"""


def build_trades_section(trades: list) -> str:
    """Build the My Trades performance HTML section."""
    if not trades:
        return ""

    rows = []
    for t in trades:
        ticker    = t["ticker"]
        buy_price = t["price_buy"]
        buy_date  = t["date"][:10]
        days_held = (datetime.now() - datetime.fromisoformat(t["date"])).days

        current = fetch_current_price(ticker)
        if current is None:
            pnl_html  = "<td>—</td><td>—</td>"
            curr_html = "<td>N/A</td>"
        else:
            pnl_d = current - buy_price
            pnl_p = pnl_d / buy_price * 100
            sign  = "+" if pnl_d >= 0 else ""
            color = "#27ae60" if pnl_d >= 0 else "#e74c3c"
            pnl_html  = (f'<td style="color:{color};font-weight:700">'
                         f'{sign}{pnl_d:.2f}</td>'
                         f'<td style="color:{color};font-weight:700">'
                         f'{sign}{pnl_p:.1f}%</td>')
            curr_html = f"<td>${current:.2f}</td>"

        source = t.get("source", "")[:45]
        rows.append(f"""<tr>
          <td><strong>{ticker}</strong></td>
          <td>{t['action']}</td>
          <td>${buy_price:.2f}</td>
          {curr_html}
          {pnl_html}
          <td>{days_held}d</td>
          <td>{buy_date}</td>
          <td style="font-size:.75rem;color:#7f8c8d">{source}</td>
        </tr>""")

    record_cmd = "python scripts/record_trade.py BUY TICKER PRICE --source &quot;Signal description&quot;"
    return f"""
<div class="section">
  <div class="section-header">📒 My Trades — Performance Tracker</div>
  <div class="section-body">
    <table>
      <thead><tr>
        <th>Ticker</th><th>Action</th><th>Buy $</th><th>Now $</th>
        <th>P&amp;L $</th><th>P&amp;L %</th><th>Days</th><th>Date</th><th>Signal Source</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    <p style="margin-top:14px;font-size:.78rem;color:#7f8c8d">
      To record a trade: <code>{record_cmd}</code>
    </p>
  </div>
</div>"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from src.scraper import PolymarketClient, TrendingDetector
from src.correlator import StockCorrelator, RiskyCorrelator
from src.predictor import SignalGenerator
from src.utils import config

logging.getLogger("polymarket").setLevel(logging.WARNING)

# ── Palette ──────────────────────────────────────────────────────────────────
C_BUY   = "#27ae60"
C_SELL  = "#e74c3c"
C_WATCH = "#e67e22"
C_GRID  = "#ecf0f1"
C_TEXT  = "#2c3e50"
C_MUTED = "#7f8c8d"


def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ── 1. Run pipeline ───────────────────────────────────────────────────────────
def run_pipeline():
    print("Running pipeline…")
    client  = PolymarketClient()
    markets = client.get_trending_markets(limit=100)
    client.save_snapshot(markets)

    detector        = TrendingDetector(client)
    trending        = detector.detect_all(markets)

    # Filter markets for charts: same noise filter used in detection
    markets_filtered = [m for m in markets if detector._is_relevant_for_detection(m)]

    correlator      = StockCorrelator()
    stock_signals   = correlator.correlate(trending)

    risky_corr      = RiskyCorrelator()
    risky_signals   = risky_corr.correlate(trending)

    generator       = SignalGenerator()
    inv_signals     = generator.generate(stock_signals)
    generator.save_signals(inv_signals)

    print(f"  markets={len(markets)} (filtered={len(markets_filtered)})  trending={len(trending)}  "
          f"stock={len(stock_signals)}  signals={len(inv_signals)}  "
          f"risky={len(risky_signals)}")
    return markets_filtered, inv_signals, risky_signals


# ── 2. Fetch raw markets (for volume1wk, token IDs) ──────────────────────────
def fetch_raw(client):
    raw = client.get_markets(limit=100)
    # Apply same noise patterns as TrendingDetector so momentum/volume charts
    # exclude sports, esports, and entertainment markets
    detector = TrendingDetector(client)
    return [
        r for r in raw
        if not any(re.search(p, r.get("question", "").lower())
                   for p in detector._NOISE_PATTERNS)
    ]


def get_token_ids(raw):
    out = {}
    for r in raw:
        try:
            tids = json.loads(r.get("clobTokenIds", "[]"))
            out[r.get("question", "")[:65]] = tids[0] if tids else None
        except Exception:
            pass
    return out


def fetch_price_history(token_id, fidelity=60):
    url = (f"https://clob.polymarket.com/prices-history"
           f"?interval=1d&market={token_id}&fidelity={fidelity}")
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("history", [])
    except Exception:
        pass
    return []


# ── 3. Charts ─────────────────────────────────────────────────────────────────
def chart_top_markets(markets, raw):
    token_ids = get_token_ids(raw)
    rows = []
    for m in markets:
        rows.append({
            "question":    m.question[:68],
            "yes_price":   m.outcome_prices.get("Yes"),
            "volume_24h":  m.volume_24h,
            "token_id":    token_ids.get(m.question[:65]),
        })
    df = pd.DataFrame(rows).nlargest(20, "volume_24h")

    fig, ax = plt.subplots(figsize=(13, 7.5), facecolor="white")
    colors = []
    for p in df["yes_price"]:
        if p is None:    colors.append("#bdc3c7")
        elif p > 0.75:   colors.append(C_BUY)
        elif p < 0.25:   colors.append(C_SELL)
        else:            colors.append("#f39c12")

    ax.barh(range(len(df)), df["volume_24h"] / 1e6, color=colors, height=0.7)
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["question"], fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlabel("Volumen 24h (millones USD)", fontsize=10)
    ax.set_title("Top 20 Mercados por Volumen 24h", fontsize=12, fontweight="bold", color=C_TEXT)

    for i, (_, row) in enumerate(df.iterrows()):
        p = row["yes_price"]
        lbl = f"YES:{p:.0%}" if p is not None else ""
        ax.text(row["volume_24h"] / 1e6 + 0.015, i, lbl,
                va="center", fontsize=7.5, color=C_TEXT)

    legend = [
        mpatches.Patch(color=C_BUY,    label="YES > 75%"),
        mpatches.Patch(color=C_SELL,   label="YES < 25%"),
        mpatches.Patch(color="#f39c12",label="Incierto 25-75%"),
    ]
    ax.legend(handles=legend, fontsize=8, loc="lower right")
    ax.set_facecolor("white")
    ax.grid(axis="x", alpha=0.25, color=C_GRID)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    plt.tight_layout()
    b64 = fig_to_b64(fig)
    plt.close(fig)
    return b64


def chart_signals(inv_signals):
    if not inv_signals:
        return None

    df = pd.DataFrame([{
        "ticker":     s.ticker,
        "action":     s.action,
        "confidence": s.confidence,
    } for s in inv_signals]).sort_values("confidence", ascending=True)

    action_color = {
        "BUY":  C_BUY,
        "SELL": C_SELL,
        "WATCH": C_WATCH,
        "HOLD": "#95a5a6",
    }
    bar_colors = [action_color.get(a, "#bdc3c7") for a in df["action"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, max(4, len(df) * 0.38 + 1)),
                                   facecolor="white")

    # donut
    counts = df["action"].value_counts()
    pie_colors = [action_color.get(a, "#bdc3c7") for a in counts.index]
    wedges, texts, autos = ax1.pie(
        counts.values, labels=counts.index, colors=pie_colors,
        autopct="%1.0f%%", startangle=90,
        wedgeprops=dict(width=0.52),
        textprops={"fontsize": 11},
    )
    for at in autos:
        at.set_fontsize(11)
        at.set_fontweight("bold")
    ax1.set_title("Distribución", fontsize=11, fontweight="bold", color=C_TEXT)
    ax1.text(0, 0, f"{len(df)}\nseñales", ha="center", va="center",
             fontsize=13, fontweight="bold", color=C_TEXT)

    # horizontal bars
    ax2.barh(range(len(df)), df["confidence"], color=bar_colors, height=0.65)
    ax2.set_yticks(range(len(df)))
    ax2.set_yticklabels(
        [f"{row['action']:5} {row['ticker']}" for _, row in df.iterrows()],
        fontsize=8.5
    )
    ax2.set_xlim(0, 1.18)
    ax2.axvline(0.75, color=C_TEXT, linestyle="--", alpha=0.35, linewidth=1)
    ax2.set_xlabel("Confianza", fontsize=10)
    ax2.set_title("Confianza por señal", fontsize=11, fontweight="bold", color=C_TEXT)
    for i, (_, row) in enumerate(df.iterrows()):
        ax2.text(row["confidence"] + 0.01, i, f"{row['confidence']:.0%}",
                 va="center", fontsize=7.5)
    ax2.set_facecolor("white")
    ax2.grid(axis="x", alpha=0.25, color=C_GRID)
    for spine in ["top", "right"]:
        ax2.spines[spine].set_visible(False)

    plt.suptitle("Investment Signals", fontsize=12, fontweight="bold",
                 color=C_TEXT, y=1.01)
    plt.tight_layout()
    b64 = fig_to_b64(fig)
    plt.close(fig)
    return b64


def chart_price_history(finsignal_data: dict):
    """
    Show 7-day probability history for Polymarket markets that matched
    FinSignal newsletter signals. Much more useful than random top-volume markets:
    you can see how the Polymarket crowd priced an event before/after the newsletter.
    """
    signals = finsignal_data.get("signals", [])
    if not signals:
        return None

    # Build token_id lookup: fetch enough raw markets to cover FinSignal matches
    client = PolymarketClient()
    raw = client.get_markets(limit=200)
    token_map = {}
    for r in raw:
        try:
            tids = json.loads(r.get("clobTokenIds", "[]"))
            if tids:
                token_map[r["question"]] = tids[0]
        except Exception:
            pass

    # Collect (label, token_id, direction) for each FinSignal match
    dir_colors_map = {"BUY": C_BUY, "SELL": C_SELL, "WATCH": C_WATCH, "HOLD": C_MUTED}
    candidates = []
    for s in signals:
        ticker    = s.get("ticker", "")
        direction = s.get("direction", "WATCH")
        for pm in s.get("polymarket_matches", []):
            question = pm.get("question", "")
            tid = token_map.get(question)
            if tid:
                candidates.append({
                    "label":     f"{ticker} ({direction})",
                    "question":  question[:55],
                    "token_id":  tid,
                    "direction": direction,
                })

    if not candidates:
        return None

    # Deduplicate by token_id
    seen = set()
    unique = []
    for c in candidates:
        if c["token_id"] not in seen:
            seen.add(c["token_id"])
            unique.append(c)

    # Fetch 7-day history; skip flat lines (range < 3%) — those add no info
    histories = []
    for c in unique:
        h = fetch_price_history(c["token_id"], fidelity=60)
        if not h or len(h) < 3:
            continue
        prices = [p["p"] for p in h]
        if max(prices) - min(prices) < 0.03:   # flat — skip
            continue
        histories.append((c["label"], c["question"], h, c["direction"]))
        if len(histories) >= 9:
            break

    if not histories:
        return None

    ncols = 3
    nrows = (len(histories) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(15, nrows * 3.4), facecolor="white")
    import numpy as np; axes = np.array(axes).flatten()

    for ax, (label, question, history, direction) in zip(axes, histories):
        ts     = [datetime.utcfromtimestamp(p["t"]) for p in history]
        prices = [p["p"] for p in history]

        sig_color = dir_colors_map.get(direction, C_MUTED)
        trend_color = C_BUY if (len(prices) >= 2 and prices[-1] >= prices[0]) else C_SELL

        ax.plot(ts, prices, color=trend_color, linewidth=2)
        ax.fill_between(ts, prices, alpha=0.12, color=trend_color)
        ax.axhline(0.5, color=C_MUTED, linestyle="--", alpha=0.4, linewidth=0.8)

        # Mark start and end
        if len(prices) >= 2:
            delta = prices[-1] - prices[0]
            sign  = "+" if delta >= 0 else ""
            ax.annotate(
                f"Ahora: {prices[-1]:.0%}  ({sign}{delta:.0%})",
                xy=(ts[-1], prices[-1]),
                xytext=(-65, 8), textcoords="offset points",
                fontsize=7.5, fontweight="bold", color=trend_color,
            )

        ax.set_ylim(-0.05, 1.05)
        # Two-line title: ticker+direction / market question
        ax.set_title(f"{label}\n{question}{'…' if len(question) >= 55 else ''}",
                     fontsize=7, fontweight="bold", color=C_TEXT, linespacing=1.4)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
        ax.tick_params(axis="x", labelsize=6, rotation=30)
        ax.tick_params(axis="y", labelsize=7)
        ax.set_facecolor("white")
        ax.grid(alpha=0.2, color=C_GRID)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)

    for ax in axes[len(histories):]:
        ax.set_visible(False)

    plt.suptitle("📈 FinSignal × Polymarket — Historial 7 días de mercados relacionados",
                 fontsize=11, fontweight="bold", color=C_TEXT, y=1.01)
    plt.tight_layout()
    b64 = fig_to_b64(fig)
    plt.close(fig)
    return b64


def chart_momentum(raw):
    rows = []
    for r in raw:
        try:
            vol24 = float(r.get("volume24hr", 0) or 0)
            vol1w = float(r.get("volume1wk",  0) or 0)
            if vol1w > 0 and vol24 > 30_000:
                rows.append({
                    "question": r.get("question", "")[:60],
                    "vol_24h":  vol24,
                    "avg_day":  vol1w / 7,
                    "momentum": vol24 / (vol1w / 7),
                })
        except Exception:
            pass

    if not rows:
        return None

    df = pd.DataFrame(rows).nlargest(20, "momentum")

    fig, ax = plt.subplots(figsize=(13, 7.5), facecolor="white")
    bar_colors = [
        C_SELL    if r > 4   else
        C_WATCH   if r > 2   else
        "#95a5a6"
        for r in df["momentum"]
    ]
    ax.barh(range(len(df)), df["momentum"], color=bar_colors, height=0.7)
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["question"], fontsize=8.5)
    ax.invert_yaxis()
    ax.axvline(1.0, color=C_TEXT,  linestyle="--", alpha=0.4, linewidth=1)
    ax.axvline(4.0, color=C_SELL,  linestyle="--", alpha=0.35, linewidth=1)
    ax.set_xlabel("Vol 24h / Promedio diario semanal", fontsize=10)
    ax.set_title("Momentum — Actividad Hoy vs Promedio Semanal",
                 fontsize=12, fontweight="bold", color=C_TEXT)

    for i, (_, row) in enumerate(df.iterrows()):
        ax.text(row["momentum"] + 0.05, i, f"{row['momentum']:.1f}x",
                va="center", fontsize=7.5, color=C_TEXT)

    legend = [
        mpatches.Patch(color=C_SELL,  label="Spike fuerte (>4x)"),
        mpatches.Patch(color=C_WATCH, label="Spike moderado (2-4x)"),
        mpatches.Patch(color="#95a5a6", label="Normal (<2x)"),
    ]
    ax.legend(handles=legend, fontsize=8, loc="lower right")
    ax.set_facecolor("white")
    ax.grid(axis="x", alpha=0.25, color=C_GRID)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    plt.tight_layout()
    b64 = fig_to_b64(fig)
    plt.close(fig)
    return b64


# ── 4. Build HTML ─────────────────────────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polymarket Dashboard — {date}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f4f6f9; color: #2c3e50; }}

  /* Header */
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
             color: white; padding: 28px 40px; display: flex;
             justify-content: space-between; align-items: center; }}
  .header h1 {{ font-size: 1.7rem; font-weight: 700; letter-spacing: -0.5px; }}
  .header .subtitle {{ font-size: 0.85rem; opacity: 0.7; margin-top: 4px; }}
  .header .date {{ font-size: 0.9rem; opacity: 0.8; text-align: right; }}

  /* KPI cards */
  .kpi-row {{ display: flex; gap: 16px; padding: 24px 40px 8px; flex-wrap: wrap; }}
  .kpi {{ background: white; border-radius: 12px; padding: 18px 24px;
          flex: 1; min-width: 140px; box-shadow: 0 2px 8px rgba(0,0,0,0.07); }}
  .kpi .label {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px;
                 color: #7f8c8d; font-weight: 600; }}
  .kpi .value {{ font-size: 2rem; font-weight: 700; margin-top: 4px; }}
  .kpi .sub   {{ font-size: 0.78rem; color: #7f8c8d; margin-top: 2px; }}
  .kpi.buy    {{ border-left: 4px solid #27ae60; }}
  .kpi.sell   {{ border-left: 4px solid #e74c3c; }}
  .kpi.watch  {{ border-left: 4px solid #e67e22; }}
  .kpi.total  {{ border-left: 4px solid #3498db; }}
  .kpi.buy   .value {{ color: #27ae60; }}
  .kpi.sell  .value {{ color: #e74c3c; }}
  .kpi.watch .value {{ color: #e67e22; }}
  .kpi.total .value {{ color: #3498db; }}

  /* Section */
  .section {{ margin: 16px 40px; background: white; border-radius: 12px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.07); overflow: hidden; }}
  .section-header {{ padding: 16px 24px 12px; border-bottom: 1px solid #ecf0f1;
                     font-size: 1rem; font-weight: 700; color: #2c3e50; }}
  .section-body {{ padding: 20px 24px; }}
  .chart-img {{ width: 100%; height: auto; display: block; border-radius: 6px; }}

  /* Signals table */
  table {{ width: 100%; border-collapse: collapse; font-size: 0.83rem; }}
  thead tr {{ background: #2c3e50; color: white; }}
  thead th {{ padding: 10px 14px; text-align: left; font-weight: 600;
              font-size: 0.78rem; letter-spacing: 0.3px; }}
  tbody tr {{ border-bottom: 1px solid #ecf0f1; transition: background 0.15s; }}
  tbody tr:hover {{ background: #f8f9fa; }}
  tbody td {{ padding: 9px 14px; vertical-align: middle; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 20px;
            font-size: 0.75rem; font-weight: 700; letter-spacing: 0.3px; }}
  .badge-BUY   {{ background: #d5f5e3; color: #1e8449; }}
  .badge-SELL  {{ background: #fadbd8; color: #922b21; }}
  .badge-WATCH {{ background: #fef3cd; color: #7d6608; }}
  .badge-HOLD  {{ background: #eaecee; color: #566573; }}
  .timing-act_now {{ color: #27ae60; font-weight: 700; }}
  .timing-prepare {{ color: #2980b9; font-weight: 600; }}
  .timing-late    {{ color: #e67e22; }}
  .timing-wait    {{ color: #7f8c8d; }}
  .conf-bar {{ display: inline-block; height: 6px; border-radius: 3px;
               background: #3498db; vertical-align: middle; margin-right: 6px; }}
  .conf-high {{ background: #27ae60; }}
  .conf-med  {{ background: #e67e22; }}
  .source    {{ font-size: 0.75rem; color: #7f8c8d; max-width: 320px; }}

  /* Priority topics */
  .badge-priority {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
                     font-size: 0.68rem; font-weight: 700; letter-spacing: 0.2px;
                     background: #fef9e7; color: #b7770d; border: 1px solid #f0c040;
                     margin-left: 5px; white-space: nowrap; }}
  .priority-row {{ background: #fffdf0 !important; }}
  .priority-row:hover {{ background: #fdf6d3 !important; }}
  .section-priority {{ border-left: 4px solid #f0c040; }}
  .priority-table th {{ background: #2c3e50; }}

  /* Footer */
  .footer {{ text-align: center; padding: 20px; font-size: 0.75rem;
             color: #7f8c8d; margin-top: 8px; }}
  {portfolio_css}
</style>
</head>
<body>

<div class="header">
  <div>
    <div class="h1">📈 Polymarket Investment Adviser</div>
    <div class="subtitle">Weekly Dashboard — Prediction Markets → Investment Signals</div>
  </div>
  <div class="date">
    Generado: {datetime}<br>
    Próxima corrida: lunes
  </div>
</div>

<div class="kpi-row">
  <div class="kpi total">
    <div class="label">Mercados analizados</div>
    <div class="value">{n_markets}</div>
    <div class="sub">top por volumen 24h</div>
  </div>
  <div class="kpi total">
    <div class="label">Señales detectadas</div>
    <div class="value">{n_signals}</div>
    <div class="sub">con correlación financiera</div>
  </div>
  <div class="kpi sell">
    <div class="label">SELL</div>
    <div class="value">{n_sell}</div>
    <div class="sub">señales de venta</div>
  </div>
  <div class="kpi buy">
    <div class="label">BUY</div>
    <div class="value">{n_buy}</div>
    <div class="sub">señales de compra</div>
  </div>
  <div class="kpi watch">
    <div class="label">WATCH</div>
    <div class="value">{n_watch}</div>
    <div class="sub">monitorear</div>
  </div>
  <div class="kpi total">
    <div class="label">Top vol 24h</div>
    <div class="value">{top_vol}</div>
    <div class="sub">{top_market}</div>
  </div>
</div>

<!-- Priority Topics Watch -->
{priority_watch_html}

<!-- Portfolio section (populated by JS from localStorage) -->
{portfolio_section_html}

<!-- Signals table -->
<div class="section">
  <div class="section-header">🎯 Investment Signals</div>
  <div class="section-body">
    <table>
      <thead>
        <tr>
          <th>Acción</th>
          <th>Ticker</th>
          <th>Nombre</th>
          <th>Confianza</th>
          <th>Timing</th>
          <th>YES %</th>
          <th>Vol 24h (fuente)</th>
          <th>Mercado Polymarket</th>
          <th>Comprar</th>
        </tr>
      </thead>
      <tbody>
        {signal_rows}
      </tbody>
    </table>
  </div>
</div>

<!-- Chart: signals -->
{chart_signals_html}

<!-- Chart: top markets -->
<div class="section">
  <div class="section-header">📊 Top 20 Mercados por Volumen 24h</div>
  <div class="section-body">
    <img class="chart-img" src="data:image/png;base64,{chart_top_markets}">
  </div>
</div>

<!-- Chart: momentum -->
<div class="section">
  <div class="section-header">⚡ Momentum — Actividad Hoy vs Promedio Semanal</div>
  <div class="section-body">
    <img class="chart-img" src="data:image/png;base64,{chart_momentum}">
  </div>
</div>

<!-- Chart: price history -->
{chart_history_html}

<!-- Non-Obvious Signals -->
{risky_section_html}

<!-- FinSignal: Newsletter → Polymarket -->
{finsignal_section_html}

<!-- My Trades -->
{trades_section_html}

<div class="footer">
  Polymarket Investment Adviser · {date} · Datos: Polymarket Gamma API + CLOB API
</div>
{buy_modal_html}
{dashboard_data_script}
{portfolio_js}
</body>
</html>"""


def build_risky_section(risky_signals) -> str:
    """Build the Non-Obvious Signals HTML section."""
    if not risky_signals:
        return ""

    mech_icon = {
        "competitor":   "🥊",
        "supply_chain": "⛓️",
        "currency":     "💱",
        "regulatory":   "⚖️",
    }
    rows = []
    for s in risky_signals:
        icon = mech_icon.get(s.mechanism, "🔗")
        direction_color = "#27ae60" if s.direction == "positive" else "#e74c3c"
        direction_label = "▲ Long" if s.direction == "positive" else "▼ Short"
        conf_pct = int(s.confidence * 100)
        rows.append(f"""<tr>
          <td><strong>{s.ticker}</strong></td>
          <td>{s.name}</td>
          <td style="color:{direction_color};font-weight:700">{direction_label}</td>
          <td>{conf_pct}%</td>
          <td>{icon} <em>{s.mechanism}</em></td>
          <td style="font-size:.78rem">{s.rationale}</td>
          <td style="font-size:.75rem;color:#7f8c8d">{s.source_question[:55]}…</td>
        </tr>""")

    return f"""
<div class="section">
  <div class="section-header">⚡ Non-Obvious Signals
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      experimental — second-order effects, verify before acting
    </span>
  </div>
  <div class="section-body">
    <table>
      <thead><tr>
        <th>Ticker</th><th>Name</th><th>Direction</th><th>Conf</th>
        <th>Mechanism</th><th>Why this instrument</th><th>Triggered by</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>
</div>"""


FINSIGNAL_FILE = Path(__file__).parent / "data" / "finsignal" / "signals_latest.json"


def load_finsignal() -> dict:
    if not FINSIGNAL_FILE.exists():
        return {}
    try:
        data = json.loads(FINSIGNAL_FILE.read_text())
    except Exception:
        return {}

    # Run Polymarket matching on every signal that hasn't been matched yet.
    # This handles signals written by Claude (which have polymarket_matches: []).
    try:
        from src.finsignal.polymarket_matcher import match_ticker_to_markets, classify_alignment
        from src.finsignal.newsletter_parser import TickerMention

        enriched = False
        for s in data.get("signals", []):
            if s.get("polymarket_matches"):   # already matched — skip
                continue
            ticker = s.get("ticker", "")
            if not ticker:
                continue
            mention = TickerMention(
                ticker=ticker,
                direction=s.get("direction", "MENTION"),
                confidence=s.get("confidence", 0.0),
                context=s.get("context", ""),
                source=s.get("source", ""),
                date=s.get("date", ""),
            )
            matches = match_ticker_to_markets(mention, top_n=3)
            if matches:
                s["polymarket_matches"] = matches
                s["has_pm_signal"] = True
                s["pm_confirms"] = any(
                    classify_alignment(mention, m) == "CONFIRMS" for m in matches
                )
                enriched = True

        # Persist enriched matches back to disk so next load is instant
        if enriched:
            FINSIGNAL_FILE.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        import logging
        logging.getLogger("polymarket").warning(f"PM matching failed: {exc}")

    return data


def _build_signal_row(s, today, dir_colors):
    """Build a single <tr> for a FinSignal entry."""
    from datetime import datetime
    ticker     = s.get("ticker", "")
    direction  = s.get("direction", "MENTION")
    confidence = s.get("confidence", 0)
    source     = s.get("source", "")[:55]
    context    = s.get("context", "")[:100]
    sig_date   = s.get("date", "")
    pm_matches = s.get("polymarket_matches", [])
    confirms   = s.get("pm_confirms", False)

    age_label = ""
    age_color = "#7f8c8d"
    age_days  = 9999
    if sig_date:
        try:
            d = datetime.strptime(sig_date[:10], "%Y-%m-%d").date()
            age_days  = (today - d).days
            age_label = sig_date[:10]
            if age_days <= 7:
                age_color = "#27ae60"
            elif age_days <= 30:
                age_color = "#e67e22"
            else:
                age_color = "#c0392b"
        except Exception:
            age_label = sig_date[:10]

    bg, fg = dir_colors.get(direction, ("#eaecee", "#566573"))
    badge = (f'<span style="background:{bg};color:{fg};padding:2px 9px;'
             f'border-radius:12px;font-weight:700;font-size:.76rem">{direction}</span>')
    conf_pct = int(confidence * 100)

    pm_cell = "—"
    if pm_matches:
        first = pm_matches[0]
        align_icon = "🟢" if confirms else "🔵"
        try:
            yes_pct = f"{float(first.get('yes_price', 0)):.0%}"
        except Exception:
            yes_pct = "?"
        pm_cell = (f'{align_icon} <a href="{first["url"]}" target="_blank" '
                   f'style="font-size:.76rem;color:#2980b9">'
                   f'{first["question"][:55]}</a>'
                   f' <span style="color:#7f8c8d">YES={yes_pct}</span>')

    return age_days, f"""<tr>
      <td><strong>{ticker}</strong></td>
      <td>{badge}</td>
      <td>{conf_pct}%</td>
      <td style="font-size:.76rem;font-weight:600;color:{age_color}">{age_label}</td>
      <td style="font-size:.75rem;color:#7f8c8d">{source}</td>
      <td style="font-size:.76rem">{context}…</td>
      <td>{pm_cell}</td>
    </tr>"""


def build_finsignal_section(finsignal_data: dict) -> str:
    """Build the FinSignal newsletter pipeline HTML section."""
    from datetime import datetime
    from collections import Counter

    signals      = finsignal_data.get("signals", [])
    collected_at = finsignal_data.get("collected_at", "")[:16].replace("T", " ")
    emails_count = finsignal_data.get("emails_processed", 0)

    if not signals:
        return """
<div class="section">
  <div class="section-header">📬 FinSignal — Newsletter Pipeline
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      No data yet — run: python scripts/finsignal_collect.py --demo
    </span>
  </div>
</div>"""

    dir_colors = {
        "BUY":     ("#d5f5e3", "#1e8449"),
        "SELL":    ("#fadbd8", "#922b21"),
        "HOLD":    ("#eaecee", "#566573"),
        "WATCH":   ("#fef9e7", "#7d6608"),
        "MENTION": ("#eaf4fb", "#1a5276"),
    }

    today = datetime.utcnow().date()

    # Detectar tickers mencionados múltiples veces (convergencia entre newsletters)
    ticker_counts = Counter(s.get("ticker", "") for s in signals)
    repeated = {t for t, c in ticker_counts.items() if c > 1}

    # Separar activas (≤30 días) e históricas (>30 días), ordenar por fecha desc
    active_rows   = []
    historic_rows = []

    for s in sorted(signals, key=lambda x: x.get("date", ""), reverse=True):
        ticker = s.get("ticker", "")
        age_days, row_html = _build_signal_row(s, today, dir_colors)

        # Inyectar badge de convergencia si aparece más de una vez
        if ticker in repeated:
            row_html = row_html.replace(
                f"<strong>{ticker}</strong>",
                f'<strong>{ticker}</strong> '
                f'<span title="Aparece {ticker_counts[ticker]}x en newsletters" '
                f'style="background:#d2b4de;color:#6c3483;padding:1px 6px;'
                f'border-radius:10px;font-size:.68rem;font-weight:700">'
                f'×{ticker_counts[ticker]}</span>'
            )

        if age_days <= 30:
            active_rows.append(row_html)
        else:
            historic_rows.append(row_html)

    table_head = """<table>
      <thead><tr>
        <th>Ticker</th><th>Direction</th><th>Conf</th>
        <th>Fecha señal</th><th>Source Newsletter</th><th>Context</th><th>Polymarket Match</th>
      </tr></thead>"""

    active_html = ""
    if active_rows:
        active_html = f"""{table_head}
      <tbody>{"".join(active_rows)}</tbody>
    </table>"""
    else:
        active_html = '<p style="color:#7f8c8d;font-size:.85rem">Sin señales activas (≤30 días).</p>'

    historic_html = ""
    if historic_rows:
        historic_html = f"""
    <details style="margin-top:16px">
      <summary style="cursor:pointer;font-size:.83rem;font-weight:600;color:#7f8c8d;
                      padding:6px 0;border-top:1px solid #eaecee">
        🕰 Históricas ({len(historic_rows)} señales, >30 días) — clic para expandir
      </summary>
      <div style="margin-top:8px;opacity:.8">
        {table_head}
          <tbody>{"".join(historic_rows)}</tbody>
        </table>
      </div>
    </details>"""

    n_active   = len(active_rows)
    n_historic = len(historic_rows)
    convergence_note = ""
    if repeated:
        tickers_rep = ", ".join(sorted(repeated))
        convergence_note = (f'&nbsp;|&nbsp; 🔁 Convergencia (múltiples fuentes): '
                            f'<strong>{tickers_rep}</strong>')

    return f"""
<div class="section">
  <div class="section-header">📬 FinSignal — Newsletter Recommendations vs Polymarket
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      {n_active} activas · {n_historic} históricas · {emails_count} emails · Updated: {collected_at}
    </span>
  </div>
  <div class="section-body">
    {active_html}
    {historic_html}
    <p style="margin-top:12px;font-size:.76rem;color:#7f8c8d">
      🟢 Polymarket CONFIRMS &nbsp;|&nbsp; 🔵 PM market relacionado
      {convergence_note}
    </p>
  </div>
</div>"""


def build_priority_watch_section(markets: list, priority_topics: list) -> str:
    """
    Build a dedicated section showing all markets related to user priority topics.
    These markets always appear regardless of volume/trending thresholds.
    """
    if not priority_topics:
        return ""

    priority_markets = []
    for m in markets:
        matched, topic_name = match_priority_topic(m.question, priority_topics)
        if matched:
            priority_markets.append((m, topic_name))

    if not priority_markets:
        # Show section anyway so user knows no priority markets are active
        topic_names = ", ".join(t["name"] for t in priority_topics)
        return f"""
<div class="section section-priority">
  <div class="section-header">⭐ Priority Watch — {topic_names}
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      Sin mercados activos en Polymarket para estos temas hoy
    </span>
  </div>
</div>"""

    # Sort: highest volume first
    priority_markets.sort(key=lambda x: x[0].volume_24h, reverse=True)

    topic_names = ", ".join(t["name"] for t in priority_topics)
    rows = []
    for m, topic_name in priority_markets:
        yes_price = m.outcome_prices.get("Yes")
        yes_str   = f"{yes_price:.0%}" if yes_price is not None else "—"
        if yes_price is None:
            price_color = "#7f8c8d"
        elif yes_price > 0.75:
            price_color = "#27ae60"
        elif yes_price < 0.25:
            price_color = "#e74c3c"
        else:
            price_color = "#e67e22"

        end_str = "—"
        days_left_str = ""
        if m.end_date:
            try:
                end_dt = datetime.fromisoformat(m.end_date.replace("Z", "+00:00"))
                end_str = end_dt.strftime("%Y-%m-%d")
                days_left = (end_dt.replace(tzinfo=None) - datetime.now()).days
                if days_left >= 0:
                    days_left_str = f" ({days_left}d)"
            except Exception:
                pass

        vol_str = f"${m.volume_24h/1e3:.0f}K" if m.volume_24h >= 1000 else f"${m.volume_24h:.0f}"

        rows.append(f"""<tr class="priority-row">
          <td><span class="badge-priority">⭐ {topic_name}</span></td>
          <td style="font-size:.83rem">{m.question[:90]}{'…' if len(m.question) > 90 else ''}</td>
          <td style="font-weight:700;color:{price_color};text-align:center">{yes_str}</td>
          <td style="text-align:center">{vol_str}</td>
          <td style="font-size:.78rem;color:#7f8c8d">{end_str}{days_left_str}</td>
          <td style="font-size:.75rem;color:#7f8c8d">{m.category or '—'}</td>
        </tr>""")

    return f"""
<div class="section section-priority">
  <div class="section-header">⭐ Priority Watch — {topic_names}
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      {len(priority_markets)} mercado{'s' if len(priority_markets) != 1 else ''} activo{'s' if len(priority_markets) != 1 else ''} · siempre visible independientemente del volumen
    </span>
  </div>
  <div class="section-body">
    <table class="priority-table">
      <thead><tr>
        <th>Tema</th><th>Mercado</th><th style="text-align:center">YES %</th>
        <th style="text-align:center">Vol 24h</th><th>Cierre</th><th>Categoría</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>
</div>"""


def build_signal_rows(inv_signals, priority_topics: list = None):
    if priority_topics is None:
        priority_topics = []

    # Priority signals float to the top, then sort by action → confidence
    action_order = {"BUY": 0, "SELL": 1, "WATCH": 2, "HOLD": 3}

    def _signal_sort_key(s):
        is_prio, _ = match_priority_topic(s.source_market, priority_topics)
        return (0 if is_prio else 1, action_order.get(s.action, 9), -s.confidence)

    sorted_signals = sorted(inv_signals, key=_signal_sort_key)

    rows = []
    for s in sorted_signals:
        conf_pct = int(s.confidence * 100)
        bar_w    = int(s.confidence * 80)
        bar_cls  = "conf-high" if conf_pct >= 75 else "conf-med"
        timing_cls = f"timing-{s.timing_action}"

        is_prio, topic_name = match_priority_topic(s.source_market, priority_topics)
        prio_badge = (f' <span class="badge-priority">⭐ {topic_name}</span>'
                      if is_prio else "")
        row_cls = ' class="priority-row"' if is_prio else ""

        name_esc   = s.instrument_name.replace('"', '&quot;')
        source_esc = s.source_market.replace('"', '&quot;')
        buy_btn    = ('<td><button class="buy-btn" onclick="openBuyModal(this)">'
                      '🛒 Buy</button></td>') if s.action == "BUY" else "<td></td>"

        rows.append(f"""
        <tr{row_cls} data-ticker="{s.ticker}" data-name="{name_esc}" data-yes-price="{s.yes_price:.6f}" data-source="{source_esc}" data-action="{s.action}">
          <td><span class="badge badge-{s.action}">{s.action}</span></td>
          <td><strong>{s.ticker}</strong>{prio_badge}</td>
          <td>{s.instrument_name}</td>
          <td>
            <span class="conf-bar {bar_cls}" style="width:{bar_w}px"></span>
            {conf_pct}%
          </td>
          <td><span class="{timing_cls}">{s.timing_action}</span></td>
          <td>{s.yes_price:.0%}</td>
          <td>${s.volume_24h:,.0f}</td>
          <td class="source">{s.source_market[:70]}</td>
          {buy_btn}
        </tr>""")
    return "\n".join(rows)


# ── 5. Daily Snapshot ─────────────────────────────────────────────────────────
def save_daily_snapshot(
    now: datetime,
    markets: list,
    inv_signals: list,
    risky_signals: list,
    finsignal_data: dict,
    n_buy: int,
    n_sell: int,
    n_watch: int,
) -> Path:
    """
    Save a structured JSON snapshot of everything shown in today's dashboard.

    Stored at: data/snapshots/YYYY-MM-DD/snapshot_YYYY-MM-DD.json
    One file per day (overwrites if regenerated same day).
    """
    date_str = now.strftime("%Y-%m-%d")
    snapshot_dir = config.data_dir / "snapshots" / date_str
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Top market by volume
    top = max(markets, key=lambda m: m.volume_24h) if markets else None
    top_market_data = {
        "question":   top.question if top else "",
        "yes_price":  top.outcome_prices.get("Yes") if top else None,
        "volume_24h": top.volume_24h if top else 0,
        "category":   top.category if top else "",
    }

    # Avg confidence
    avg_conf = round(
        sum(s.confidence for s in inv_signals) / len(inv_signals), 4
    ) if inv_signals else 0.0

    snapshot = {
        "date":         date_str,
        "generated_at": now.isoformat(),
        "summary": {
            "markets_analyzed":  len(markets),
            "n_buy":             n_buy,
            "n_sell":            n_sell,
            "n_watch":           n_watch,
            "n_signals_total":   len(inv_signals),
            "avg_confidence":    avg_conf,
            "top_market":        top_market_data,
        },
        "investment_signals": [s.to_dict() for s in inv_signals],
        "risky_signals": [
            {
                "ticker":          rs.ticker,
                "name":            rs.name,
                "direction":       rs.direction,
                "confidence":      rs.confidence,
                "mechanism":       rs.mechanism,
                "rationale":       rs.rationale,
                "source_question": rs.source_question,
                "source_volume":   rs.source_volume,
            }
            for rs in risky_signals
        ],
        "top_markets": [
            {
                "question":   m.question,
                "yes_price":  m.outcome_prices.get("Yes"),
                "no_price":   m.outcome_prices.get("No"),
                "volume_24h": m.volume_24h,
                "liquidity":  m.liquidity,
                "category":   m.category,
                "end_date":   m.end_date,
            }
            for m in sorted(markets, key=lambda m: m.volume_24h, reverse=True)[:30]
        ],
        "finsignal": finsignal_data,
    }

    out_path = snapshot_dir / f"snapshot_{date_str}.json"
    out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Snapshot saved:   {out_path}")
    return out_path


# ── 6. Main ───────────────────────────────────────────────────────────────────
def main():
    open_browser = "--no-open" not in sys.argv

    markets, inv_signals, risky_signals = run_pipeline()

    client = PolymarketClient()
    raw    = fetch_raw(client)

    print("Generating charts…")
    finsignal_data   = load_finsignal()           # needed by chart_price_history
    b64_top      = chart_top_markets(markets, raw)
    b64_signals  = chart_signals(inv_signals)
    b64_history  = chart_price_history(finsignal_data)
    b64_momentum = chart_momentum(raw)

    # KPIs
    n_buy   = sum(1 for s in inv_signals if s.action == "BUY")
    n_sell  = sum(1 for s in inv_signals if s.action == "SELL")
    n_watch = sum(1 for s in inv_signals if s.action in ("WATCH", "HOLD"))

    top = max(markets, key=lambda m: m.volume_24h)
    top_vol_str = f"${top.volume_24h/1e6:.1f}M"
    top_market_str = top.question[:30] + "…"

    now = datetime.now()

    chart_signals_html = ""
    if b64_signals:
        chart_signals_html = f"""
<div class="section">
  <div class="section-header">📉 Distribución y Confianza de Señales</div>
  <div class="section-body">
    <img class="chart-img" src="data:image/png;base64,{b64_signals}">
  </div>
</div>"""

    chart_history_html = ""
    if b64_history:
        chart_history_html = f"""
<div class="section">
  <div class="section-header">📈 FinSignal × Polymarket — Probabilidad últimos 7 días
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      Mercados de Polymarket relacionados con señales de newsletters
    </span>
  </div>
  <div class="section-body">
    <img class="chart-img" src="data:image/png;base64,{b64_history}">
  </div>
</div>"""

    print("Loading trade performance, FinSignal data, and priority topics…")
    trades            = load_trades()
    trades_section    = build_trades_section(trades)
    risky_section     = build_risky_section(risky_signals)
    finsignal_section = build_finsignal_section(finsignal_data)

    priority_topics   = load_priority_topics()
    n_priority = sum(1 for m in markets if match_priority_topic(m.question, priority_topics)[0])
    print(f"  Priority topics: {len(priority_topics)} topics, "
          f"{n_priority} matching markets found")
    priority_watch_section = build_priority_watch_section(markets, priority_topics)

    # Fetch current stock prices for BUY signals (for portfolio P&L tracking)
    buy_tickers = list({s.ticker for s in inv_signals if s.action == "BUY"})
    print(f"Fetching current prices for BUY tickers: {buy_tickers}")
    current_prices = fetch_current_prices_batch(buy_tickers)
    print(f"  Prices: {current_prices}")
    dashboard_data = {"date": now.strftime("%Y-%m-%d"), "current_prices": current_prices}
    dashboard_data_script = (
        f'<script>window.DASHBOARD_DATA = {json.dumps(dashboard_data)};</script>'
    )

    html = HTML_TEMPLATE.format(
        date            = now.strftime("%Y-%m-%d"),
        datetime        = now.strftime("%Y-%m-%d %H:%M"),
        n_markets       = len(markets),
        n_signals       = len(inv_signals),
        n_buy           = n_buy,
        n_sell          = n_sell,
        n_watch         = n_watch,
        top_vol         = top_vol_str,
        top_market      = top_market_str,
        signal_rows     = build_signal_rows(inv_signals, priority_topics),
        chart_top_markets  = b64_top,
        chart_signals_html = chart_signals_html,
        chart_momentum     = b64_momentum or "",
        chart_history_html = chart_history_html,
        risky_section_html   = risky_section,
        finsignal_section_html = finsignal_section,
        trades_section_html  = trades_section,
        priority_watch_html  = priority_watch_section,
        portfolio_css          = PORTFOLIO_CSS,
        portfolio_section_html = PORTFOLIO_SECTION_HTML,
        buy_modal_html         = BUY_MODAL_HTML,
        dashboard_data_script  = dashboard_data_script,
        portfolio_js           = PORTFOLIO_JS,
    )

    out_path = config.processed_data_dir / f"dashboard_{now.strftime('%Y-%m-%d')}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\nDashboard saved: {out_path}")

    save_daily_snapshot(
        now=now,
        markets=markets,
        inv_signals=inv_signals,
        risky_signals=risky_signals,
        finsignal_data=finsignal_data,
        n_buy=n_buy,
        n_sell=n_sell,
        n_watch=n_watch,
    )

    if open_browser:
        webbrowser.open(f"file://{out_path.resolve()}")
        print("Opening in browser…")

    return str(out_path)


if __name__ == "__main__":
    main()

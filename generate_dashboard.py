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
WATCHLIST_FILE       = Path(__file__).parent / "data" / "watchlist.json"
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


def load_watchlist() -> list:
    """Load user-defined watchlist from data/watchlist.json."""
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text()).get("tickers", [])
        except Exception:
            pass
    return []


def save_watchlist(tickers: list):
    """Persist updated watchlist back to disk."""
    WATCHLIST_FILE.write_text(
        json.dumps({"tickers": tickers}, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def match_watchlist_to_markets(entry: dict, markets: list, raw_markets: list) -> list:
    """
    Find Polymarket markets relevant to a watchlist ticker.
    Matches against the ticker's keywords AND the ticker symbol itself
    across the filtered market list.
    """
    keywords = [k.lower() for k in entry.get("keywords", [])]
    ticker   = entry.get("ticker", "").lower()
    name     = entry.get("name", "").lower()
    matches  = []

    for m in markets:
        q = m.question.lower()
        # Match if any keyword hits, or ticker/name appears in question
        hit = (
            any(kw in q for kw in keywords) or
            ticker in q or
            (len(name) > 3 and name in q)
        )
        if hit:
            yes_price = m.outcome_prices.get("Yes")
            matches.append({
                "question":  m.question,
                "yes_price": yes_price,
                "volume_24h": m.volume_24h,
                "end_date":  m.end_date or "",
                "slug":      getattr(m, "slug", ""),
                "url":       f"https://polymarket.com/event/{m.slug}" if getattr(m, "slug", "") else "",
            })

    # Also scan raw markets (includes non-filtered, catches more niche markets)
    seen = {m["question"] for m in matches}
    for r in raw_markets:
        q = r.get("question", "").lower()
        if q in seen:
            continue
        hit = (
            any(kw in q for kw in keywords) or
            ticker in q or
            (len(name) > 3 and name in q)
        )
        if hit:
            try:
                yes_price = float(r.get("outcomePrices", ["0.5"])[0]) if isinstance(r.get("outcomePrices"), list) else None
            except Exception:
                yes_price = None
            matches.append({
                "question":  r.get("question", ""),
                "yes_price": yes_price,
                "volume_24h": float(r.get("volume24hr", 0) or 0),
                "end_date":  r.get("endDate", "")[:10] if r.get("endDate") else "",
                "slug":      r.get("slug", ""),
                "url":       f"https://polymarket.com/event/{r.get('slug', '')}" if r.get("slug") else "",
            })
            seen.add(q)

    # Sort by volume desc
    return sorted(matches, key=lambda x: x["volume_24h"], reverse=True)[:6]


def build_watchlist_section(watchlist: list, markets: list, raw_markets: list,
                             current_prices: dict) -> str:
    """
    Build the manual watchlist section: one card per ticker showing
    current price, 1d delta, and matched Polymarket markets.
    """
    if not watchlist:
        return ""

    cards_html = ""
    for entry in watchlist:
        ticker  = entry.get("ticker", "")
        name    = entry.get("name", ticker)
        notes   = entry.get("notes", "")
        kws     = ", ".join(entry.get("keywords", [])[:5])

        # Price info
        price_info = current_prices.get(ticker, {})
        price      = price_info.get("price")
        delta_1d   = price_info.get("delta_1d")

        if price is not None:
            price_html = f'<span style="font-size:1.4rem;font-weight:700;color:#2c3e50">${price:,.2f}</span>'
        else:
            price_html = '<span style="font-size:.8rem;color:#bdc3c7">precio no disponible</span>'

        if delta_1d is not None:
            d_color = "#27ae60" if delta_1d >= 0 else "#e74c3c"
            d_sign  = "+" if delta_1d >= 0 else ""
            delta_html = (f'<span style="font-size:.85rem;font-weight:600;color:{d_color};margin-left:8px">'
                          f'{d_sign}{delta_1d:.2f} hoy</span>')
        else:
            delta_html = ""

        # Matched PM markets
        pm_matches = match_watchlist_to_markets(entry, markets, raw_markets)

        if pm_matches:
            rows = ""
            for pm in pm_matches:
                yp = pm["yes_price"]
                yp_str   = f"{yp:.0%}" if yp is not None else "—"
                yp_color = "#27ae60" if (yp or 0) > 0.6 else ("#e74c3c" if (yp or 1) < 0.4 else "#e67e22")
                vol_str  = f"${pm['volume_24h']/1e3:.0f}K" if pm['volume_24h'] < 1e6 else f"${pm['volume_24h']/1e6:.1f}M"
                end_str  = pm["end_date"][:10] if pm["end_date"] else "—"
                link     = (f'<a href="{pm["url"]}" target="_blank" '
                            f'style="color:#2980b9;text-decoration:none;font-size:.77rem">'
                            f'{pm["question"][:75]}</a>'
                            if pm["url"] else
                            f'<span style="font-size:.77rem">{pm["question"][:75]}</span>')
                rows += f"""
                <tr style="border-bottom:1px solid #f5f5f5">
                  <td style="padding:6px 8px">{link}</td>
                  <td style="padding:6px 8px;text-align:center;font-weight:700;color:{yp_color}">{yp_str}</td>
                  <td style="padding:6px 8px;text-align:right;font-size:.75rem;color:#7f8c8d">{vol_str}</td>
                  <td style="padding:6px 8px;text-align:right;font-size:.75rem;color:#7f8c8d">{end_str}</td>
                </tr>"""

            pm_table = f"""
            <table style="width:100%;border-collapse:collapse;margin-top:10px">
              <thead>
                <tr style="background:#f7f9fc;border-bottom:2px solid #e8e8e8">
                  <th style="padding:6px 8px;font-size:.74rem;color:#7f8c8d;text-align:left">Mercado Polymarket</th>
                  <th style="padding:6px 8px;font-size:.74rem;color:#7f8c8d;text-align:center">YES %</th>
                  <th style="padding:6px 8px;font-size:.74rem;color:#7f8c8d;text-align:right">Vol 24h</th>
                  <th style="padding:6px 8px;font-size:.74rem;color:#7f8c8d;text-align:right">Cierre</th>
                </tr>
              </thead>
              <tbody>{rows}</tbody>
            </table>"""
        else:
            pm_table = '<p style="color:#bdc3c7;font-size:.8rem;margin-top:8px">Sin mercados Polymarket relacionados hoy.</p>'

        ticker_esc = ticker.replace('"', '&quot;')
        cards_html += f"""
        <div style="background:#fff;border:1px solid #e8e8e8;border-radius:10px;
                    padding:16px 20px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,0.06)">
          <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
            <div>
              <strong style="font-size:1.1rem;color:#2c3e50">{ticker}</strong>
              <span style="font-size:.85rem;color:#7f8c8d;margin-left:8px">{name}</span>
              <button onclick="removeWatchlistTicker('{ticker_esc}')"
                style="margin-left:12px;background:none;border:1px solid #e74c3c;color:#e74c3c;
                       border-radius:6px;padding:2px 8px;font-size:.72rem;cursor:pointer">✕ Quitar</button>
            </div>
            <div style="display:flex;align-items:center;gap:10px">
              {price_html}{delta_html}
              <button class="buy-btn" onclick="openBuyModal(this)"
                data-ticker="{ticker_esc}" data-name="{name}" data-action="BUY"
                data-source="Watchlist manual" data-yes-price="0"
                style="background:#27ae60;color:#fff;border:none;border-radius:6px;
                       padding:6px 14px;cursor:pointer;font-size:.82rem;font-weight:600">
                🛒 Registrar compra
              </button>
            </div>
          </div>
          {f'<div style="font-size:.75rem;color:#95a5a6;margin-top:4px">📎 {notes}</div>' if notes else ''}
          <div style="font-size:.72rem;color:#bdc3c7;margin-top:2px">Keywords: {kws}</div>
          {pm_table}
        </div>"""

    # Add-ticker form
    add_form = """
    <div style="background:#f7f9fc;border:1px dashed #bdc3c7;border-radius:10px;
                padding:14px 18px;margin-top:4px" id="watchlist-add-form">
      <strong style="font-size:.85rem;color:#2c3e50">➕ Agregar ticker</strong>
      <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;align-items:flex-end">
        <div>
          <label style="font-size:.74rem;color:#7f8c8d;display:block;margin-bottom:3px">Ticker</label>
          <input id="wl-ticker" type="text" placeholder="ej. NVDA" maxlength="10"
            style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:.85rem;width:90px;text-transform:uppercase">
        </div>
        <div>
          <label style="font-size:.74rem;color:#7f8c8d;display:block;margin-bottom:3px">Nombre</label>
          <input id="wl-name" type="text" placeholder="ej. NVIDIA Corp"
            style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:.85rem;width:160px">
        </div>
        <div>
          <label style="font-size:.74rem;color:#7f8c8d;display:block;margin-bottom:3px">Keywords (separadas por coma)</label>
          <input id="wl-keywords" type="text" placeholder="ej. ai, chips, semiconductor"
            style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:.85rem;width:220px">
        </div>
        <div>
          <label style="font-size:.74rem;color:#7f8c8d;display:block;margin-bottom:3px">Notas</label>
          <input id="wl-notes" type="text" placeholder="opcional"
            style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:.85rem;width:160px">
        </div>
        <button onclick="addWatchlistTicker()"
          style="background:#2980b9;color:#fff;border:none;border-radius:6px;
                 padding:8px 16px;font-size:.85rem;cursor:pointer;font-weight:600">Agregar</button>
      </div>
      <div id="wl-msg" style="font-size:.75rem;margin-top:6px;color:#27ae60"></div>
      <div style="font-size:.72rem;color:#aaa;margin-top:6px">
        💡 Los tickers agregados aquí se guardan en <code>data/watchlist.json</code> y aparecen en el próximo run.
      </div>
    </div>"""

    return f"""
<div class="section">
  <div class="section-header">👁 Mi Watchlist — Correlación con Polymarket</div>
  <div class="section-body">
    {cards_html}
    {add_form}
  </div>
</div>"""


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
const _PF_KEY  = 'pmadv_portfolio_v1';
const _PF_API  = 'http://localhost:7741';
let _buySignal = null;

function _getPF() {
  // Prefer server-embedded data (freshest); fall back to localStorage
  const base = (window.SAVED_PORTFOLIO && window.SAVED_PORTFOLIO.length > 0)
    ? window.SAVED_PORTFOLIO
    : [];
  try {
    const local = JSON.parse(localStorage.getItem(_PF_KEY) || '[]');
    // Merge: local entries not already in base (by id)
    const baseIds = new Set(base.map(t => String(t.id)));
    const extra   = local.filter(t => !baseIds.has(String(t.id)));
    return [...base, ...extra];
  } catch(e) { return base; }
}

function _savePF(trades) {
  // Always keep localStorage in sync for instant UI
  localStorage.setItem(_PF_KEY, JSON.stringify(trades));
}

function openBuyModal(btn) {
  const tr = btn.closest('tr');
  const d = tr ? tr.dataset : btn.dataset;
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

async function confirmBuy() {
  const amt = parseFloat(document.getElementById('pm-modal-amount').value);
  const inp = document.getElementById('pm-modal-amount');
  if (!amt || amt <= 0) { inp.style.borderColor = '#e74c3c'; inp.focus(); return; }
  if (!_buySignal) return;

  const trade = {
    id:            Date.now().toString(),
    ticker:        _buySignal.ticker,
    instrument_name: _buySignal.name,
    usd_amount:    amt,
    price_at_buy:  _buySignal.currentPrice,
    date_bought:   new Date().toISOString(),
    signal_source: _buySignal.source,
    action:        _buySignal.action
  };

  // Save to localStorage immediately for instant UI
  const pf = _getPF();
  pf.push(trade);
  _savePF(pf);
  closeBuyModal();
  renderPortfolio();

  // Persist to disk via API (background — non-blocking)
  try {
    await fetch(_PF_API + '/portfolio/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(trade)
    });
    // Regenerate portfolio dashboard so the tab shows the new position
    await fetch(_PF_API + '/portfolio/rebuild', { method: 'POST' }).catch(() => {});
  } catch(e) {
    console.warn('Portfolio API not available — saved to localStorage only. Run: python scripts/watchlist_api.py');
  }
}

async function removePosition(id) {
  if (!confirm('Eliminar esta posicion del portfolio?')) return;
  _savePF(_getPF().filter(p => p.id !== id));
  renderPortfolio();

  // Remove from disk
  try {
    await fetch(_PF_API + '/portfolio/remove', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ id: String(id) })
    });
  } catch(e) {
    console.warn('Portfolio API not available.');
  }
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
    """Build the My Trades performance HTML section with portfolio share."""
    if not trades:
        return ""

    # Pre-calculate total portfolio value
    trade_data = []
    total_portfolio_value = 0.0

    for t in trades:
        ticker = t["ticker"]
        current = fetch_current_price(ticker) if ticker != "CASH" else 1.0
        quantity = t.get("quantity", 0.0)
        current_value = (current * quantity) if (current is not None and quantity > 0) else 0.0
        total_portfolio_value += current_value
        trade_data.append((t, current, current_value))

    rows = []
    for t, current, current_value in trade_data:
        ticker    = t["ticker"]
        buy_price = t["price_buy"]
        buy_date  = t["date"][:10]
        days_held = (datetime.now() - datetime.fromisoformat(t["date"])).days
        quantity  = t.get("quantity", 0.0)

        if current is None:
            pnl_html  = "<td>—</td><td>—</td>"
            curr_html = "<td>N/A</td>"
            share_html = "<td>—</td>"
            val_html  = "<td>—</td>"
        else:
            pnl_d = current - buy_price
            pnl_p = pnl_d / buy_price * 100
            sign  = "+" if pnl_d >= 0 else ""
            color = "#27ae60" if pnl_d >= 0 else "#e74c3c"
            
            # For CASH, no P&L
            if ticker == "CASH":
                pnl_html = "<td>—</td><td>—</td>"
                curr_html = "<td>$1.00</td>"
            else:
                pnl_html  = (f'<td style="color:{color};font-weight:700">'
                             f'{sign}{pnl_d:.2f}</td>'
                             f'<td style="color:{color};font-weight:700">'
                             f'{sign}{pnl_p:.1f}%</td>')
                curr_html = f"<td>${current:.2f}</td>"
            
            val_html = f"<td>${current_value:,.2f}</td>"
            
            if total_portfolio_value > 0 and current_value > 0:
                share_pct = (current_value / total_portfolio_value) * 100
                share_html = f"<td><strong>{share_pct:.1f}%</strong></td>"
            else:
                share_html = "<td>—</td>"

        source = t.get("source", "")[:45]
        qty_str = f"{quantity:,.4f}" if quantity > 0 else "—"

        rows.append(f"""<tr>
          <td><strong>{ticker}</strong></td>
          <td>{t['action']}</td>
          <td>{qty_str}</td>
          <td>${buy_price:.2f}</td>
          {curr_html}
          {val_html}
          {pnl_html}
          {share_html}
          <td style="font-size:.75rem;color:#7f8c8d">{source}</td>
        </tr>""")

    record_cmd = "python scripts/record_trade.py BUY TICKER PRICE --source &quot;Signal description&quot;"
    return f"""
<div class="section">
  <div class="section-header">📒 My Trades — Performance Tracker (Portfolio Total Value: ${total_portfolio_value:,.2f})</div>
  <div class="section-body">
    <table>
      <thead><tr>
        <th>Ticker</th><th>Action</th><th>Shares</th><th>Buy $</th><th>Now $</th>
        <th>Total Value</th><th>P&amp;L $</th><th>P&amp;L %</th><th>Share %</th><th>Signal Source</th>
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
from src.paper_trading import MomentumFilter, PaperTradeLogger, PaperTradeResolver, PerformanceTracker
from src.predictor.decorrelator import decorrelate_signals
from src.predictor.calibration_log import log_signal as cal_log_signal, update_forward_returns, get_calibration_stats

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


def build_top10_pm_correlations(inv_signals):
    """
    Returns an HTML string with the top-10 investment alternatives that have
    a direct Polymarket correlation, ranked by confidence × log(volume).
    Returns an empty string if nothing qualifies.
    """
    import math

    ACTION_STYLE = {
        "BUY":   ("background:#1a9c4a;color:#fff",   "BUY"),
        "SELL":  ("background:#e74c3c;color:#fff",   "SELL"),
        "WATCH": ("background:#e67e22;color:#fff",   "WATCH"),
        "HOLD":  ("background:#95a5a6;color:#fff",   "HOLD"),
    }

    # Only include signals with a real PM market linked (yes_price > 0, source_market set)
    qualified = [
        s for s in inv_signals
        if s.source_market and s.yes_price > 0
    ]
    if not qualified:
        return ""

    # Rank: confidence × log1p(volume_24h)
    ranked = sorted(
        qualified,
        key=lambda s: s.confidence * math.log1p(s.volume_24h),
        reverse=True
    )[:10]

    rows_html = ""
    for i, s in enumerate(ranked, 1):
        style, label = ACTION_STYLE.get(s.action, ("background:#bdc3c7;color:#333", s.action))
        badge = f'<span style="{style};padding:2px 10px;border-radius:11px;font-size:.74rem;font-weight:700">{label}</span>'
        conf_bar_w = int(s.confidence * 90)
        conf_html = (
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:{conf_bar_w}px;height:8px;background:#2980b9;border-radius:4px"></div>'
            f'<span style="font-size:.78rem;color:#555">{s.confidence:.0%}</span>'
            f'</div>'
        )
        yes_color = "#1a9c4a" if s.yes_price > 0.6 else ("#e74c3c" if s.yes_price < 0.4 else "#e67e22")
        rows_html += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
          <td style="padding:8px 6px;font-size:.8rem;color:#7f8c8d;text-align:center">{i}</td>
          <td style="padding:8px 6px"><strong style="font-size:.9rem">{s.ticker}</strong><br>
            <span style="font-size:.74rem;color:#7f8c8d">{s.instrument_name[:40]}</span></td>
          <td style="padding:8px 6px;text-align:center">{badge}</td>
          <td style="padding:8px 6px">{conf_html}</td>
          <td style="padding:8px 6px;font-size:.78rem;color:{yes_color};font-weight:700;text-align:center">{s.yes_price:.0%}</td>
          <td style="padding:8px 6px;font-size:.75rem;max-width:320px">{
              f'<a href="{s.market_url}" target="_blank" style="color:#2980b9;text-decoration:none">{s.source_market[:80]}</a>'
              if getattr(s, "market_url", "") else s.source_market[:80]
          }</td>
          <td style="padding:8px 6px;font-size:.74rem;color:#7f8c8d;text-align:right">${s.volume_24h:,.0f}</td>
        </tr>"""

    return f"""
<table style="width:100%;border-collapse:collapse;font-family:sans-serif">
  <thead>
    <tr style="background:#f7f9fc;border-bottom:2px solid #e0e0e0">
      <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:center">#</th>
      <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:left">Instrumento</th>
      <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:center">Acción</th>
      <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:left">Confianza</th>
      <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:center">YES %</th>
      <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:left">Mercado Polymarket</th>
      <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:right">Vol 24h</th>
    </tr>
  </thead>
  <tbody>{rows_html}
  </tbody>
</table>"""


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

  /* Tab Nav */
  .tab-nav {{ display: flex; background: #0d1117; padding: 0 32px; gap: 0;
              position: sticky; top: 0; z-index: 999;
              border-bottom: 2px solid #30363d; }}
  .tab-nav a {{ color: #8b949e; text-decoration: none; padding: 12px 22px;
                font-size: .82rem; font-weight: 600; letter-spacing: .3px;
                border-bottom: 3px solid transparent; margin-bottom: -2px;
                transition: color .15s; display: flex; align-items: center; gap: 6px; }}
  .tab-nav a:hover {{ color: #e6edf3; }}
  .tab-nav a.active {{ color: #58a6ff; border-bottom-color: #58a6ff; }}

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

<nav class="tab-nav">
  <a href="#" class="active">📈 Signals Dashboard</a>
  <a href="./portfolio_dashboard_latest.html">💼 Portfolio Monitor</a>
</nav>

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
    <div style="margin-top:4px">{delta_sell}</div>
  </div>
  <div class="kpi buy">
    <div class="label">BUY</div>
    <div class="value">{n_buy}</div>
    <div class="sub">señales de compra</div>
    <div style="margin-top:4px">{delta_buy}</div>
  </div>
  <div class="kpi watch">
    <div class="label">WATCH</div>
    <div class="value">{n_watch}</div>
    <div class="sub">monitorear</div>
    <div style="margin-top:4px">{delta_watch}</div>
  </div>
  <div class="kpi total">
    <div class="label">Top vol 24h</div>
    <div class="value">{top_vol}</div>
    <div class="sub">{top_market}</div>
  </div>
</div>

<!-- Scorecard -->
{scorecard_html}

<!-- Seth Goldman Copy Button -->
{seth_copy_html}

<!-- Decorrelation Report -->
{decorrelation_html}

<!-- Calibration Curve -->
{calibration_html}

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
          <th>Actualizado</th>
          <th>YES %</th>
          <th>Vol 24h (fuente)</th>
          <th>Mercado Polymarket</th>
          <th>Impacto Portfolio</th>
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

<!-- Email Parsing Quality -->
{finsignal_quality_html}

<!-- Non-Obvious Signals -->
{risky_section_html}

<!-- My Trades -->
{trades_section_html}

<!-- Paper Trading -->
{paper_trading_html}

<!-- Watchlist -->
{watchlist_section_html}

<!-- Portfolio Recommendations -->
{portfolio_recs_html}

<div class="footer">
  Polymarket Investment Adviser · {date} · Datos: Polymarket Gamma API + CLOB API
</div>
{buy_modal_html}
{dashboard_data_script}
{portfolio_js}
<script>
// ── Watchlist JS — writes directly to data/watchlist.json via local API ──────
const WL_API = 'http://localhost:7741';

async function addWatchlistTicker() {{
  const ticker   = document.getElementById('wl-ticker').value.trim().toUpperCase();
  const name     = document.getElementById('wl-name').value.trim();
  const keywords = document.getElementById('wl-keywords').value.split(',').map(k => k.trim()).filter(Boolean);
  const notes    = document.getElementById('wl-notes').value.trim();
  const msg      = document.getElementById('wl-msg');

  if (!ticker) {{ msg.style.color='#e74c3c'; msg.textContent='Ingresa un ticker.'; return; }}
  msg.textContent = '⏳ Guardando…';

  try {{
    const res = await fetch(`${{WL_API}}/add`, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ ticker, name: name||ticker, keywords, notes }})
    }});
    const data = await res.json();
    if (data.ok) {{
      msg.style.color='#27ae60';
      msg.textContent=`✓ ${{ticker}} guardado en watchlist.json. Vuelve a correr el dashboard para verlo.`;
      document.getElementById('wl-ticker').value='';
      document.getElementById('wl-name').value='';
      document.getElementById('wl-keywords').value='';
      document.getElementById('wl-notes').value='';
    }} else {{
      msg.style.color='#e67e22';
      msg.textContent = data.error || 'Error al guardar.';
    }}
  }} catch(e) {{
    msg.style.color='#e74c3c';
    msg.textContent='⚠️ API local no disponible. Corre: python scripts/watchlist_api.py';
  }}
}}

async function removeWatchlistTicker(ticker) {{
  if (!confirm(`¿Quitar ${{ticker}} del watchlist?`)) return;
  try {{
    const res = await fetch(`${{WL_API}}/remove`, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ ticker }})
    }});
    const data = await res.json();
    if (data.ok) {{
      alert(`✓ ${{ticker}} eliminado. Vuelve a correr el dashboard.`);
    }} else {{
      alert(data.error || 'Error al eliminar.');
    }}
  }} catch(e) {{
    alert('⚠️ API local no disponible. Corre: python scripts/watchlist_api.py');
  }}
}}
</script>
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


def build_portfolio_recommendations_section(inv_signals, owned_tickers: set) -> str:
    """Build the Portfolio-Based Signal Recommendations HTML section."""
    
    recs = [s for s in inv_signals if s.ticker in owned_tickers]

    if not recs:
        return f"""
<div class="section" style="border-left: 4px solid #8e44ad;">
  <div class="section-header">💼 Portfolio-Based Recommendations
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      Active Polymarket signals targeting your current holdings
    </span>
  </div>
  <div class="section-body">
    <p style="color:#7f8c8d;font-size:0.85rem;">No active Polymarket signals targeting your current portfolio holdings today.</p>
  </div>
</div>"""

    rows = []
    for r in recs:
        action = r.action
        if action == "BUY":
            badge = '<span class="badge badge-BUY">BUY</span>'
            rationale_fit = f"Portfolio Hedge / Increases Exposure to {r.ticker}"
        elif action == "SELL":
            badge = '<span class="badge badge-SELL">SELL</span>'
            rationale_fit = f"Portfolio Hedge / Trims Exposure from {r.ticker}"
        else:
            badge = f'<span class="badge badge-{action}">{action}</span>'
            rationale_fit = f"Affects your {r.ticker} holding."
            
        conf_pct = int(r.confidence * 100)
        
        rows.append(f"""<tr>
          <td><strong>{r.ticker}</strong></td>
          <td>{r.instrument_name}</td>
          <td>{badge}</td>
          <td>{conf_pct}%</td>
          <td style="font-size:.78rem;color:#2c3e50">{rationale_fit} | {r.rationale}</td>
        </tr>""")

    return f"""
<div class="section" style="border-left: 4px solid #8e44ad;">
  <div class="section-header">💼 Portfolio-Based Recommendations
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      Active Polymarket signals targeting your current holdings
    </span>
  </div>
  <div class="section-body">
    <table>
      <thead><tr>
        <th>Ticker</th><th>Name</th><th>Action</th><th>Conf</th>
        <th>Rationale (Portfolio Fit)</th>
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


def build_signal_rows(inv_signals, priority_topics: list = None, owned_tickers: set = None, prev_signal_keys: set = None):
    if priority_topics is None:
        priority_topics = []
    if owned_tickers is None:
        owned_tickers = set()
    if prev_signal_keys is None:
        prev_signal_keys = set()

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
        btn_style  = ("background:#27ae60" if s.action == "BUY" else
                      "background:#e74c3c" if s.action == "SELL" else
                      "background:#7f8c8d")
        btn_label  = "🛒 Buy" if s.action != "SELL" else "📤 Sell"
        buy_btn    = (f'<td><button class="buy-btn" onclick="openBuyModal(this)" '
                      f'style="{btn_style};color:#fff;border:none;border-radius:6px;'
                      f'padding:4px 10px;cursor:pointer;font-size:.78rem">'
                      f'{btn_label}</button></td>')

        # Age badge — new vs recurring
        is_recurring = (s.ticker, s.action) in prev_signal_keys
        if is_recurring:
            age_badge = ('<span style="background:#f39c12;color:#fff;padding:1px 7px;'
                         'border-radius:10px;font-size:.68rem;font-weight:700;margin-left:4px">'
                         '↩ Recurrente</span>')
        else:
            age_badge = ('<span style="background:#27ae60;color:#fff;padding:1px 7px;'
                         'border-radius:10px;font-size:.68rem;font-weight:700;margin-left:4px">'
                         '🆕 Nuevo</span>')

        # Confirmation score badge
        conf_score = getattr(s, "confirmation_score", None)
        mom_flag   = getattr(s, "momentum_flag", None)
        conf_badge = ""
        if conf_score is not None:
            cs_color = "#1a9c4a" if conf_score >= 3 else ("#e67e22" if conf_score == 2 else "#95a5a6")
            conf_badge = (f'<span style="background:{cs_color};color:#fff;padding:1px 7px;'
                          f'border-radius:10px;font-size:.68rem;font-weight:700;margin-left:4px">'
                          f'{conf_score}/4 ✓</span>')
        if mom_flag == "late":
            conf_badge += ('<span style="background:#e74c3c;color:#fff;padding:1px 6px;'
                           'border-radius:10px;font-size:.66rem;font-weight:700;margin-left:3px">'
                           '⚠ Tarde</span>')
        elif mom_flag == "contrarian":
            conf_badge += ('<span style="background:#8e44ad;color:#fff;padding:1px 6px;'
                           'border-radius:10px;font-size:.66rem;font-weight:700;margin-left:3px">'
                           '↩ Contrarian</span>')

        # Clickable PM link for source market
        market_url = getattr(s, "market_url", "")
        if market_url:
            source_cell = (f'<a href="{market_url}" target="_blank" '
                           f'style="color:#2980b9;font-size:.78rem;text-decoration:none" '
                           f'title="{source_esc}">{s.source_market[:70]}</a>')
        else:
            source_cell = s.source_market[:70]

        date_label = getattr(s, "signal_date_label", "") or "—"

        is_owned = s.ticker in owned_tickers
        impact_html = "<td><span style='color:#7f8c8d;font-size:0.8rem;'>⚪ New Position</span></td>"
        if is_owned:
            if s.action == "BUY":
                impact_html = "<td><strong style='color:#27ae60;font-size:0.8rem;'>🟢 Adds Exposure</strong></td>"
            elif s.action == "SELL":
                impact_html = "<td><strong style='color:#e74c3c;font-size:0.8rem;'>🔴 Hedges Risk</strong></td>"
            else:
                impact_html = "<td><strong style='color:#f39c12;font-size:0.8rem;'>🟡 Monitor Holding</strong></td>"

        rows.append(f"""
        <tr{row_cls} data-ticker="{s.ticker}" data-name="{name_esc}" data-yes-price="{s.yes_price:.6f}" data-source="{source_esc}" data-action="{s.action}">
          <td><span class="badge badge-{s.action}">{s.action}</span></td>
          <td><strong>{s.ticker}</strong>{prio_badge}{age_badge}{conf_badge}</td>
          <td>{s.instrument_name}</td>
          <td>
            <span class="conf-bar {bar_cls}" style="width:{bar_w}px"></span>
            {conf_pct}%
          </td>
          <td><span class="{timing_cls}">{s.timing_action}</span></td>
          <td><span style="font-size:.78rem;color:#7f8c8d;white-space:nowrap">{date_label}</span></td>
          <td>{s.yes_price:.0%}</td>
          <td>${s.volume_24h:,.0f}</td>
          <td class="source">{source_cell}</td>
          {impact_html}
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


# ── 6. Email Parsing Quality Score ───────────────────────────────────────────
def build_finsignal_quality_section(finsignal_data: dict) -> str:
    """
    Show a quality card for signals parsed from roresendiz@gmail.com.
    Displays: ticker, direction, confidence, and the context snippet that triggered it.
    Only renders if there are signals with a known personal-account source.
    """
    signals = finsignal_data.get("signals", [])
    if not signals:
        return ""

    DIR_STYLE = {
        "BUY":     ("background:#1a9c4a;color:#fff",   "BUY"),
        "SELL":    ("background:#e74c3c;color:#fff",   "SELL"),
        "HOLD":    ("background:#95a5a6;color:#fff",   "HOLD"),
        "MENTION": ("background:#2980b9;color:#fff",   "MENTION"),
    }

    rows_html = ""
    for s in signals:
        ticker     = s.get("ticker", "—")
        direction  = s.get("direction", "MENTION")
        confidence = float(s.get("confidence", 0))
        context    = s.get("context", "")[:120]
        source     = s.get("source", "")
        pm_matches = s.get("polymarket_matches", [])

        style, label = DIR_STYLE.get(direction, ("background:#bdc3c7;color:#333", direction))
        badge = f'<span style="{style};padding:2px 9px;border-radius:11px;font-size:.73rem;font-weight:700">{label}</span>'
        conf_bar_w = int(confidence * 80)
        pm_count   = len(pm_matches)
        pm_badge   = (f'<span style="background:#8e44ad;color:#fff;padding:1px 7px;'
                      f'border-radius:10px;font-size:.68rem;font-weight:700">'
                      f'{pm_count} PM match{"es" if pm_count != 1 else ""}</span>'
                      if pm_count > 0 else
                      '<span style="color:#bdc3c7;font-size:.72rem">Sin match PM</span>')

        rows_html += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
          <td style="padding:8px 6px"><strong style="font-size:.9rem">{ticker}</strong></td>
          <td style="padding:8px 6px;text-align:center">{badge}</td>
          <td style="padding:8px 6px">
            <div style="display:flex;align-items:center;gap:5px">
              <div style="width:{conf_bar_w}px;height:7px;background:#2980b9;border-radius:4px"></div>
              <span style="font-size:.77rem;color:#555">{confidence:.0%}</span>
            </div>
          </td>
          <td style="padding:8px 6px;font-size:.75rem;color:#555;font-style:italic">"{context}"</td>
          <td style="padding:8px 6px;text-align:center">{pm_badge}</td>
          <td style="padding:8px 6px;font-size:.72rem;color:#7f8c8d">{source[:50]}</td>
        </tr>"""

    collected_at = finsignal_data.get("collected_at", "")[:16].replace("T", " ")
    mode_badge   = ('<span style="background:#e67e22;color:#fff;padding:1px 8px;'
                    'border-radius:10px;font-size:.7rem;font-weight:700">DEMO</span>'
                    if finsignal_data.get("mode") == "demo" else "")

    return f"""
<div class="section">
  <div class="section-header">📧 Email Parsing Quality
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      {len(signals)} señal{"es" if len(signals) != 1 else ""} extraída{"s" if len(signals) != 1 else ""} · {collected_at} {mode_badge}
    </span>
  </div>
  <div class="section-body">
    <table style="width:100%;border-collapse:collapse;font-family:sans-serif">
      <thead>
        <tr style="background:#f7f9fc;border-bottom:2px solid #e0e0e0">
          <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:left">Ticker</th>
          <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:center">Dirección</th>
          <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:left">Confianza</th>
          <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:left">Contexto que lo activó</th>
          <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:center">Polymarket</th>
          <th style="padding:9px 6px;font-size:.78rem;color:#7f8c8d;text-align:left">Fuente</th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>
  </div>
</div>"""


# ── 7. Yesterday's Snapshot Helpers ──────────────────────────────────────────
def load_yesterday_snapshot() -> dict:
    """Load the most recent previous snapshot (any day before today)."""
    snapshots_dir = config.data_dir / "snapshots"
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not snapshots_dir.exists():
        return {}
    # Gather all snapshot dirs sorted descending, skip today
    dirs = sorted(
        [d for d in snapshots_dir.iterdir() if d.is_dir() and d.name != today_str],
        reverse=True
    )
    for d in dirs:
        snap_file = d / f"snapshot_{d.name}.json"
        if snap_file.exists():
            try:
                return json.loads(snap_file.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def get_yesterday_signal_keys(yesterday: dict) -> set:
    """Return a set of (ticker, action) tuples from yesterday's snapshot."""
    return {
        (s["ticker"], s["action"])
        for s in yesterday.get("investment_signals", [])
        if "ticker" in s and "action" in s
    }


def kpi_delta_html(today_val: int, yesterday: dict, key: str) -> str:
    """Return a small colored delta span vs yesterday's snapshot summary."""
    prev = yesterday.get("summary", {}).get(key)
    if prev is None:
        return '<span style="font-size:.7rem;color:#bdc3c7">—</span>'
    delta = today_val - prev
    if delta > 0:
        color, sign = "#27ae60", "+"
    elif delta < 0:
        color, sign = "#e74c3c", ""
    else:
        color, sign = "#95a5a6", "±"
    return (f'<span style="font-size:.82rem;font-weight:700;color:{color}">'
            f'{sign}{delta} vs ayer</span>')


# ── 7. Main ───────────────────────────────────────────────────────────────────
def enrich_signals_with_momentum(inv_signals: list, finsignal_data: dict) -> list:
    """
    Post-process inv_signals to add:
    1. momentum_10d / momentum_flag  (price movement filter)
    2. confirmation_score            (multi-source confirmation: 0-4)
    3. confirmation_sources          (which sources fired)

    Returns the same list, mutated in place with extra attributes.
    """
    # ── Momentum batch fetch ─────────────────────────────────────────────────
    tickers = list({s.ticker for s in inv_signals})
    mf = MomentumFilter()
    try:
        mom = mf.get_momentum_batch(tickers, days=10)
    except Exception:
        mom = {}

    # ── Newsletter ticker → date map ─────────────────────────────────────────
    from email.utils import parsedate
    import time as _time

    newsletter_tickers = {}   # ticker → most recent parsed date string "Apr 14"
    for sig in finsignal_data.get("signals", []):
        ticker = sig.get("ticker", "").upper()
        raw_date = sig.get("date", "")
        if not ticker:
            continue
        # Parse RFC 2822 email date → "Apr 14" label
        label = ""
        try:
            t = parsedate(raw_date)
            if t:
                label = _time.strftime("%b %d", t)
        except Exception:
            pass
        # Keep the most recent date per ticker (later = higher index)
        if ticker not in newsletter_tickers or label:
            newsletter_tickers[ticker] = label

    enriched = []
    for s in inv_signals:
        m = mom.get(s.ticker, {})
        pct    = m.get("pct_change", 0.0) or 0.0
        flag   = mf.classify_for_signal(s.action, pct)

        sources = []

        # Source 1 — PM probability strong (extreme = >65% or <35%)
        if s.yes_price >= 0.65 or s.yes_price <= 0.35:
            sources.append("pm_probability")

        # Source 2 — Newsletter mention
        if s.ticker.upper() in newsletter_tickers:
            sources.append("newsletter")

        # Source 3 — PM volume spike (>$500K/day = significant)
        if s.volume_24h >= 500_000:
            sources.append("volume_spike")

        # Source 4 — Price momentum not "late" (instrument hasn't already run)
        if flag not in ("late",):
            sources.append("momentum_aligned")

        # Signal date: use newsletter date if available, else pipeline run date
        newsletter_date = newsletter_tickers.get(s.ticker.upper(), "")
        if not newsletter_date:
            try:
                newsletter_date = datetime.fromisoformat(s.generated_at).strftime("%b %d")
            except Exception:
                newsletter_date = ""

        # Attach as extra attributes (avoids changing dataclass)
        s.__dict__["momentum_10d"]          = round(pct, 2)
        s.__dict__["momentum_flag"]          = flag
        s.__dict__["confirmation_score"]     = len(sources)
        s.__dict__["confirmation_sources"]   = sources
        s.__dict__["signal_date_label"]      = newsletter_date

        enriched.append(s)

    return enriched


def build_paper_trading_section(open_trades: list, closed_trades: list, current_prices: dict = None) -> str:
    """Dashboard section showing paper trading performance + open positions."""
    if current_prices is None:
        current_prices = {}
    tracker = PerformanceTracker(open_trades, closed_trades)
    summary = tracker.summary()
    by_ticker = tracker.by_ticker()
    streak    = tracker.streak()

    # ── P&L over open positions ───────────────────────────────────────────────
    total_invested = sum(getattr(t, 'usd_amount', 0) or 0 for t in open_trades)
    total_current  = 0.0
    for t in open_trades:
        amt = getattr(t, 'usd_amount', 0) or 0
        if amt > 0 and t.entry_price > 0:
            cur = (current_prices.get(t.ticker) or {}).get("price")
            if cur:
                total_current += amt * (cur / t.entry_price)
            else:
                total_current += amt
        else:
            total_current += amt
    total_pnl     = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
    pnl_color     = "#27ae60" if total_pnl >= 0 else "#e74c3c"
    pnl_sign      = "+" if total_pnl >= 0 else ""

    # ── Summary bar ──────────────────────────────────────────────────────────
    win_rate   = summary.get("win_rate", 0)
    wr_color   = "#27ae60" if win_rate >= 0.55 else ("#e74c3c" if win_rate < 0.45 else "#e67e22")
    avg_ret    = summary.get("avg_return_pct", 0)
    ret_color  = "#27ae60" if avg_ret >= 0 else "#e74c3c"
    ret_sign   = "+" if avg_ret >= 0 else ""
    streak_val = streak.get("current_streak", 0)
    streak_dir = "victorias" if streak_val > 0 else "pérdidas"
    streak_col = "#27ae60" if streak_val > 0 else ("#e74c3c" if streak_val < 0 else "#95a5a6")

    invested_kpi = f"""
      <div style="background:#f7f9fc;border-radius:8px;padding:12px 18px;flex:1;min-width:120px;text-align:center">
        <div style="font-size:.75rem;color:#7f8c8d">Capital simulado</div>
        <div style="font-size:1.6rem;font-weight:700;color:#2c3e50">${total_invested:,.0f}</div>
        <div style="font-size:.72rem;color:#95a5a6">USD en papel</div>
      </div>
      <div style="background:#f7f9fc;border-radius:8px;padding:12px 18px;flex:1;min-width:120px;text-align:center;border-left:4px solid {pnl_color}">
        <div style="font-size:.75rem;color:#7f8c8d">P&L al día de hoy</div>
        <div style="font-size:1.6rem;font-weight:700;color:{pnl_color}">{pnl_sign}${total_pnl:,.0f}</div>
        <div style="font-size:.72rem;color:{pnl_color};font-weight:600">{pnl_sign}{total_pnl_pct:.1f}%</div>
      </div>""" if total_invested > 0 else ""

    kpis_html = f"""
    <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:16px">
      {invested_kpi}
      <div style="background:#f7f9fc;border-radius:8px;padding:12px 18px;flex:1;min-width:120px;text-align:center">
        <div style="font-size:.75rem;color:#7f8c8d">Trades totales</div>
        <div style="font-size:1.6rem;font-weight:700;color:#2c3e50">{summary['total_trades']}</div>
        <div style="font-size:.72rem;color:#95a5a6">{summary['open_count']} abiertos · {summary['closed_count']} cerrados</div>
      </div>
      <div style="background:#f7f9fc;border-radius:8px;padding:12px 18px;flex:1;min-width:120px;text-align:center">
        <div style="font-size:.75rem;color:#7f8c8d">Win Rate</div>
        <div style="font-size:1.6rem;font-weight:700;color:{wr_color}">{win_rate:.0%}</div>
        <div style="font-size:.72rem;color:#95a5a6">{summary['win_count']}G · {summary['loss_count']}P · {summary['neutral_count']}N</div>
      </div>
      <div style="background:#f7f9fc;border-radius:8px;padding:12px 18px;flex:1;min-width:120px;text-align:center">
        <div style="font-size:.75rem;color:#7f8c8d">Retorno promedio</div>
        <div style="font-size:1.6rem;font-weight:700;color:{ret_color}">{ret_sign}{avg_ret:.1f}%</div>
        <div style="font-size:.72rem;color:#95a5a6">por trade cerrado</div>
      </div>
      <div style="background:#f7f9fc;border-radius:8px;padding:12px 18px;flex:1;min-width:120px;text-align:center">
        <div style="font-size:.75rem;color:#7f8c8d">Racha actual</div>
        <div style="font-size:1.6rem;font-weight:700;color:{streak_col}">{abs(streak_val)}</div>
        <div style="font-size:.72rem;color:#95a5a6">{streak_dir} consecutivas</div>
      </div>
    </div>"""

    # ── Open trades ───────────────────────────────────────────────────────────
    if not open_trades and not closed_trades:
        body = """
        <div style="color:#7f8c8d;font-size:.85rem;padding:20px;text-align:center;background:#f9f9f9;border-radius:8px">
          📭 Sin trades aún. Se registran automáticamente cuando una señal BUY/SELL tiene
          confianza ≥ 60% y al menos 2 fuentes de confirmación.
        </div>"""
        return f"""
<div class="section">
  <div class="section-header">🧪 Paper Trading — Modo Simulación
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      Señales auto-registradas · Sin dinero real
    </span>
  </div>
  <div class="section-body">{body}</div>
</div>"""

    # Open positions table
    open_rows = ""
    for t in sorted(open_trades, key=lambda x: x.entry_date, reverse=True):
        conf_badge   = f'<span style="font-size:.72rem;color:#2980b9">{t.confirmation_score}/4 fuentes</span>'
        mom_color    = "#27ae60" if t.momentum_flag == "aligned" else ("#e74c3c" if t.momentum_flag == "late" else "#e67e22")
        mom_label    = {"aligned": "✓ Alineado", "late": "⚠ Tarde", "contrarian": "↩ Contrarian", "neutral": "— Neutral"}.get(t.momentum_flag, t.momentum_flag)
        action_style = "background:#1a9c4a;color:#fff" if t.action == "BUY" else "background:#e74c3c;color:#fff"
        days_open    = (datetime.now().date() - datetime.strptime(t.entry_date, "%Y-%m-%d").date()).days if t.entry_date else "?"

        # P&L calculation
        amt = getattr(t, 'usd_amount', 0) or 0
        cur_price = (current_prices.get(t.ticker) or {}).get("price")
        amt_html = f"${amt:,.0f}" if amt > 0 else "—"
        if amt > 0 and cur_price and t.entry_price > 0:
            cur_val  = amt * (cur_price / t.entry_price)
            pnl_usd  = cur_val - amt
            pnl_pct  = pnl_usd / amt * 100
            pc       = "#27ae60" if pnl_usd >= 0 else "#e74c3c"
            ps       = "+" if pnl_usd >= 0 else ""
            pnl_html = f'<span style="color:{pc};font-weight:700">{ps}${pnl_usd:,.0f} ({ps}{pnl_pct:.1f}%)</span>'
        else:
            pnl_html = '<span style="color:#bdc3c7">—</span>'

        open_rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
          <td style="padding:7px 6px"><strong>{t.ticker}</strong></td>
          <td style="padding:7px 6px;text-align:center">
            <span style="{action_style};padding:2px 8px;border-radius:10px;font-size:.73rem;font-weight:700">{t.action}</span>
          </td>
          <td style="padding:7px 6px;text-align:right">${t.entry_price:.2f}</td>
          <td style="padding:7px 6px;text-align:right;font-weight:600">{amt_html}</td>
          <td style="padding:7px 6px;text-align:right">{pnl_html}</td>
          <td style="padding:7px 6px;text-align:center;font-size:.8rem;color:#7f8c8d">{t.entry_date}</td>
          <td style="padding:7px 6px;text-align:center;font-size:.8rem">{days_open}d</td>
          <td style="padding:7px 6px;text-align:center">{conf_badge}</td>
          <td style="padding:7px 6px;text-align:center;font-size:.78rem;color:{mom_color}">{mom_label}</td>
          <td style="padding:7px 6px;font-size:.72rem;color:#7f8c8d;max-width:200px">{t.pm_market[:55]}</td>
        </tr>"""

    # Closed trades table (last 10)
    closed_rows = ""
    for t in sorted(closed_trades, key=lambda x: x.exit_date or "", reverse=True)[:10]:
        icon  = "🟢" if t.outcome == "win" else ("🔴" if t.outcome == "loss" else "⚪")
        move  = f"{t.price_move_pct:+.1f}%" if t.price_move_pct else "—"
        mc    = "#27ae60" if (t.price_move_pct or 0) > 0 else ("#e74c3c" if (t.price_move_pct or 0) < 0 else "#95a5a6")
        pm_r  = ("YES ✓" if t.pm_resolved_yes else "NO ✗") if t.pm_resolved_yes is not None else "—"
        closed_rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
          <td style="padding:7px 6px">{icon} <strong>{t.ticker}</strong></td>
          <td style="padding:7px 6px;text-align:center;font-size:.8rem">{t.action}</td>
          <td style="padding:7px 6px;text-align:right">${t.entry_price:.2f}</td>
          <td style="padding:7px 6px;text-align:right">${t.exit_price:.2f if t.exit_price else '—'}</td>
          <td style="padding:7px 6px;text-align:center;font-weight:700;color:{mc}">{move}</td>
          <td style="padding:7px 6px;text-align:center;font-size:.78rem;color:#7f8c8d">{pm_r}</td>
          <td style="padding:7px 6px;text-align:center;font-size:.78rem;color:#7f8c8d">{t.exit_date[:10] if t.exit_date else '—'}</td>
        </tr>"""

    # Per-ticker accuracy
    ticker_rows = ""
    for row in sorted(by_ticker, key=lambda x: x.get("trades", 0), reverse=True)[:8]:
        wr = row.get("win_rate", 0)
        wr_c = "#27ae60" if wr >= 0.55 else ("#e74c3c" if wr < 0.45 else "#e67e22")
        ticker_rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
          <td style="padding:6px 8px"><strong>{row['ticker']}</strong></td>
          <td style="padding:6px 8px;text-align:center">{row['trades']}</td>
          <td style="padding:6px 8px;text-align:center;color:{wr_c};font-weight:700">{wr:.0%}</td>
          <td style="padding:6px 8px;text-align:center">{row['wins']}G / {row['losses']}P</td>
        </tr>"""

    if not open_trades:
        _open_inner = '<p style="color:#95a5a6;font-size:.8rem">Sin posiciones abiertas.</p>'
    else:
        _open_inner = (
            '<table style="width:100%;border-collapse:collapse">'
            '<thead><tr style="background:#f7f9fc;border-bottom:2px solid #e0e0e0">'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:left">Ticker</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:center">Acción</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:right">Entrada</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:right">Monto</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:right">P&L hoy</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:center">Fecha</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:center">Días</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:center">Confirmación</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:center">Momentum</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:left">Mercado PM</th>'
            f'</tr></thead><tbody>{open_rows}</tbody></table>'
        )
    open_section = f"""
    <div style="margin-bottom:20px">
      <div style="font-size:.85rem;font-weight:700;color:#2c3e50;margin-bottom:8px">
        📂 Posiciones Abiertas ({len(open_trades)})
      </div>
      {_open_inner}
    </div>"""

    if not closed_trades:
        _closed_inner = '<p style="color:#95a5a6;font-size:.8rem">Sin trades cerrados aún.</p>'
    else:
        _closed_inner = (
            '<table style="width:100%;border-collapse:collapse">'
            '<thead><tr style="background:#f7f9fc;border-bottom:2px solid #e0e0e0">'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:left">Ticker</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:center">Acción</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:right">Entrada</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:right">Salida</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:center">Movimiento</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:center">PM Resolvió</th>'
            '<th style="padding:7px 6px;font-size:.75rem;color:#7f8c8d;text-align:center">Cierre</th>'
            f'</tr></thead><tbody>{closed_rows}</tbody></table>'
        )
    closed_section = f"""
    <div style="margin-bottom:20px">
      <div style="font-size:.85rem;font-weight:700;color:#2c3e50;margin-bottom:8px">
        ✅ Últimos Trades Cerrados ({min(len(closed_trades),10)} de {len(closed_trades)})
      </div>
      {_closed_inner}
    </div>"""

    ticker_section = ""
    if by_ticker:
        ticker_section = f"""
    <div>
      <div style="font-size:.85rem;font-weight:700;color:#2c3e50;margin-bottom:8px">
        📈 Precisión por Ticker
      </div>
      <table style="width:100%;border-collapse:collapse;max-width:400px">
        <thead><tr style="background:#f7f9fc;border-bottom:2px solid #e0e0e0">
          <th style="padding:6px 8px;font-size:.75rem;color:#7f8c8d;text-align:left">Ticker</th>
          <th style="padding:6px 8px;font-size:.75rem;color:#7f8c8d;text-align:center">Trades</th>
          <th style="padding:6px 8px;font-size:.75rem;color:#7f8c8d;text-align:center">Win Rate</th>
          <th style="padding:6px 8px;font-size:.75rem;color:#7f8c8d;text-align:center">G/P</th>
        </tr></thead>
        <tbody>{ticker_rows}</tbody>
      </table>
    </div>"""

    return f"""
<div class="section">
  <div class="section-header">🧪 Paper Trading — Modo Simulación
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      Señales auto-registradas · Sin dinero real · Corre <code>python scripts/paper_trading_check.py</code> para resolver
    </span>
  </div>
  <div class="section-body">
    {kpis_html}
    {open_section}
    {closed_section}
    {ticker_section}
  </div>
</div>"""


def _ensure_watchlist_api():
    """Start the watchlist API server in the background if not already running."""
    import socket, subprocess
    try:
        with socket.create_connection(("localhost", 7741), timeout=0.3):
            return  # already running
    except OSError:
        pass
    api_script = Path(__file__).parent / "scripts" / "watchlist_api.py"
    subprocess.Popen(
        [sys.executable, str(api_script)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


SCORECARD_FILE = Path(__file__).parent / "data" / "scorecard.csv"


def build_decorrelation_section(suppressed_clusters: list, total_before: int, total_after: int) -> str:
    """Show which signals were collapsed and why."""
    if not suppressed_clusters:
        return ""

    n_suppressed = sum(len(c["suppressed_tickers"]) for c in suppressed_clusters)

    rows = ""
    for c in suppressed_clusters:
        suppressed_badges = " ".join(
            f'<span style="background:#1e293b;color:#94a3b8;padding:2px 7px;border-radius:3px;font-size:11px;">{t}</span>'
            for t in c["suppressed_tickers"]
        )
        rows += f"""
        <tr>
          <td style="padding:8px 10px;color:#a5b4fc;font-weight:600;">{c["theme"]}</td>
          <td style="padding:8px 10px;">
            <span style="background:#312e81;color:#c7d2fe;padding:3px 9px;border-radius:4px;font-size:12px;font-weight:600;">
              ✓ {c["leader_ticker"]}
            </span>
            <span style="color:#64748b;font-size:11px;margin-left:6px;">{c["leader_name"][:30]}</span>
          </td>
          <td style="padding:8px 10px;">{suppressed_badges}</td>
          <td style="padding:8px 10px;color:#f59e0b;font-size:12px;text-align:center;">{c["avg_corr"]:.2f}</td>
        </tr>"""

    return f"""
<div class="section" style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:20px;margin:20px 0;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap;">
    <h2 style="color:#e2e8f0;font-size:15px;font-weight:600;margin:0;">
      🔗 Decorrelation Layer
    </h2>
    <span style="background:#1e293b;color:#94a3b8;padding:3px 10px;border-radius:12px;font-size:11px;">
      {total_before} signals in → {total_after} surfaced · {n_suppressed} collapsed
    </span>
    <span style="color:#64748b;font-size:11px;">
      Tickers with |90d corr| &gt; 0.70 on the same factor are collapsed to the highest-conviction expression
    </span>
  </div>
  <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="border-bottom:1px solid #1e293b;">
          <th style="padding:6px 10px;color:#64748b;text-align:left;font-weight:500;">Theme</th>
          <th style="padding:6px 10px;color:#64748b;text-align:left;font-weight:500;">Kept (leader)</th>
          <th style="padding:6px 10px;color:#64748b;text-align:left;font-weight:500;">Suppressed</th>
          <th style="padding:6px 10px;color:#64748b;text-align:center;font-weight:500;">Avg |corr|</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""


def build_calibration_section(stats: dict) -> str:
    """Show the calibration curve — confidence bucket vs actual hit rate."""
    total = stats.get("total_signals", 0)
    oldest = stats.get("oldest_signal", "—")

    if total == 0:
        return f"""
<div class="section" style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:20px;margin:20px 0;">
  <h2 style="color:#e2e8f0;font-size:15px;font-weight:600;margin:0 0 10px 0;">📈 Signal Calibration</h2>
  <p style="color:#64748b;font-size:13px;margin:0;">
    No signal history yet. The calibration curve will build automatically as signals are generated each day.
    Once you have 2–4 weeks of data, this table will show whether higher confidence actually predicts better returns.
  </p>
</div>"""

    horizons = ["1w", "1m", "3m", "6m"]
    horizon_labels = {"1w": "1 Week", "1m": "1 Month", "3m": "3 Months", "6m": "6 Months"}

    # Header row
    header_cells = "".join(
        f'<th style="padding:8px 12px;color:#64748b;text-align:center;font-weight:500;min-width:90px;">{horizon_labels[h]}</th>'
        for h in horizons
    )

    rows = ""
    for bucket in stats["buckets"]:
        if bucket["total"] == 0:
            continue
        row_cells = ""
        for h in horizons:
            hdata = bucket["horizons"].get(h, {})
            n        = hdata.get("n", 0)
            win_rate = hdata.get("win_rate")
            avg_ret  = hdata.get("avg_return")
            if n == 0 or win_rate is None:
                row_cells += '<td style="padding:8px 12px;text-align:center;color:#374151;font-size:12px;">—</td>'
            else:
                color = "#6ee7b7" if win_rate >= 0.55 else ("#fbbf24" if win_rate >= 0.45 else "#f87171")
                ret_str = f"{avg_ret:+.1f}%" if avg_ret is not None else ""
                row_cells += f"""
                <td style="padding:8px 12px;text-align:center;">
                  <span style="color:{color};font-weight:600;font-size:13px;">{win_rate:.0%}</span>
                  <span style="color:#64748b;font-size:11px;display:block;">{ret_str} · n={n}</span>
                </td>"""
        rows += f"""
        <tr style="border-bottom:1px solid #0f172a;">
          <td style="padding:8px 12px;color:#e2e8f0;font-weight:600;">{bucket["label"]}</td>
          <td style="padding:8px 12px;color:#64748b;text-align:center;font-size:12px;">{bucket["total"]}</td>
          {row_cells}
        </tr>"""

    pending_note = ""
    if total < 30:
        pending_note = f'<p style="color:#f59e0b;font-size:12px;margin:12px 0 0 0;">⚠️ {total} signals logged so far — calibration becomes meaningful at ~30+. Keep running the dashboard daily.</p>'

    return f"""
<div class="section" style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:20px;margin:20px 0;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap;">
    <h2 style="color:#e2e8f0;font-size:15px;font-weight:600;margin:0;">📈 Signal Calibration Curve</h2>
    <span style="background:#1e293b;color:#94a3b8;padding:3px 10px;border-radius:12px;font-size:11px;">
      {total} signals logged · since {oldest}
    </span>
    <span style="color:#64748b;font-size:11px;">Win rate = price move in predicted direction at each horizon</span>
  </div>
  <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="border-bottom:1px solid #1e293b;">
          <th style="padding:8px 12px;color:#64748b;text-align:left;font-weight:500;">Confidence</th>
          <th style="padding:8px 12px;color:#64748b;text-align:center;font-weight:500;">Signals</th>
          {header_cells}
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  {pending_note}
</div>"""


def _build_seth_copy_section(date_str: str) -> str:
    """
    Returns an HTML section with a button that formats today's signals + trades
    into a ready-to-paste brief for the Seth Goldman Claude.ai project.
    The JS reads window.DASHBOARD_DATA which is injected later in the page,
    so we use a DOMContentLoaded listener.
    """
    return r"""
<div class="section" style="background:#0f172a;border:1px solid #312e81;border-radius:8px;padding:20px;margin:20px 0;">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
    <div>
      <h2 style="color:#a5b4fc;font-size:16px;font-weight:600;margin:0 0 4px 0;">
        🧠 Seth Goldman — CIO Daily Brief
      </h2>
      <p style="color:#64748b;font-size:12px;margin:0;">
        Click to copy a formatted brief → paste it into your <strong style="color:#94a3b8;">Seth Goldman</strong> project in Claude.ai
      </p>
    </div>
    <button id="sethCopyBtn"
      onclick="sethCopyBrief()"
      style="background:#4f46e5;color:#fff;border:none;border-radius:6px;padding:10px 20px;
             font-size:13px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:8px;
             transition:background 0.2s;"
      onmouseover="this.style.background='#4338ca'"
      onmouseout="this.style.background='#4f46e5'">
      📋 Copy Brief for Seth Goldman
    </button>
  </div>
  <div id="sethCopyFeedback" style="margin-top:10px;font-size:12px;color:#6ee7b7;display:none;">
    ✅ Copied! Open claude.ai → Seth Goldman project → paste it in.
  </div>
</div>

<script>
function sethCopyBrief() {
  var data = window.DASHBOARD_DATA || {};
  var today = data.date || new Date().toISOString().slice(0,10);
  var signals = data.seth_signals || [];
  var trades  = data.seth_trades  || [];
  var prices  = data.current_prices || {};

  var lines = [];
  lines.push("# Daily Investment Brief — " + today);
  lines.push("");
  lines.push("I'm sharing today's Polymarket dashboard data. Please give me your CIO-grade critique:");
  lines.push("1. Signal Quality — are these actionable for a 12–36 month horizon, or noise?");
  lines.push("2. Portfolio Coherence — do the open trades form a coherent macro thesis?");
  lines.push("3. Concentration / Risk — dangerous overlaps or tail risks?");
  lines.push("4. What's Missing — key hedges or sectors absent?");
  lines.push("5. One Actionable Recommendation.");
  lines.push("");
  lines.push("---");
  lines.push("");

  // Signals
  lines.push("## Today's Investment Signals (" + signals.length + " total)");
  lines.push("");
  if (signals.length === 0) {
    lines.push("No signals today.");
  } else {
    var buySignals  = signals.filter(function(s){ return s.action === "BUY"; });
    var sellSignals = signals.filter(function(s){ return s.action === "SELL"; });
    var watchSignals= signals.filter(function(s){ return s.action === "WATCH"; });

    if (buySignals.length) {
      lines.push("**BUY signals:**");
      buySignals.forEach(function(s) {
        lines.push("- " + s.ticker + " (" + s.instrument_name + ") — conf " + Math.round(s.confidence * 100) + "% | " + (s.source_market || "Polymarket"));
      });
      lines.push("");
    }
    if (sellSignals.length) {
      lines.push("**SELL signals:**");
      sellSignals.forEach(function(s) {
        lines.push("- " + s.ticker + " — conf " + Math.round(s.confidence * 100) + "%");
      });
      lines.push("");
    }
    if (watchSignals.length) {
      lines.push("**WATCH signals:**");
      watchSignals.forEach(function(s) {
        lines.push("- " + s.ticker + " — conf " + Math.round(s.confidence * 100) + "%");
      });
      lines.push("");
    }
  }

  // Paper trades
  lines.push("## Open Paper Trades (Simulated Portfolio)");
  lines.push("");
  if (trades.length === 0) {
    lines.push("No open paper trades.");
  } else {
    var totalInvested = 0;
    var totalPnL = 0;
    trades.forEach(function(t){ totalInvested += t.usd_amount; totalPnL += t.pnl_usd; });
    lines.push("**Total simulated capital:** $" + totalInvested.toLocaleString());
    lines.push("**Total P&L today:** $" + totalPnL.toFixed(0) + " (" + (totalPnL / totalInvested * 100).toFixed(1) + "%)");
    lines.push("");
    trades.forEach(function(t) {
      var pnlStr = t.pnl_pct !== 0
        ? " | P&L " + (t.pnl_pct > 0 ? "+" : "") + t.pnl_pct + "% ($" + (t.pnl_usd > 0 ? "+" : "") + t.pnl_usd.toFixed(0) + ")"
        : "";
      lines.push("- " + t.action + " " + t.ticker +
        " @ $" + t.entry_price + " on " + t.entry_date +
        " ($" + t.usd_amount.toLocaleString() + " invested)" +
        (t.current_price ? " | now $" + t.current_price : "") +
        pnlStr);
    });
  }

  lines.push("");
  lines.push("---");
  lines.push("*Generated by Polymarket Investment Dashboard*");

  var brief = lines.join("\n");

  navigator.clipboard.writeText(brief).then(function() {
    var fb = document.getElementById("sethCopyFeedback");
    var btn = document.getElementById("sethCopyBtn");
    fb.style.display = "block";
    btn.textContent = "✅ Copied!";
    btn.style.background = "#059669";
    setTimeout(function() {
      fb.style.display = "none";
      btn.innerHTML = "📋 Copy Brief for Seth Goldman";
      btn.style.background = "#4f46e5";
    }, 3000);
  }).catch(function() {
    // Fallback: create a textarea and select it
    var ta = document.createElement("textarea");
    ta.value = brief;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    document.getElementById("sethCopyFeedback").style.display = "block";
    setTimeout(function() {
      document.getElementById("sethCopyFeedback").style.display = "none";
    }, 3000);
  });
}
</script>
"""


def build_scorecard_section(current_prices: dict) -> str:
    """Build scorecard section from data/scorecard.csv — RB vs HG teams with live prices."""
    if not SCORECARD_FILE.exists():
        return ""

    import csv
    teams: dict[str, list] = {}
    with open(SCORECARD_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            symbol = row.get("Symbol", "").strip()
            team   = row.get("Team", "").strip()
            if symbol and team:
                teams.setdefault(team, []).append(symbol)

    if not teams:
        return ""

    # Fetch prices for all scorecard tickers not already fetched
    all_tickers = [s for tickers in teams.values() for s in tickers]
    missing = [t for t in all_tickers if t not in current_prices]
    if missing:
        extra = fetch_current_prices_batch(missing)
        current_prices.update(extra)

    def team_html(team_name: str, tickers: list) -> str:
        total_delta = 0.0
        counted = 0
        rows = ""
        for ticker in tickers:
            p = current_prices.get(ticker, {})
            price = p.get("price")
            delta = p.get("delta_1d")
            price_str = f"${price:,.2f}" if price else "—"
            if delta is not None:
                d_color = "#27ae60" if delta >= 0 else "#e74c3c"
                sign    = "+" if delta >= 0 else ""
                delta_str = f'<span style="color:{d_color};font-weight:700">{sign}${delta:.2f}</span>'
                total_delta += delta
                counted += 1
            else:
                delta_str = '<span style="color:#bdc3c7">—</span>'
            rows += f"""<tr style="border-bottom:1px solid #f0f0f0">
              <td style="padding:8px 12px;font-weight:700">{ticker}</td>
              <td style="padding:8px 12px;text-align:right">{price_str}</td>
              <td style="padding:8px 12px;text-align:right">{delta_str}</td>
            </tr>"""

        avg_delta = total_delta / counted if counted else 0
        score_color = "#27ae60" if avg_delta >= 0 else "#e74c3c"
        score_sign  = "+" if avg_delta >= 0 else ""
        return f"""
      <div style="flex:1;min-width:260px;background:#f7f9fc;border-radius:10px;overflow:hidden">
        <div style="background:#2c3e50;color:white;padding:12px 16px;display:flex;
                    justify-content:space-between;align-items:center">
          <span style="font-weight:700;font-size:1rem">Team {team_name}</span>
          <span style="font-size:.85rem;color:{score_color};font-weight:700;
                       background:rgba(255,255,255,.1);padding:2px 10px;border-radius:12px">
            {score_sign}${avg_delta:.2f} avg
          </span>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:.84rem">
          <thead><tr style="background:#ecf0f1">
            <th style="padding:7px 12px;text-align:left;color:#7f8c8d;font-size:.75rem">Ticker</th>
            <th style="padding:7px 12px;text-align:right;color:#7f8c8d;font-size:.75rem">Precio</th>
            <th style="padding:7px 12px;text-align:right;color:#7f8c8d;font-size:.75rem">Δ hoy</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>"""

    teams_html = "".join(team_html(name, tickers) for name, tickers in sorted(teams.items()))
    return f"""
<div class="section">
  <div class="section-header">🏆 Scorecard — {" vs ".join(sorted(teams.keys()))}
    <span style="font-size:.75rem;font-weight:400;color:#7f8c8d;margin-left:10px">
      {len(all_tickers)} tickers · precios en tiempo real
    </span>
  </div>
  <div class="section-body">
    <div style="display:flex;gap:20px;flex-wrap:wrap">
      {teams_html}
    </div>
  </div>
</div>"""


def main():
    open_browser = "--no-open" not in sys.argv
    _ensure_watchlist_api()

    markets, inv_signals, risky_signals = run_pipeline()

    client = PolymarketClient()
    raw    = fetch_raw(client)

    print("Generating charts…")
    finsignal_data   = load_finsignal()
    yesterday_snap   = load_yesterday_snapshot()
    prev_signal_keys = get_yesterday_signal_keys(yesterday_snap)

    # ── High-impact enrichments ───────────────────────────────────────────────
    print("Enriching signals with momentum + multi-source confirmation…")
    inv_signals = enrich_signals_with_momentum(inv_signals, finsignal_data)

    # ── Decorrelation layer ───────────────────────────────────────────────────
    print("Running signal decorrelation…")
    inv_signals_all = inv_signals  # keep full list for display / paper trading
    inv_signals_deduped, suppressed_clusters = decorrelate_signals(inv_signals)
    n_suppressed = sum(len(c["suppressed_tickers"]) for c in suppressed_clusters)
    print(f"  {len(inv_signals_all)} signals → {len(inv_signals_deduped)} kept, "
          f"{n_suppressed} suppressed across {len(suppressed_clusters)} clusters")

    b64_top      = chart_top_markets(markets, raw)
    top10_pm_html = build_top10_pm_correlations(inv_signals)
    b64_history  = chart_price_history(finsignal_data)
    b64_momentum = chart_momentum(raw)

    # KPIs — count from deduped set so the numbers reflect real opportunities
    n_buy   = sum(1 for s in inv_signals_deduped if s.action == "BUY")
    n_sell  = sum(1 for s in inv_signals_deduped if s.action == "SELL")
    n_watch = sum(1 for s in inv_signals_deduped if s.action in ("WATCH", "HOLD"))
    delta_buy   = kpi_delta_html(n_buy,   yesterday_snap, "n_buy")
    delta_sell  = kpi_delta_html(n_sell,  yesterday_snap, "n_sell")
    delta_watch = kpi_delta_html(n_watch, yesterday_snap, "n_watch")

    top = max(markets, key=lambda m: m.volume_24h)
    top_vol_str = f"${top.volume_24h/1e6:.1f}M"
    top_market_str = top.question[:30] + "…"

    now = datetime.now()

    chart_signals_html = ""
    if top10_pm_html:
        chart_signals_html = f"""
<div class="section">
  <div class="section-header">🏆 Top 10 Alternativas de Inversión con Correlación Polymarket</div>
  <div class="section-body">
    {top10_pm_html}
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
    owned_tickers     = {t.get("ticker") for t in trades if t.get("ticker")}
    trades_section    = build_trades_section(trades)
    portfolio_recs    = build_portfolio_recommendations_section(inv_signals_deduped, owned_tickers)
    risky_section     = build_risky_section(risky_signals)
    finsignal_quality = build_finsignal_quality_section(finsignal_data)
    watchlist         = load_watchlist()

    priority_topics   = load_priority_topics()
    n_priority = sum(1 for m in markets if match_priority_topic(m.question, priority_topics)[0])
    print(f"  Priority topics: {len(priority_topics)} topics, "
          f"{n_priority} matching markets found")
    priority_watch_section = build_priority_watch_section(markets, priority_topics)

    # Fetch prices for BUY/SELL/high-conf signals + watchlist tickers
    buy_tickers       = list({s.ticker for s in inv_signals_deduped if s.action in ("BUY", "SELL")})
    watch_tickers     = list({s.ticker for s in inv_signals_deduped
                               if s.action == "WATCH"
                               and s.confidence >= 0.75
                               and getattr(s, "confirmation_score", 0) >= 3})
    watchlist_tickers = [e.get("ticker") for e in watchlist if e.get("ticker")]
    all_price_tickers = list(set(buy_tickers + watch_tickers + watchlist_tickers))
    print(f"Fetching current prices for BUY tickers: {buy_tickers}")
    current_prices = fetch_current_prices_batch(all_price_tickers)
    print(f"  Prices: {current_prices}")
    scorecard_section = build_scorecard_section(current_prices)
    watchlist_section = build_watchlist_section(watchlist, markets, raw, current_prices)

    # ── Calibration log: record every BUY/SELL signal with entry price ────────
    print("Logging signals to calibration log…")
    cal_logged = 0
    for s in inv_signals_all:
        if s.action not in ("BUY", "SELL"):
            continue
        price_info  = current_prices.get(s.ticker, {})
        entry_price = price_info.get("price", 0.0)
        if entry_price > 0:
            added = cal_log_signal(
                ticker=s.ticker,
                action=s.action,
                confidence=s.confidence,
                entry_price=entry_price,
                instrument_name=getattr(s, "instrument_name", s.ticker),
                source_market=getattr(s, "source_market", ""),
            )
            if added:
                cal_logged += 1
    # Fill in any due forward returns from previous signals
    cal_filled = update_forward_returns()
    print(f"  Calibration: +{cal_logged} new, {cal_filled} returns filled")
    calibration_stats = get_calibration_stats()

    # ── Paper trading: auto-log qualifying signals ────────────────────────────
    print("Logging qualifying signals to paper trading…")
    pt_logger = PaperTradeLogger()
    # Load manual exclusion list — tickers the user explicitly doesn't want auto-logged
    _pt_exclude_file = config.data_dir / "paper_trades" / "excluded_tickers.json"
    _pt_excluded = set()
    if _pt_exclude_file.exists():
        try:
            _pt_excluded = set(json.loads(_pt_exclude_file.read_text()))
        except Exception:
            pass
    logged_count = 0
    for s in inv_signals:
        if s.ticker in _pt_excluded:
            continue
        conf_score = getattr(s, "confirmation_score", 0)
        conf_sources = getattr(s, "confirmation_sources", [])
        mom_10d = getattr(s, "momentum_10d", 0.0)
        mom_flag = getattr(s, "momentum_flag", "neutral")
        price_info = current_prices.get(s.ticker, {})
        entry_price = price_info.get("price", 0.0)
        if entry_price > 0:
            trade = pt_logger.log_signal(
                signal=s,
                entry_price=entry_price,
                confirmation_score=conf_score,
                confirmation_sources=conf_sources,
                momentum_10d=mom_10d,
                momentum_flag=mom_flag,
            )
            if trade:
                logged_count += 1
    if logged_count:
        print(f"  Logged {logged_count} new paper trade(s)")

    # ── Paper trading section ─────────────────────────────────────────────────
    open_trades   = pt_logger.load_open_trades()
    closed_trades = pt_logger.load_closed_trades()
    paper_trading_section = build_paper_trading_section(open_trades, closed_trades, current_prices)

    # ── Seth Goldman copy brief ───────────────────────────────────────────────
    seth_copy_section = _build_seth_copy_section(now.strftime("%Y-%m-%d"))

    # ── Decorrelation + Calibration sections ─────────────────────────────────
    decorrelation_section = build_decorrelation_section(
        suppressed_clusters, len(inv_signals_all), len(inv_signals_deduped)
    )
    calibration_section = build_calibration_section(calibration_stats)

    # Load saved portfolio from disk to seed the dashboard
    portfolio_file = Path(__file__).parent / "data" / "portfolio" / "portfolio.json"
    saved_portfolio = []
    if portfolio_file.exists():
        try:
            saved_portfolio = json.loads(portfolio_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Build structured data for Seth Goldman copy button
    seth_signals_data = []
    for s in inv_signals:
        seth_signals_data.append({
            "ticker": s.ticker,
            "action": s.action,
            "confidence": round(float(s.confidence), 2),
            "source_market": getattr(s, "source_market", ""),
            "instrument_name": getattr(s, "instrument_name", s.ticker),
        })

    seth_trades_data = []
    for t in open_trades:
        entry  = float(t.entry_price)
        usd    = float(t.usd_amount)
        cur    = (current_prices.get(t.ticker) or {}).get("price", 0.0)
        pnl_pct = round((cur - entry) / entry * 100, 2) if entry > 0 and cur > 0 else 0.0
        pnl_usd = round(usd * pnl_pct / 100, 2)
        seth_trades_data.append({
            "ticker": t.ticker,
            "action": t.action,
            "entry_price": entry,
            "entry_date": t.entry_date,
            "usd_amount": usd,
            "current_price": round(cur, 2),
            "pnl_pct": pnl_pct,
            "pnl_usd": pnl_usd,
            "confidence": round(float(t.confidence), 2),
        })

    dashboard_data = {
        "date": now.strftime("%Y-%m-%d"),
        "current_prices": current_prices,
        "seth_signals": seth_signals_data,
        "seth_trades": seth_trades_data,
    }
    dashboard_data_script = (
        f'<script>window.DASHBOARD_DATA = {json.dumps(dashboard_data)};\n'
        f'window.SAVED_PORTFOLIO = {json.dumps(saved_portfolio)};</script>'
    )

    html = HTML_TEMPLATE.format(
        date            = now.strftime("%Y-%m-%d"),
        datetime        = now.strftime("%Y-%m-%d %H:%M"),
        n_markets       = len(markets),
        n_signals       = len(inv_signals),
        n_buy           = n_buy,
        n_sell          = n_sell,
        n_watch         = n_watch,
        delta_buy       = delta_buy,
        delta_sell      = delta_sell,
        delta_watch     = delta_watch,
        top_vol         = top_vol_str,
        top_market      = top_market_str,
        signal_rows     = build_signal_rows(inv_signals_deduped, priority_topics, owned_tickers, prev_signal_keys),
        chart_top_markets  = b64_top,
        chart_signals_html = chart_signals_html,
        chart_momentum     = b64_momentum or "",
        chart_history_html = chart_history_html,
        paper_trading_html     = paper_trading_section,
        watchlist_section_html = watchlist_section,
        portfolio_recs_html  = portfolio_recs,
        risky_section_html   = risky_section,
        finsignal_quality_html = finsignal_quality,
        trades_section_html  = trades_section,
        scorecard_html         = scorecard_section,
        seth_copy_html         = seth_copy_section,
        decorrelation_html     = decorrelation_section,
        calibration_html       = calibration_section,
        priority_watch_html  = priority_watch_section,
        portfolio_css          = PORTFOLIO_CSS,
        portfolio_section_html = PORTFOLIO_SECTION_HTML,
        buy_modal_html         = BUY_MODAL_HTML,
        dashboard_data_script  = dashboard_data_script,
        portfolio_js           = PORTFOLIO_JS,
    )

    out_path = config.processed_data_dir / f"dashboard_{now.strftime('%Y-%m-%d')}.html"
    out_path.write_text(html, encoding="utf-8")
    # Keep a stable "latest" copy so the portfolio dashboard can always link back
    latest_path = config.processed_data_dir / "dashboard_latest.html"
    latest_path.write_text(html, encoding="utf-8")
    print(f"\nDashboard saved: {out_path}")
    print(f"Latest copy:     {latest_path}")

    save_daily_snapshot(
        now=now,
        markets=markets,
        inv_signals=inv_signals_deduped,
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

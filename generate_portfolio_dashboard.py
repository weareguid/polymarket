#!/usr/bin/env python3
"""
Portfolio Monitoring Dashboard
================================
Generates a self-contained HTML dashboard tracking all positions
from both trades.json (historical) and portfolio.json (dashboard buys).

Usage:
    python generate_portfolio_dashboard.py          # generate + open
    python generate_portfolio_dashboard.py --no-open
"""
import sys
import json
import io
import base64
import webbrowser
from pathlib import Path
from datetime import datetime

import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT           = Path(__file__).parent
TRADES_FILE    = ROOT / "data" / "portfolio" / "trades.json"
PORTFOLIO_FILE = ROOT / "data" / "portfolio" / "portfolio.json"
OUT_DIR        = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Palette ───────────────────────────────────────────────────────────────────
C_GREEN  = "#27ae60"
C_RED    = "#e74c3c"
C_BLUE   = "#2980b9"
C_ORANGE = "#e67e22"
C_DARK   = "#2c3e50"
C_GRAY   = "#7f8c8d"
C_BG     = "#f4f6f9"

CHART_COLORS = ["#2980b9","#27ae60","#e67e22","#8e44ad","#e74c3c",
                "#1abc9c","#f39c12","#3498db","#2ecc71","#9b59b6",
                "#e91e63","#00bcd4","#ff5722","#607d8b","#795548"]


# ── Data loading ──────────────────────────────────────────────────────────────
def load_positions() -> list:
    """
    Merge trades.json (historical, quantity-based) and
    portfolio.json (dashboard buys, usd_amount-based) into a
    unified list of positions.
    """
    positions = []

    # Historical trades (quantity × price)
    if TRADES_FILE.exists():
        try:
            for t in json.loads(TRADES_FILE.read_text()):
                ticker = t.get("ticker", "").upper()
                if not ticker or t.get("action") == "HOLD" and ticker == "CASH":
                    # Keep CASH as a position
                    pass
                qty      = float(t.get("quantity", 0))
                price_in = float(t.get("price_buy", 0))
                positions.append({
                    "id":           str(t.get("id", "")),
                    "ticker":       ticker,
                    "name":         ticker,
                    "invested":     round(qty * price_in, 2),
                    "qty":          qty,
                    "price_in":     price_in,
                    "date":         t.get("date", "")[:10],
                    "source":       t.get("source", "Import"),
                    "action":       t.get("action", "BUY"),
                    "from_file":    "trades.json",
                })
        except Exception as e:
            print(f"  Warning reading trades.json: {e}")

    # Dashboard buys (usd_amount-based)
    if PORTFOLIO_FILE.exists():
        try:
            for t in json.loads(PORTFOLIO_FILE.read_text()):
                ticker   = t.get("ticker", "").upper()
                usd      = float(t.get("usd_amount", 0))
                price_in = float(t.get("price_at_buy") or 0)
                qty      = round(usd / price_in, 6) if price_in > 0 else 0
                positions.append({
                    "id":           str(t.get("id", "")),
                    "ticker":       ticker,
                    "name":         t.get("instrument_name", ticker),
                    "invested":     usd,
                    "qty":          qty,
                    "price_in":     price_in,
                    "date":         (t.get("date_bought") or "")[:10],
                    "source":       t.get("signal_source", "Dashboard"),
                    "action":       t.get("action", "BUY"),
                    "from_file":    "portfolio.json",
                })
        except Exception as e:
            print(f"  Warning reading portfolio.json: {e}")

    return positions


def fetch_prices(tickers: list) -> dict:
    """Fetch current price, 1d delta, and 30d history for each ticker."""
    result = {}
    unique = [t for t in set(tickers) if t and t != "CASH"]
    if not unique:
        return result
    print(f"  Fetching prices for: {unique}")
    for ticker in unique:
        try:
            tk   = yf.Ticker(ticker)
            hist = tk.history(period="35d")
            if hist.empty:
                continue
            price   = round(float(hist["Close"].iloc[-1]), 4)
            delta1d = round(float(hist["Close"].iloc[-1] - hist["Close"].iloc[-2]), 4) if len(hist) >= 2 else 0.0
            pct1d   = round(delta1d / hist["Close"].iloc[-2] * 100, 2) if len(hist) >= 2 else 0.0
            hist30  = hist["Close"].tail(30).tolist()
            result[ticker] = {
                "price":   price,
                "delta1d": delta1d,
                "pct1d":   pct1d,
                "hist30":  hist30,
            }
        except Exception as e:
            print(f"    {ticker}: {e}")
    return result


# ── Chart helpers ─────────────────────────────────────────────────────────────
def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def chart_allocation(positions: list, prices: dict) -> str:
    """Pie chart of current allocation by ticker value."""
    data = {}
    for p in positions:
        t = p["ticker"]
        if t == "CASH":
            val = p["invested"]
        else:
            pr = prices.get(t, {}).get("price")
            val = (pr * p["qty"]) if pr and p["qty"] > 0 else p["invested"]
        if val > 0:
            data[t] = data.get(t, 0) + val

    if not data:
        return ""

    labels = list(data.keys())
    values = list(data.values())
    colors = CHART_COLORS[:len(labels)]

    fig, ax = plt.subplots(figsize=(7, 5.5), facecolor="white")
    wedges, texts, autos = ax.pie(
        values, labels=None, colors=colors,
        autopct=lambda p: f"{p:.1f}%" if p > 3 else "",
        startangle=90, wedgeprops=dict(width=0.55),
        textprops={"fontsize": 9},
    )
    for at in autos:
        at.set_fontweight("bold")
        at.set_fontsize(8.5)

    total = sum(values)
    ax.text(0, 0, f"${total:,.0f}", ha="center", va="center",
            fontsize=13, fontweight="bold", color=C_DARK)

    ax.legend(
        [f"{l}  ${v:,.0f}" for l, v in zip(labels, values)],
        loc="lower center", bbox_to_anchor=(0.5, -0.18),
        ncol=3, fontsize=8, frameon=False,
    )
    ax.set_title("Allocation por Posición", fontsize=12, fontweight="bold",
                 color=C_DARK, pad=10)
    plt.tight_layout()
    b64 = fig_to_b64(fig)
    plt.close(fig)
    return b64


def chart_pnl_bars(positions: list, prices: dict) -> str:
    """Horizontal bar chart of P&L % per ticker."""
    rows = []
    seen = set()
    for p in positions:
        t = p["ticker"]
        if t == "CASH" or t in seen:
            continue
        seen.add(t)
        pr = prices.get(t, {}).get("price")
        if pr and p["price_in"] > 0:
            pnl_pct = (pr - p["price_in"]) / p["price_in"] * 100
            rows.append((t, round(pnl_pct, 2)))

    if not rows:
        return ""

    rows.sort(key=lambda x: x[1])
    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]
    colors = [C_GREEN if v >= 0 else C_RED for v in values]

    fig, ax = plt.subplots(figsize=(8, max(3.5, len(rows) * 0.45 + 1.2)),
                           facecolor="white")
    bars = ax.barh(range(len(rows)), values, color=colors, height=0.65)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.axvline(0, color=C_DARK, linewidth=0.8)
    ax.set_xlabel("P&L %", fontsize=9)
    ax.set_title("P&L por Posición", fontsize=12, fontweight="bold",
                 color=C_DARK)
    ax.set_facecolor("white")
    ax.grid(axis="x", alpha=0.2)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for i, (v, bar) in enumerate(zip(values, bars)):
        sign = "+" if v >= 0 else ""
        ax.text(v + (0.1 if v >= 0 else -0.1), i,
                f"{sign}{v:.1f}%",
                va="center", ha="left" if v >= 0 else "right",
                fontsize=8, color=C_DARK)
    plt.tight_layout()
    b64 = fig_to_b64(fig)
    plt.close(fig)
    return b64


def chart_sparklines(positions: list, prices: dict) -> str:
    """Grid of 30-day sparklines for each position."""
    tickers = list({p["ticker"] for p in positions if p["ticker"] != "CASH"})
    tickers_with_hist = [(t, prices[t]["hist30"]) for t in tickers if t in prices and len(prices[t].get("hist30", [])) > 2]
    if not tickers_with_hist:
        return ""

    n   = len(tickers_with_hist)
    cols = min(4, n)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.2, rows * 1.8),
                              facecolor="white")
    if n == 1:
        axes = [[axes]]
    elif rows == 1:
        axes = [axes]

    idx = 0
    for r in range(rows):
        for c in range(cols):
            ax = axes[r][c]
            if idx >= n:
                ax.set_visible(False)
                continue
            ticker, hist = tickers_with_hist[idx]
            color = C_GREEN if hist[-1] >= hist[0] else C_RED
            ax.plot(hist, color=color, linewidth=1.8)
            ax.fill_between(range(len(hist)), hist, alpha=0.12, color=color)
            ax.set_title(ticker, fontsize=9, fontweight="bold", color=C_DARK, pad=2)
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            pct = prices[ticker].get("pct1d", 0)
            sign = "+" if pct >= 0 else ""
            ax.text(0.97, 0.08, f"{sign}{pct:.1f}%", transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=8,
                    color=C_GREEN if pct >= 0 else C_RED, fontweight="bold")
            idx += 1

    plt.suptitle("Precio últimos 30 días", fontsize=11, fontweight="bold",
                 color=C_DARK, y=1.01)
    plt.tight_layout()
    b64 = fig_to_b64(fig)
    plt.close(fig)
    return b64


# ── HTML builder ──────────────────────────────────────────────────────────────
def build_kpi(label, value, sub="", color=C_DARK):
    return f"""
    <div style="background:#fff;border-radius:12px;padding:18px 22px;
                flex:1;min-width:140px;box-shadow:0 2px 8px rgba(0,0,0,0.07)">
      <div style="font-size:.72rem;color:{C_GRAY};text-transform:uppercase;letter-spacing:.5px;font-weight:600">{label}</div>
      <div style="font-size:1.55rem;font-weight:700;color:{color};margin-top:4px">{value}</div>
      {f'<div style="font-size:.75rem;color:{C_GRAY};margin-top:2px">{sub}</div>' if sub else ''}
    </div>"""


def build_positions_table(positions: list, prices: dict) -> str:
    rows_html = ""
    total_invested = 0
    total_current  = 0

    # Group by ticker for aggregate view
    agg = {}
    for p in positions:
        t = p["ticker"]
        if t not in agg:
            agg[t] = {"invested": 0, "qty": 0, "price_in": p["price_in"],
                      "date": p["date"], "source": p["source"],
                      "name": p["name"], "action": p["action"]}
        agg[t]["invested"] += p["invested"]
        agg[t]["qty"]      += p["qty"]

    for ticker, g in sorted(agg.items(), key=lambda x: -x[1]["invested"]):
        pr_data = prices.get(ticker, {})
        cur     = pr_data.get("price")
        delta1d = pr_data.get("delta1d", 0)
        pct1d   = pr_data.get("pct1d", 0)

        qty     = g["qty"]
        inv     = g["invested"]
        total_invested += inv

        if ticker == "CASH":
            cur_val  = inv
            pnl_d    = 0.0
            pnl_pct  = 0.0
            cur_str  = "$1.00"
            pnl_html = '<td>—</td><td>—</td>'
            d1d_html = '<td>—</td>'
            val_str  = f"${cur_val:,.2f}"
        elif cur:
            cur_val  = cur * qty if qty > 0 else inv
            pnl_d    = cur_val - inv
            pnl_pct  = pnl_d / inv * 100 if inv > 0 else 0
            sign     = "+" if pnl_d >= 0 else ""
            col      = C_GREEN if pnl_d >= 0 else C_RED
            pnl_html = (f'<td style="font-weight:700;color:{col}">{sign}${abs(pnl_d):,.2f}</td>'
                        f'<td style="font-weight:700;color:{col}">{sign}{pnl_pct:.1f}%</td>')
            d_sign   = "+" if delta1d >= 0 else ""
            d_col    = C_GREEN if delta1d >= 0 else C_RED
            d1d_html = f'<td style="color:{d_col};font-weight:600">{d_sign}{pct1d:.1f}%</td>'
            cur_str  = f"${cur:,.4f}" if cur < 10 else f"${cur:,.2f}"
            val_str  = f"${cur_val:,.2f}"
        else:
            cur_val  = inv
            pnl_html = '<td style="color:#bdc3c7">N/A</td><td style="color:#bdc3c7">N/A</td>'
            d1d_html = '<td>—</td>'
            cur_str  = "<span style='color:#bdc3c7'>N/A</span>"
            val_str  = f"${inv:,.2f}"

        total_current += cur_val

        days = ""
        if g["date"]:
            try:
                d = datetime.strptime(g["date"], "%Y-%m-%d")
                days = f"{(datetime.now() - d).days}d"
            except Exception:
                pass

        in_str   = f"${g['price_in']:,.4f}" if g["price_in"] < 10 else f"${g['price_in']:,.2f}"
        qty_str  = f"{qty:,.4f}" if qty < 100 else f"{qty:,.2f}"

        src_short = g["source"][:40]
        tag_col   = "#e8f5e9" if g.get("from_file") else "#fff"

        rows_html += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
          <td style="padding:9px 8px"><strong style="font-size:.95rem">{ticker}</strong>
            <div style="font-size:.71rem;color:{C_GRAY}">{g['name'][:30]}</div></td>
          <td style="padding:9px 8px;text-align:right">${inv:,.2f}</td>
          <td style="padding:9px 8px;text-align:right">{qty_str}</td>
          <td style="padding:9px 8px;text-align:right">{in_str}</td>
          <td style="padding:9px 8px;text-align:right"><strong>{cur_str}</strong></td>
          <td style="padding:9px 8px;text-align:right"><strong>{val_str}</strong></td>
          {pnl_html}
          {d1d_html}
          <td style="padding:9px 8px;text-align:center;font-size:.75rem;color:{C_GRAY}">{days}</td>
          <td style="padding:9px 8px;font-size:.72rem;color:{C_GRAY};max-width:140px">{src_short}</td>
        </tr>"""

    # Totals row
    total_pnl  = total_current - total_invested
    total_pct  = total_pnl / total_invested * 100 if total_invested > 0 else 0
    t_sign     = "+" if total_pnl >= 0 else ""
    t_col      = C_GREEN if total_pnl >= 0 else C_RED

    rows_html += f"""
        <tr style="background:#f7f9fc;font-weight:700;border-top:2px solid #ddd">
          <td style="padding:10px 8px">TOTAL</td>
          <td style="padding:10px 8px;text-align:right">${total_invested:,.2f}</td>
          <td colspan="3" style="padding:10px 8px"></td>
          <td style="padding:10px 8px;text-align:right">${total_current:,.2f}</td>
          <td style="padding:10px 8px;text-align:right;color:{t_col}">{t_sign}${abs(total_pnl):,.2f}</td>
          <td style="padding:10px 8px;text-align:right;color:{t_col}">{t_sign}{total_pct:.1f}%</td>
          <td colspan="2" style="padding:10px 8px"></td>
        </tr>"""

    return rows_html, total_invested, total_current


def build_trades_log(positions: list) -> str:
    sorted_pos = sorted(positions, key=lambda p: p["date"] or "", reverse=True)
    rows = ""
    for p in sorted_pos[:30]:
        action_color = C_GREEN if p["action"] == "BUY" else C_GRAY
        rows += f"""
        <tr style="border-bottom:1px solid #f5f5f5">
          <td style="padding:7px 8px;font-size:.8rem;color:{C_GRAY}">{p['date']}</td>
          <td style="padding:7px 8px">
            <span style="background:{action_color};color:#fff;padding:1px 8px;border-radius:10px;font-size:.72rem;font-weight:700">{p['action']}</span>
          </td>
          <td style="padding:7px 8px"><strong>{p['ticker']}</strong></td>
          <td style="padding:7px 8px;text-align:right">${p['invested']:,.2f}</td>
          <td style="padding:7px 8px;text-align:right">${p['price_in']:,.2f}</td>
          <td style="padding:7px 8px;font-size:.72rem;color:{C_GRAY}">{p['source'][:50]}</td>
          <td style="padding:7px 8px;font-size:.7rem;color:#bdc3c7">{p['from_file']}</td>
        </tr>"""
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    open_browser = "--no-open" not in sys.argv
    now = datetime.now()
    print(f"\n📊 Portfolio Dashboard — {now.strftime('%Y-%m-%d %H:%M')}")

    print("Loading positions…")
    positions = load_positions()
    print(f"  {len(positions)} position entries loaded")

    tickers = list({p["ticker"] for p in positions})
    print("Fetching market prices…")
    prices = fetch_prices(tickers)

    print("Building charts…")
    b64_alloc    = chart_allocation(positions, prices)
    b64_pnl      = chart_pnl_bars(positions, prices)
    b64_sparks   = chart_sparklines(positions, prices)

    # Summary KPIs
    total_invested = sum(p["invested"] for p in positions)
    total_current  = 0
    for p in positions:
        t = p["ticker"]
        if t == "CASH":
            total_current += p["invested"]
        else:
            pr = prices.get(t, {}).get("price")
            total_current += (pr * p["qty"]) if pr and p["qty"] > 0 else p["invested"]

    total_pnl  = total_current - total_invested
    total_pct  = total_pnl / total_invested * 100 if total_invested > 0 else 0
    n_pos      = len({p["ticker"] for p in positions})
    winners    = sum(1 for p in positions
                     if p["ticker"] != "CASH" and prices.get(p["ticker"], {}).get("price", 0) > p["price_in"] > 0)
    losers     = sum(1 for p in positions
                     if p["ticker"] != "CASH" and 0 < prices.get(p["ticker"], {}).get("price", 0) < p["price_in"])

    pnl_sign  = "+" if total_pnl >= 0 else ""
    pnl_color = C_GREEN if total_pnl >= 0 else C_RED

    kpis_html = f"""
    <div style="display:flex;gap:14px;flex-wrap:wrap;padding:20px 0 10px">
      {build_kpi("Invertido Total", f"${total_invested:,.2f}")}
      {build_kpi("Valor Actual", f"${total_current:,.2f}")}
      {build_kpi("P&L Total", f"{pnl_sign}${abs(total_pnl):,.2f}", f"{pnl_sign}{total_pct:.1f}%", pnl_color)}
      {build_kpi("Posiciones", str(n_pos), f"{winners} ganadoras · {losers} perdedoras")}
      {build_kpi("Última actualización", now.strftime("%H:%M"), now.strftime("%Y-%m-%d"), C_GRAY)}
    </div>"""

    # Positions table
    rows_html, _, _ = build_positions_table(positions, prices)
    table_html = f"""
    <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06);margin-bottom:24px">
      <div style="font-size:1rem;font-weight:700;color:{C_DARK};margin-bottom:14px">📋 Posiciones Actuales</div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:.84rem">
          <thead>
            <tr style="background:#f7f9fc;border-bottom:2px solid #e0e0e0">
              <th style="padding:9px 8px;text-align:left;color:{C_GRAY};font-size:.75rem">Ticker</th>
              <th style="padding:9px 8px;text-align:right;color:{C_GRAY};font-size:.75rem">Invertido</th>
              <th style="padding:9px 8px;text-align:right;color:{C_GRAY};font-size:.75rem">Cantidad</th>
              <th style="padding:9px 8px;text-align:right;color:{C_GRAY};font-size:.75rem">Precio Compra</th>
              <th style="padding:9px 8px;text-align:right;color:{C_GRAY};font-size:.75rem">Precio Actual</th>
              <th style="padding:9px 8px;text-align:right;color:{C_GRAY};font-size:.75rem">Valor Actual</th>
              <th style="padding:9px 8px;text-align:right;color:{C_GRAY};font-size:.75rem">P&L $</th>
              <th style="padding:9px 8px;text-align:right;color:{C_GRAY};font-size:.75rem">P&L %</th>
              <th style="padding:9px 8px;text-align:right;color:{C_GRAY};font-size:.75rem">Hoy %</th>
              <th style="padding:9px 8px;text-align:center;color:{C_GRAY};font-size:.75rem">Tiempo</th>
              <th style="padding:9px 8px;text-align:left;color:{C_GRAY};font-size:.75rem">Fuente</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>"""

    # Charts section
    charts_html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px">'
    if b64_alloc:
        charts_html += f"""
        <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06)">
          <img src="data:image/png;base64,{b64_alloc}" style="width:100%">
        </div>"""
    if b64_pnl:
        charts_html += f"""
        <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06)">
          <img src="data:image/png;base64,{b64_pnl}" style="width:100%">
        </div>"""
    charts_html += "</div>"

    sparks_html = ""
    if b64_sparks:
        sparks_html = f"""
        <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06);margin-bottom:24px">
          <img src="data:image/png;base64,{b64_sparks}" style="width:100%">
        </div>"""

    # Trade log
    trade_rows = build_trades_log(positions)
    log_html = f"""
    <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06);margin-bottom:24px">
      <div style="font-size:1rem;font-weight:700;color:{C_DARK};margin-bottom:14px">📝 Historial de Trades</div>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:.83rem">
          <thead>
            <tr style="background:#f7f9fc;border-bottom:2px solid #e0e0e0">
              <th style="padding:7px 8px;text-align:left;color:{C_GRAY};font-size:.74rem">Fecha</th>
              <th style="padding:7px 8px;text-align:left;color:{C_GRAY};font-size:.74rem">Acción</th>
              <th style="padding:7px 8px;text-align:left;color:{C_GRAY};font-size:.74rem">Ticker</th>
              <th style="padding:7px 8px;text-align:right;color:{C_GRAY};font-size:.74rem">Invertido</th>
              <th style="padding:7px 8px;text-align:right;color:{C_GRAY};font-size:.74rem">Precio</th>
              <th style="padding:7px 8px;text-align:left;color:{C_GRAY};font-size:.74rem">Fuente</th>
              <th style="padding:7px 8px;text-align:left;color:{C_GRAY};font-size:.74rem">Origen</th>
            </tr>
          </thead>
          <tbody>{trade_rows}</tbody>
        </table>
      </div>
    </div>"""

    # Full HTML
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Portfolio Dashboard — {now.strftime('%Y-%m-%d')}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: {C_BG}; color: {C_DARK}; }}
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
    .header {{ background: linear-gradient(135deg, #1a1a2e, #16213e);
               color: white; padding: 24px 40px; }}
    .header h1 {{ font-size: 1.6rem; font-weight: 700; }}
    .header .sub {{ font-size: .85rem; color: rgba(255,255,255,0.6); margin-top: 4px; }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 20px 32px 60px; }}
    table tr:hover {{ background: #f8f9fa; }}
    @media (max-width: 768px) {{
      .container {{ padding: 12px; }}
      div[style*="grid-template-columns"] {{ grid-template-columns: 1fr !important; }}
    }}
  </style>
</head>
<body>

<nav class="tab-nav">
  <a href="./dashboard_latest.html">📈 Signals Dashboard</a>
  <a href="#" class="active">💼 Portfolio Monitor</a>
</nav>

<div class="header">
  <h1>💼 Portfolio Dashboard</h1>
  <div class="sub">Actualizado: {now.strftime('%Y-%m-%d %H:%M')} · {n_pos} posiciones · Datos: Yahoo Finance</div>
</div>

<div class="container">
  {kpis_html}
  {charts_html}
  {sparks_html}
  {table_html}
  {log_html}

  <div style="text-align:center;font-size:.75rem;color:{C_GRAY};margin-top:20px">
    Polymarket Investment Adviser · Portfolio Monitor ·
    <code>python generate_portfolio_dashboard.py</code> para actualizar
  </div>
</div>

</body>
</html>"""

    out_path = OUT_DIR / f"portfolio_dashboard_{now.strftime('%Y-%m-%d')}.html"
    # Also write a "latest" version for easy access
    latest_path = OUT_DIR / "portfolio_dashboard_latest.html"
    out_path.write_text(html, encoding="utf-8")
    latest_path.write_text(html, encoding="utf-8")
    print(f"\n✅ Dashboard saved: {out_path}")
    print(f"   Latest:          {latest_path}")

    if open_browser:
        webbrowser.open(f"file://{latest_path}")
        print("   Opening in browser…")


if __name__ == "__main__":
    main()

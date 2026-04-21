"""
Seth Goldman Critique — calls Claude API with the CIO-grade advisor persona
to review today's FinSignal newsletter signals and open paper trades.

Usage (standalone):
    python3 scripts/seth_critique.py              # prints critique to stdout
    python3 scripts/seth_critique.py --json       # outputs raw JSON

Called from generate_dashboard.py to inject a critique section into the HTML.

Requires ANTHROPIC_API_KEY in .env
"""

import json
import os
import sys
import logging
from datetime import date
from pathlib import Path

# ── project root ────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

logger = logging.getLogger(__name__)

# ── paths ────────────────────────────────────────────────────────────────────
_SIGNALS_FILE     = _ROOT / "data" / "finsignal" / "signals_latest.json"
_OPEN_TRADES_FILE = _ROOT / "data" / "paper_trades" / "open_trades.json"
_SYSTEM_PROMPT_FILE = Path(
    "/Users/rodrigogarciaresendiz/wealth&finance/long-term-investment-advisor/system_prompt.md"
)

# ── Seth Goldman system prompt ───────────────────────────────────────────────
def _load_system_prompt() -> str:
    if _SYSTEM_PROMPT_FILE.exists():
        return _SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    # Fallback compact version if file missing
    return (
        "You are a senior global macro and long-term investment strategist with 40+ years "
        "of experience. You think in years and decades, not weeks. You prioritize compounding, "
        "resilience, balance-sheet strength, and pricing power. You write like a CIO briefing "
        "someone with real capital at risk: calm, precise, no hype. "
        "Respond in English."
    )


# ── data loaders ─────────────────────────────────────────────────────────────
def _load_signals() -> list:
    if not _SIGNALS_FILE.exists():
        return []
    try:
        raw = json.loads(_SIGNALS_FILE.read_text(encoding="utf-8"))
        return raw.get("signals", [])
    except Exception:
        return []


def _load_open_trades() -> list:
    if not _OPEN_TRADES_FILE.exists():
        return []
    try:
        raw = json.loads(_OPEN_TRADES_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
    except Exception:
        pass
    return []


# ── prompt builder ────────────────────────────────────────────────────────────
def _build_user_prompt(signals: list, open_trades: list, current_prices: dict | None = None) -> str:
    today = date.today().isoformat()
    lines = [
        f"Date: {today}",
        "",
        "## Task",
        "You are reviewing the daily Polymarket Investment Dashboard. Give a concise CIO-grade critique.",
        "Be direct. Flag what's sound, what's weak, what's missing. No fluff.",
        "",
        "---",
        "",
        "## Today's Newsletter Signals (FinSignal Pipeline)",
    ]

    # Filter to recent high-confidence signals
    top_signals = sorted(
        [s for s in signals if s.get("confidence", 0) >= 0.7],
        key=lambda x: x.get("confidence", 0),
        reverse=True
    )[:10]

    if top_signals:
        for s in top_signals:
            direction = s.get("direction", "?")
            ticker    = s.get("ticker", "?")
            conf      = s.get("confidence", 0)
            context   = s.get("context", "")[:200]
            source    = s.get("source", "")[:60]
            pm_flag   = " [PM CONFIRMS]" if s.get("pm_confirms") else ""
            lines.append(
                f"- {direction} {ticker} (conf={conf:.0%}){pm_flag}: {context}  [{source}]"
            )
    else:
        lines.append("- No high-confidence signals today.")

    lines += [
        "",
        "## Open Paper Trades (Simulated Portfolio)",
    ]

    if open_trades:
        total_invested = sum(float(t.get("usd_amount", 0)) for t in open_trades)
        lines.append(f"Total simulated capital: ${total_invested:,.0f}")
        lines.append("")
        for t in open_trades:
            ticker    = t.get("ticker", "?")
            action    = t.get("action", "?")
            entry     = float(t.get("entry_price", 0))
            usd       = float(t.get("usd_amount", 0))
            entry_dt  = t.get("entry_date", "?")
            conf      = float(t.get("confidence", 0))

            pnl_str = ""
            if current_prices and ticker in current_prices:
                cur = current_prices[ticker]
                if entry > 0:
                    pct = (cur - entry) / entry * 100
                    pnl_usd = usd * (pct / 100)
                    pnl_str = f" | current=${cur:.2f} P&L={pct:+.1f}% (${pnl_usd:+,.0f})"

            lines.append(
                f"- {action} {ticker} @ ${entry:.2f} on {entry_dt} (${usd:,.0f} conf={conf:.0%}){pnl_str}"
            )
    else:
        lines.append("- No open paper trades.")

    lines += [
        "",
        "---",
        "",
        "## Your Critique (CIO perspective)",
        "",
        "Please address:",
        "1. **Signal Quality** — Are today's newsletter signals actionable for a 12-36 month horizon, or are they noise?",
        "2. **Portfolio Coherence** — Do the open paper trades form a coherent macro thesis, or are they scattered?",
        "3. **Concentration / Risk** — Any dangerous concentrations, sector overlaps, or macro tail risks?",
        "4. **What's Missing** — What key hedges, sectors, or signals are absent?",
        "5. **One Actionable Recommendation** — The single most important thing to do next.",
        "",
        "Keep it under 400 words. Write for a founder who thinks like a CIO.",
    ]

    return "\n".join(lines)


# ── main critique call ────────────────────────────────────────────────────────
def run_critique(current_prices: dict | None = None) -> dict:
    """
    Returns dict with keys:
        success: bool
        critique: str  (markdown text)
        error: str     (if success=False)
        signals_reviewed: int
        trades_reviewed: int
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {
            "success": False,
            "critique": "",
            "error": "ANTHROPIC_API_KEY not set in .env",
            "signals_reviewed": 0,
            "trades_reviewed": 0,
        }

    try:
        import anthropic
    except ImportError:
        return {
            "success": False,
            "critique": "",
            "error": "anthropic package not installed. Run: pip3 install anthropic --break-system-packages",
            "signals_reviewed": 0,
            "trades_reviewed": 0,
        }

    signals     = _load_signals()
    open_trades = _load_open_trades()
    system_prompt = _load_system_prompt()
    user_prompt   = _build_user_prompt(signals, open_trades, current_prices)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        critique_text = message.content[0].text

        return {
            "success": True,
            "critique": critique_text,
            "error": "",
            "signals_reviewed": len(signals),
            "trades_reviewed": len(open_trades),
        }

    except Exception as exc:
        logger.error("Seth critique API call failed: %s", exc)
        return {
            "success": False,
            "critique": "",
            "error": str(exc),
            "signals_reviewed": len(signals),
            "trades_reviewed": len(open_trades),
        }


# ── HTML section builder (called from generate_dashboard.py) ─────────────────
def build_seth_critique_section(current_prices: dict | None = None) -> str:
    """Returns a self-contained HTML section for the dashboard."""
    result = run_critique(current_prices)
    today  = date.today().isoformat()

    if not result["success"]:
        error_msg = result["error"]
        if "not set" in error_msg:
            body = (
                '<p style="color:#f59e0b;font-size:13px;">'
                '⚠️ Add <code>ANTHROPIC_API_KEY=sk-ant-...</code> to your <code>.env</code> file '
                'to enable Seth Goldman\'s daily critique.'
                '</p>'
            )
        else:
            body = f'<p style="color:#ef4444;font-size:13px;">Error: {error_msg}</p>'
    else:
        import re
        # Convert markdown to basic HTML
        critique_html = result["critique"]
        # Bold **text**
        critique_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', critique_html)
        # Numbered list items
        critique_html = re.sub(r'(?m)^(\d+)\.\s+', r'<br><strong>\1.</strong> ', critique_html)
        # Line breaks
        critique_html = critique_html.replace('\n\n', '</p><p style="margin:8px 0">').replace('\n', '<br>')
        critique_html = f'<p style="margin:8px 0">{critique_html}</p>'

        sig_count   = result["signals_reviewed"]
        trade_count = result["trades_reviewed"]

        body = f'''
        <div style="background:#1e293b;border-left:3px solid #6366f1;padding:12px 16px;border-radius:4px;margin-bottom:12px;font-size:12px;color:#94a3b8;">
            Reviewed {sig_count} signals · {trade_count} open paper trades · {today}
        </div>
        <div style="font-size:14px;line-height:1.7;color:#e2e8f0;">
            {critique_html}
        </div>
        '''

    return f'''
    <div class="section" style="margin:20px 0;background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:20px;">
        <h2 style="color:#a5b4fc;font-size:16px;font-weight:600;margin:0 0 16px 0;display:flex;align-items:center;gap:8px;">
            🧠 Seth Goldman — CIO Daily Critique
            <span style="font-size:11px;color:#64748b;font-weight:400;">Powered by Claude Opus 4.6</span>
        </h2>
        {body}
    </div>
    '''


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Run Seth Goldman critique")
    parser.add_argument("--json", action="store_true", help="Output raw JSON result")
    args = parser.parse_args()

    result = run_critique()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["success"]:
            print("\n" + "=" * 60)
            print("🧠 SETH GOLDMAN — CIO DAILY CRITIQUE")
            print("=" * 60)
            print(result["critique"])
            print("=" * 60)
            print(f"\nSignals reviewed: {result['signals_reviewed']}")
            print(f"Trades reviewed:  {result['trades_reviewed']}")
        else:
            print(f"\n❌ Critique failed: {result['error']}")

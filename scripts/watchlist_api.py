"""
Watchlist + Portfolio API — tiny local HTTP server (port 7741)

Endpoints:
  POST /add              — add ticker to watchlist.json
  POST /remove           — remove ticker from watchlist.json
  POST /portfolio/add    — save a trade to portfolio.json
  POST /portfolio/remove — remove a trade from portfolio.json
  GET  /portfolio        — return full portfolio as JSON

Run once in the background:
    python scripts/watchlist_api.py &

Or let generate_dashboard.py start it automatically.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

WATCHLIST_FILE  = Path(__file__).parent.parent / "data" / "watchlist.json"
PORTFOLIO_FILE  = Path(__file__).parent.parent / "data" / "portfolio" / "portfolio.json"
PORT = 7741


def load_portfolio():
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PORTFOLIO_FILE.exists():
        try:
            return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_portfolio(data):
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def load():
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"tickers": []}


def save(data):
    WATCHLIST_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence default access log

    def _send(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")

        if self.path == "/add":
            ticker = body.get("ticker", "").strip().upper()
            if not ticker:
                self._send({"ok": False, "error": "ticker requerido"}, 400)
                return
            data = load()
            if any(t["ticker"] == ticker for t in data["tickers"]):
                self._send({"ok": False, "error": f"{ticker} ya existe en watchlist"}, 409)
                return
            data["tickers"].append({
                "ticker":   ticker,
                "name":     body.get("name", ticker),
                "keywords": body.get("keywords", []),
                "notes":    body.get("notes", ""),
            })
            save(data)
            print(f"  + Added {ticker}")
            self._send({"ok": True, "ticker": ticker})

        elif self.path == "/remove":
            ticker = body.get("ticker", "").strip().upper()
            data   = load()
            before = len(data["tickers"])
            data["tickers"] = [t for t in data["tickers"] if t["ticker"] != ticker]
            if len(data["tickers"]) == before:
                self._send({"ok": False, "error": f"{ticker} no encontrado"}, 404)
                return
            save(data)
            print(f"  - Removed {ticker}")
            self._send({"ok": True, "ticker": ticker})

        elif self.path == "/portfolio/add":
            trade = body
            if not trade.get("id") or not trade.get("ticker"):
                self._send({"ok": False, "error": "id y ticker requeridos"}, 400)
                return
            portfolio = load_portfolio()
            # Avoid duplicates by id
            if any(t.get("id") == trade["id"] for t in portfolio):
                self._send({"ok": True, "duplicate": True})
                return
            portfolio.append(trade)
            save_portfolio(portfolio)
            print(f"  + Portfolio: {trade.get('action','BUY')} {trade.get('ticker')} ${trade.get('usd_amount',0):.0f}")
            self._send({"ok": True, "id": trade["id"], "total": len(portfolio)})

        elif self.path == "/portfolio/remove":
            trade_id = str(body.get("id", ""))
            portfolio = load_portfolio()
            before = len(portfolio)
            portfolio = [t for t in portfolio if str(t.get("id")) != trade_id]
            if len(portfolio) == before:
                self._send({"ok": False, "error": "trade no encontrado"}, 404)
                return
            save_portfolio(portfolio)
            print(f"  - Portfolio: removed trade {trade_id}")
            self._send({"ok": True, "id": trade_id, "total": len(portfolio)})

        elif self.path == "/portfolio/rebuild":
            import subprocess, sys
            script = Path(__file__).parent.parent / "generate_portfolio_dashboard.py"
            subprocess.Popen([sys.executable, str(script), "--no-open"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("  ~ Rebuilding portfolio dashboard in background…")
            self._send({"ok": True, "rebuilding": True})

        else:
            self._send({"ok": False, "error": "endpoint no encontrado"}, 404)

    def do_GET(self):
        if self.path == "/portfolio":
            portfolio = load_portfolio()
            self._send({"ok": True, "trades": portfolio, "total": len(portfolio)})
        else:
            self._send({"ok": False, "error": "endpoint no encontrado"}, 404)


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), Handler)
    print(f"Watchlist API running on http://localhost:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)

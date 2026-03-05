# Polymarket Investment Adviser

A system that monitors [Polymarket](https://polymarket.com) — the world's largest prediction market ($9B+ volume) — and converts its signals into stock and ETF investment recommendations.

**Core premise:** Prediction markets price geopolitical and macro events hours or days before traditional markets react. This tool captures that lead time.

---

## What it does

Two pipelines feed a single HTML dashboard:

```
PIPELINE 1 — Automated (runs daily via cron)
──────────────────────────────────────────────
Polymarket API → Top 100 markets → Signal detector
→ StockCorrelator (keywords → ETFs) + RiskyCorrelator (second-order effects)
→ generate_dashboard.py → HTML dashboard opens in browser

PIPELINE 2 — Manual weekly (FinSignal)
──────────────────────────────────────────────
Gmail newsletters → parse financial signals
→ cross-reference with Polymarket → inject into dashboard
```

The dashboard shows:
- BUY / SELL / WATCH signals with confidence scores and timing (`act_now`, `prepare`, `wait`, `late`)
- Top 20 markets by volume with hourly price history
- FinSignal section with newsletter-derived signals

---

## Project structure

```
Polymarket/
├── src/
│   ├── scraper/           # Polymarket API client + trending detector
│   ├── analyzer/          # Volume spike detection, momentum, classifier
│   ├── correlator/        # Knowledge base: country/sector → ETF mappings
│   ├── predictor/         # Signal generator + timing model
│   ├── finsignal/         # Gmail reader + newsletter parser + Polymarket matcher
│   └── utils/             # Config, logger
├── scripts/
│   ├── finsignal_collect.py    # Run FinSignal pipeline
│   ├── daily_collect.py        # Scheduled daily collection
│   └── research/               # One-off research scripts
├── research/
│   └── polycorr/          # Empirical Polymarket → stock correlation research
├── notebooks/
│   └── daily_signals.ipynb     # Interactive signal exploration
├── docs/
│   ├── business_case.md
│   ├── research.md
│   └── ITERATIONS.md
├── generate_dashboard.py  # Main entry point — runs full pipeline + opens HTML
├── run_pipeline.py        # Alternative entry point with step control
└── requirements.txt
```

---

## Installation

**Requirements:** Python 3.9+

```bash
git clone git@github.com:santibatte/polymarket-project.git
cd polymarket-project

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file in the project root (copy from `.env.example`):

```bash
cp .env.example .env
```

```env
# Optional — increases Polymarket API rate limits
POLYMARKET_API_KEY=

# Required only for FinSignal pipeline (Gmail newsletters)
GMAIL_CREDENTIALS_PATH=credentials.json

LOG_LEVEL=INFO
```

The Polymarket pipeline works **without any API key** — the public API is free and unauthenticated.

---

## Usage

### Run the full dashboard (Pipeline 1)

```bash
python generate_dashboard.py
```

This scrapes Polymarket, detects signals, correlates to stocks/ETFs, and opens the HTML dashboard in your browser. No internet access needed to view the saved HTML.

### Run individual pipeline steps

```bash
python run_pipeline.py scrape    # Only fetch markets from Polymarket
python run_pipeline.py signals   # Generate signals from latest snapshot
python run_pipeline.py           # Full pipeline
```

### Run FinSignal (Pipeline 2 — newsletter signals)

```bash
# Demo mode — no Gmail setup needed
python scripts/finsignal_collect.py --demo

# Real mode — reads your Gmail newsletters
python scripts/finsignal_collect.py --days 7
```

For real Gmail access, follow the [Gmail OAuth setup](https://developers.google.com/gmail/api/quickstart/python) and place `credentials.json` in the project root.

---

## How signals work

| Step | What happens | Output |
|------|-------------|--------|
| Scraper | Fetches top 100 active Polymarket markets | Snapshot CSV |
| Detector | Flags volume spikes, price momentum, near-expiry markets | ~185 signals |
| Correlator | Maps each signal to stocks/ETFs via knowledge base | 20–30 instruments |
| Signal Generator | Produces BUY/SELL/WATCH with confidence + timing | Dashboard |

**Knowledge base examples:**
- Countries → ETFs: Iran → XLE/USO/LMT, China → FXI/BABA, Taiwan → TSM/EWT
- Sectors → ETFs: Defense → ITA/LMT/NOC, Crypto → BTC/COIN, Energy → XLE/USO
- Keywords → stocks: `fed` → TLT/XLF, `tariff` → FXI/EWZ, `war` → ITA/GLD

---

## Research — PolyCorr

`research/polycorr/` contains an ongoing study to empirically validate which Polymarket volume patterns predict stock movements, and with what lead time. Uses 411k historical markets (2021–2026, $47.5B total volume).

See `research/polycorr/README.md` for methodology.

---

## Roadmap

- [ ] Portfolio filter — only show signals relevant to your holdings/watchlist
- [ ] Multi-period deltas (24h / 7d / 30d price change per market)
- [ ] Telegram alerts for high-confidence `act_now` signals
- [ ] Signal accuracy tracker — measure if predicted stock moves happened
- [ ] LLM classification to replace hardcoded keyword matching

---

## License

MIT

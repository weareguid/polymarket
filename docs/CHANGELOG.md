# Polymarket Adviser — Changelog

> Registro cronológico de todo lo implementado en el proyecto.
> Actualizar cada vez que se complete una feature, bugfix o cambio de arquitectura.

---

## 2026-02-25

### Snapshot diario de dashboard (`data/snapshots/`)
- **Qué**: Guardado automático de un JSON estructurado por día al finalizar cada corrida del dashboard.
- **Dónde**: `data/snapshots/YYYY-MM-DD/snapshot_YYYY-MM-DD.json`
- **Estructura**: `summary` (KPIs), `investment_signals`, `risky_signals`, `top_markets` (top 30 por volumen), `finsignal`
- **Por qué**: El dashboard HTML cambia cada día y no permite comparar. Con los snapshots se puede hacer análisis histórico: qué señales se repiten, cómo evolucionan los precios YES, trends de momentum semana a semana.
- **Implementación**: Función `save_daily_snapshot()` en `generate_dashboard.py`, llamada al final de `main()`.

### CHANGELOG (`docs/CHANGELOG.md`)
- Creación de este archivo para tracking de implementaciones.

---

## 2026-02-23 a 2026-02-25

### Automatización cron (Mon-Fri 9:00 AM)
- **Qué**: Cron job que corre `generate_dashboard.py` automáticamente en días hábiles a las 9am.
- **Log**: `logs/dashboard_cron.log` — registra cada corrida con métricas (`markets`, `trending`, `signals`).
- **Datos confirmados**:
  - Feb 23: 100 markets (filtered=80), 165 trending, 22 signals, 2 risky
  - Feb 24: 100 markets (filtered=75), 157 trending, 23 signals, 2 risky
  - Feb 25: 100 markets (filtered=72), 147 trending, 24 signals, 6 risky

---

## 2026-02-21

### FinSignal — modo live con Gmail
- **Qué**: Corrida en modo live conectando a Gmail real (`projectpolymarket@gmail.com` via IMAP).
- **Resultado**: 5 emails procesados, 6 tickers extraídos (AMZN, UNH, HUM, CVS, AIQ, BTC-USD).
- **Deduplicación**: Sistema de tracking por UID en `data/finsignal/processed_uids.json` (23 UIDs registrados).
- **Archivo**: `data/finsignal/signals_20260221_151429.json`

---

## 2026-02-20

### MVP completo — primera corrida registrada

#### Scraper (PolymarketClient)
- Conexión a Gamma API: top 100 mercados por volumen 24h.
- Guardado de snapshots raw en `data/raw/markets_YYYYMMDD_HHMMSS.csv`.
- Campos: id, question, category, yes_price, no_price, volume_24h, volume_total, liquidity, end_date, active, slug.

#### TrendingDetector
- Detección por: volume spike, price momentum, liquidity screening, closing date filter.
- Filtrado de ruido (deportes, entretenimiento, e-sports) via `_NOISE_PATTERNS`.
- Método `_is_relevant_for_detection()` para filtrar mercados del gráfico de volumen.

#### StockCorrelator + KnowledgeBase
- Knowledge base con ~13 países → ETFs, 10 sectores → instrumentos, 40+ keywords → tickers.
- Mapeado de eventos geopolíticos a correlaciones directas (russia/ukraine, china/taiwan, fed, tariff, etc.).
- Correlaciones positivas y negativas por tipo de evento.

#### RiskyCorrelator (Non-Obvious Signals)
- Señales de segundo orden: competidores, supply chain, currency, regulatory spillover.
- Sección separada "⚡ Non-Obvious Signals" en el dashboard marcada como "experimental".

#### SignalGenerator + TimingModel
- Clasificación BUY/SELL/WATCH/HOLD con confianza 0-1.
- Timing analysis: `act_now`, `prepare`, `wait`, `late` según días al evento.
- Guardado en `data/processed/investment_signals_YYYYMMDD_HHMMSS.csv`.

#### Dashboard HTML (`generate_dashboard.py`)
- Pipeline completo en un comando: `python generate_dashboard.py`.
- Dashboard autocontenido (~830-860 KB, se abre automáticamente en Chrome).
- Secciones: KPIs, tabla de señales, 4 gráficos (top markets, signals pie, momentum, price history CLOB).
- Precio history desde CLOB API (hourly, top 9 markets).

#### FinSignal Pipeline (Gmail → Stock signals)
- `scripts/finsignal_collect.py`: extrae tickers de newsletters financieras vía Gmail IMAP.
- `--demo` mode con 3 newsletters hardcodeados (NVDA, LMT, META, etc.).
- Matching con mercados de Polymarket: clasifica como CONFIRMS/CONTRADICTS/ORTHOGONAL.
- Sección "📬 FinSignal" integrada en el dashboard.

#### PolyCorr Research — Phase 2A completada
- Análisis de correlaciones Polymarket → Stocks sobre 4,687 mercados (2021-2026).
- Hallazgo crítico: alpha está DURANTE el mercado (mientras sube YES%), no post-resolución.
- Mejores categorías: Commodities +5.03% 7d return, Energy +4.77%.
- Mejores tickers por t-stat: XLE (t=9.76), GOLD (t=7.81), DJT (t=-7.42).
- Scripts en `research/polycorr/scripts/`, datos en `data/historical/`.

---

## Backlog — Pendiente de implementar

Ver `docs/ITERATIONS.md` para priorización detallada. Resumen:

| Prioridad | Feature | Esfuerzo |
|-----------|---------|----------|
| 🔴 Alta | Portfolio personal — filtrar señales por tenencias | Bajo (1-2h) |
| 🔴 Alta | Vista 72h — detectar tendencias sostenidas vs spikes | Bajo (1-2h) |
| 🔴 Alta | Delta ayer — comparar YES price vs snapshot anterior | Medio (2-3h) |
| 🔴 Alta | Telegram alerts — notificar señales >80% act_now | Medio (3-4h) |
| 🟡 Media | Signal accuracy tracker — ¿las señales funcionan? | Alto (4-6h) |
| 🟡 Media | LLM classification — reemplazar keyword matching | Medio (3-4h) |
| 🟡 Media | Arbitraje — YES+NO < 100% en mercados multi-outcome | Medio (3-4h) |
| 🟡 Media | Whale tracker — trades individuales >$50K en CLOB | Medio (3-4h) |
| 🟢 Largo | Backtesting framework | Alto |
| 🟢 Largo | Multi-platform (Kalshi) | Alto |
| 🟢 Largo | Paper trading (Alpaca API) | Alto |

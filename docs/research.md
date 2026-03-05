# Research: Polymarket & Prediction Markets for Investment

## Resumen Ejecutivo

Los mercados de prediccion como Polymarket procesan informacion **ANTES** que los mercados tradicionales. Estudios y casos reales muestran que eventos geopoliticos se pricean horas antes de las noticias mainstream, y hay correlacion casi 1:1 entre odds de conflicto y acciones de defensa.

---

## 1. Casos de Exito Documentados

### Bot de Trading: $313 -> $438,000 en 1 mes
- **Fuente:** [FinBold](https://finbold.com/trading-bot-turns-313-into-438000-on-polymarket-in-a-month/)
- **Estrategia:** Trading de mercados BTC/ETH/SOL de 15 minutos up/down
- **Win rate:** 98%
- **Periodo:** Diciembre 2025 - Enero 2026
- **Key insight:** Explota el lag entre precios de Polymarket y exchanges spot

### "French Whale": $85 millones de ganancia
- **Fuente:** [Yahoo Finance](https://finance.yahoo.com/news/french-whale-polymarket-just-won-185058145.html)
- **Estrategia:** Apuestas direccionales grandes en eleccion Trump
- **Key insight:** Movimientos de whales shiftearon odds de ~50% a 60%+ semanas antes de la eleccion

### "ilovecircle": $2.2M en 2 meses
- **Fuente:** [OKX Learn](https://www.okx.com/en-us/learn/polymarket-trading-lesson-prediction-markets)
- **Estrategia:** Modelos de datos para mercados nicho mal priceados
- **Win rate:** 74%

### Arbitrageur Anonimo: $10K -> $100K en 6 meses
- **Fuente:** [ChainCatcher](https://www.chaincatcher.com/en/article/2212288)
- **Estrategia:** Comprar todas las opciones cuando suman <100%
- **Mercados:** 10,000+ participaciones

---

## 2. Correlaciones Mercado-Acciones Documentadas

### Goldman Sachs "Basket of Geopolitical Risk Stocks"
- **Fuente:** [FinancialContent](https://markets.financialcontent.com/stocks/article/predictstreet-2026-1-19-from-gambling-to-gauges-wall-street-embraces-prediction-markets-as-the-new-macro-hedge)
- **Hallazgo:** Correlacion "nearly 1:1" entre odds de prediction markets y acciones de defensa
- **Ejemplo:** Hanwha Aerospace +25.4%, LIG Nex1 +15.2% siguiendo odds de conflicto en Polymarket
- **Timing:** Prediction markets pricean eventos "hours before hitting mainstream news"

### Hedge Funds Usando Mercados como Hedge
- **Estrategia:** Apuestas "Yes" en lanzamientos de misiles norcoreanos como hedge para longs en acciones surcoreanas
- **Fuente:** Mismo articulo de FinancialContent

### Trump Trade
- **Fuente:** [Yahoo Finance](https://finance.yahoo.com/news/stocks-that-make-up-the-trump-trade-130017653.html)
- **Correlaciones:**
  - Tesla duplico valor post-eleccion, perdio 1/3 despues de tension Trump-Musk
  - DJT (Trump Media) +6% con anuncio de plataforma de prediction markets
  - Correlacion directa entre odds de Trump y small caps (IWM)

---

## 3. Timing y Lead Time

### Cuanto Tiempo de Anticipacion?

| Tipo de Evento | Lead Time | Fuente |
|----------------|-----------|--------|
| Geopolitico | Horas antes de noticias | FinancialContent |
| Elecciones | Semanas (movimientos de whales) | Wikipedia/Polymarket |
| Crypto | Segundos a minutos | QuantVPS |
| Earnings/Corporate | 1-3 dias | Inferido |

### Stock Market Response Time
- **Fuente:** [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0304405X02001484)
- Precios responden a reportes CNBC en segundos
- Reportes positivos incorporados completamente en 1 minuto
- Traders ejecutando en 15 segundos hacen profit significativo
- Research moderno: reaccion a macro news en 5 milisegundos

### Predicciones y Tiempo
- **Fuente:** [Wikipedia](https://en.wikipedia.org/wiki/Prediction_market)
- Predicciones son mejores cuando el evento esta cerca
- Eventos >1 ano fuera: precios sesgados hacia 50% por "time preferences"

---

## 4. Estrategias Rentables Identificadas

### 4.1 Arbitraje Cross-Platform
- **Que es:** Explotar diferencias de precio entre Polymarket, Kalshi, Robinhood
- **Tool:** [EventArb.com](https://www.eventarb.com/)
- **Profit potencial:** 0.5-3% por trade
- **Riesgo:** Oportunidades cierran en segundos
- **Datos:** $40M+ extraidos en arbitraje en 12 meses (ChainCatcher)

### 4.2 Market Rebalancing
- **Fuente:** [Medium - Wanguolin](https://medium.com/@wanguolin/how-to-programmatically-identify-arbitrage-opportunities-on-polymarket-and-why-i-built-a-portfolio-23d803d6a74b)
- **Que es:** YES + NO deberia = $1.00. Si YES=$0.48 y NO=$0.50 (total $0.98), comprar ambos garantiza $0.02 profit
- **Frecuencia:** Constante en mercados multi-opcion

### 4.3 High-Probability Bonds
- **Que es:** Comprar contratos >95% probable por yield garantizado
- **Ejemplo:** Contrato "Bitcoin above $30K by December" a $0.98 = 2% yield
- **Riesgo:** Black swan events

### 4.4 Domain Specialization
- **Que es:** Desarrollar expertise en nicho donde tienes ventaja informacional
- **Ejemplo:** Experto en politica brasilena tradea mercados de Lula
- **Key:** Ser el primero en procesar informacion de tu nicho

### 4.5 Speed Trading / HFT
- **Fuente:** [QuantVPS](https://www.quantvps.com/blog/polymarket-hft-traders-use-ai-arbitrage-mispricing)
- **Que es:** Explotar lag entre Polymarket y exchanges spot (Binance, Coinbase)
- **Requerimientos:** Latencia <50ms, WebSocket API
- **Tool:** Polysights (ML trend indicators)

### 4.6 Hedging Equity Positions
- **Que es:** Usar contratos de Polymarket como binary hedge
- **Ejemplo:** Long South Korea equities + Yes bet on North Korea missile = hedged
- **Quien lo hace:** Hedge funds segun FinancialContent

---

## 5. Riesgos y Warnings

### Solo 0.5% Son Rentables
- **Fuente:** [Yahoo Finance](https://finance.yahoo.com/news/arbitrage-bots-dominate-polymarket-millions-100000888.html)
- Solo 0.51% de wallets tienen profits >$1,000
- 1.7% tienen volumen >$50,000

### Fee Drag
- Polymarket cobra 2% en profits
- Spreads deben ser >2.5-3% para ser rentables despues de fees

### Wash Trading
- **Fuente:** [Fortune](https://fortune.com/2025/11/07/polymarket-wash-trading-inflated-prediction-markets-columbia-research/)
- 45% del trading de sports es ficticio
- 17% de actividad de elecciones es ficticia

### Accuracy Concerns
- **Fuente:** [DL News](https://www.dlnews.com/articles/markets/polymarket-kalshi-prediction-markets-not-so-reliable-says-study/)
- Estudio Vanderbilt: 58% de mercados presidenciales mostraron correlacion serial negativa
- Indica noise trading, no informacion

### Manipulacion
- **Fuente:** [Columbia Statistics](https://statmodeling.stat.columbia.edu/2024/09/06/very-interesting-failed-attempt-at-manipulation-on-polymarket-today/)
- Intento documentado de manipular DJT contract por 3 horas
- Mercados pueden ser moveados por actores con capital

---

## 6. APIs y Recursos Tecnicos

### Polymarket API
- **Docs:** [docs.polymarket.com](https://docs.polymarket.com/developers/gamma-markets-api/overview)
- **Gamma API:** Market data, precios, trades historicos
- **CLOB API:** Order book, trading
- **WebSocket:** Updates en tiempo real (<50ms latency)

### Python Package
- **PyPI:** [polymarket-apis](https://pypi.org/project/polymarket-apis/)
- CLOB, Gamma, WebSocket clients incluidos

### Multi-Platform API
- **FinFeedAPI:** [finfeedapi.com](https://www.finfeedapi.com/products/prediction-markets-api)
- Unifica Polymarket, Kalshi, Myriad, Manifold

### Analytics Tools
- **Polymarket Analytics:** [polymarketanalytics.com](https://polymarketanalytics.com/)
- Dashboards, top traders, arbitrage finder

### Arbitrage Calculator
- **EventArb:** [eventarb.com](https://www.eventarb.com/)
- Cross-platform: Kalshi, Polymarket, Robinhood, IBKR

---

## 7. Research Academico

### Prediction Markets as Financial Derivatives
- **Fuente:** [AInvest](https://www.ainvest.com/news/prediction-markets-frontier-financial-derivatives-institutional-strategies-risk-hedging-alpha-generation-2509/)
- Instituciones logran 12-15% outperformance explotando ineficiencias
- Kalshi valorado en $2B
- BlackRock AIM usa ML para analizar prediction markets

### Market Efficiency in Real Time
- **Fuente:** [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0304405X02001484)
- Precios se ajustan en segundos a nueva informacion
- Pero hay window de profit para los mas rapidos

---

## 8. Takeaways para Nuestro Sistema

### Donde Esta el Alpha

1. **Correlacion Geopolitica:** Casi 1:1 con defensa. Monitorear odds de conflicto -> tradear defensa.

2. **Lead Time Real:** Horas en geopolitica, dias en elecciones. No esperar a noticias.

3. **Nicho Expertise:** Donde tenemos ventaja informacional? Latam? Tech?

4. **Timing:** Actuar cuando conviction >70% y evento dentro de 1-7 dias.

5. **Arbitrage Basico:** Multi-option markets que suman <100% son profit garantizado.

### Que NO Hacer

1. **Competir con HFT:** No tenemos infraestructura para <50ms trades

2. **Ignorar Fees:** 2% come profit en trades de bajo margen

3. **Confiar Ciegamente:** 58% de mercados muestran noise, no signal

4. **Overtrade:** Solo 0.5% son rentables - ser selectivo

---

## 9. Links Completos

### Estrategias
- [Complete Polymarket Playbook](https://jinlow.medium.com/the-complete-polymarket-playbook-finding-real-edges-in-the-9b-prediction-market-revolution-a2c1d0a47d9d)
- [Six Profitable Models](https://www.chaincatcher.com/en/article/2233047)
- [HFT on Polymarket](https://www.quantvps.com/blog/polymarket-hft-traders-use-ai-arbitrage-mispricing)

### Correlaciones
- [Wall Street Embraces Prediction Markets](https://markets.financialcontent.com/stocks/article/predictstreet-2026-1-19-from-gambling-to-gauges-wall-street-embraces-prediction-markets-as-the-new-macro-hedge)
- [Geopolitical Disaster Markets](https://markets.financialcontent.com/stocks/article/predictstreet-2026-1-19-betting-on-the-brink-inside-the-explosive-rise-of-geopolitical-disaster-markets)

### Casos
- [Bot $313->$438K](https://finbold.com/trading-bot-turns-313-into-438000-on-polymarket-in-a-month/)
- [French Whale $85M](https://finance.yahoo.com/news/french-whale-polymarket-just-won-185058145.html)
- [Trading Lessons](https://www.okx.com/en-us/learn/polymarket-trading-lesson-prediction-markets)

### Criticas
- [Accuracy Study](https://www.dlnews.com/articles/markets/polymarket-kalshi-prediction-markets-not-so-reliable-says-study/)
- [Wash Trading](https://fortune.com/2025/11/07/polymarket-wash-trading-inflated-prediction-markets-columbia-research/)

### APIs
- [Polymarket Docs](https://docs.polymarket.com/)
- [Python Package](https://pypi.org/project/polymarket-apis/)
- [FinFeedAPI](https://www.finfeedapi.com/products/prediction-markets-api)

---

**Ultima actualizacion:** Febrero 2026

---

## Research Project: Correlaciones Históricas Polymarket → Stocks

> **Estado:** Pendiente de ejecutar. Dataset disponible. Prioridad: alta.
> **Tipo:** Investigación exploratoria, separada del pipeline de producción.

### Premisa
Tenemos 411,765 mercados históricos de Polymarket. La hipótesis central es que movimientos en el precio YES de ciertos mercados precedieron movimientos en acciones relacionadas por horas o días. Si podemos medir eso, tenemos validación empírica del edge del sistema.

### Dataset disponible
- **Archivo:** `data/historical/markets_historical_20260220.csv` (411k filas, ~185MB total con parquet)
- **Período:** Desde ~2021 hasta Feb 2026
- **Columnas:** `id, question, slug, category, yes_price_final, volume_total, volume_24h, liquidity, start_date, end_date, closed_time, created_at, resolved`
- **Limitación:** Solo tenemos precio FINAL (yes_price_final), no series de tiempo de precio. Para correlaciones necesitamos el histórico de precios via CLOB API.

### Plan de investigación

**Fase 1 — Filtrar mercados financieramente relevantes** (1 día)
- Descartar: deportes, entretenimiento, cripto de corto plazo, celebridades
- Quedarse con: geopolítica, macro, elecciones, commodities, regulación, empresas específicas
- Usar la knowledge base existente de keywords para clasificar
- Target: ~15,000-25,000 mercados relevantes de los 411k totales

**Fase 2 — Bajar precios históricos de Polymarket** (1-2 días)
- CLOB API: `GET /prices-history?market={token_id}&interval=1d&fidelity=60`
- Por cada mercado filtrado, bajar el historial de precio YES día a día
- Guardar en `data/historical/price_series/` como parquets por mercado
- Script: `scripts/fetch_price_series.py` — pausar 0.5s entre calls para no rate-limitear

**Fase 3 — Bajar precios históricos de stocks** (1 día)
- Usar `yfinance` (ya instalado): `yf.download(ticker, start, end)`
- Para cada mercado, identificar el ticker relacionado via knowledge base
- Descargar precio diario de ese ticker en el período del mercado ± 30 días
- Guardar en `data/historical/stock_prices/`

```python
import yfinance as yf

# Ejemplo: mercado sobre Iran → bajar XLE
ticker_data = yf.download("XLE",
    start="2024-03-01",  # 30 días antes del start del mercado
    end="2024-06-01"     # 30 días después del end
)
```

**Fase 4 — Análisis de correlaciones** (2-3 días)
Para cada par (mercado Polymarket, stock relacionado):
- Calcular correlación entre movimiento YES y movimiento del stock
- Medir lag: ¿el YES se movió N días ANTES que el stock? ¿cuánto antes?
- Calcular: si compraste el stock cuando YES cruzó 60% → ¿cuánto ganaste?

Métricas a calcular:
```
- Lead time: días promedio que Polymarket va adelante del stock
- Hit rate: % de veces que la dirección del YES predijo la dirección del stock
- Return: ganancia promedio si se actúa cuando YES > 60% y sube > 10pp en 7 días
- Sharpe: ajustado por volatilidad del período
```

**Fase 5 — Slow Rising Volume Analysis** (1-2 días)
Análisis separado del spike de 24h. Detectar mercados donde el volumen crece sostenidamente durante 2-4 semanas sin ser un spike abrupto.

- Calcular `volume_growth_rate` = pendiente de regresión lineal del volumen diario en ventana de 14 días
- Clasificar: spike (alto en 1-3 días), tendencia (crecimiento lineal 7-21 días), flat
- Hipótesis: las tendencias son mejores señales que los spikes porque reflejan información acumulándose, no reacción a noticia
- Comparar performance de señales generadas por spikes vs tendencias

### Outputs esperados
- `outputs/historical_analysis/correlations_summary.csv` — top correlaciones encontradas
- `outputs/historical_analysis/lead_time_by_category.png` — ¿qué categorías van más adelante?
- `outputs/historical_analysis/slow_vs_spike_performance.png` — ¿tendencia o spike gana más?
- Informe: actualizar esta sección con hallazgos

### Cómo ejecutar (cuando esté listo)
```bash
# Fase 1-2: filtrar y bajar series de precio Polymarket
python scripts/fetch_price_series.py --filter-relevant --output data/historical/price_series/

# Fase 3: bajar stocks
python scripts/fetch_stock_prices.py --input data/historical/price_series/ --output data/historical/stock_prices/

# Fase 4-5: análisis
jupyter notebook notebooks/historical_correlation_analysis.ipynb
```

### Notas importantes
- El análisis es retrospectivo — no garantiza que las correlaciones del pasado se repitan
- Mercados cerrados tienen precio final pero no necesariamente precio a mitad del mercado
- Algunos mercados relevantes son de muy bajo volumen → filtrar por `volume_total > 50,000`
- La CLOB API puede tener rate limiting → respetar pausas entre requests

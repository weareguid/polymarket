# Polymarket Investment Adviser — Project Overview

> Documento de referencia rápida. Última actualización: 2026-02-20

---

## ¿Qué es?

Sistema automático que monitorea **Polymarket** (mercado de predicciones con $9B+ en volumen) y convierte sus señales en recomendaciones de inversión en acciones y ETFs.

**Premisa central:** Los mercados de predicción pricean eventos geopolíticos, económicos y macro *horas o días antes* que los mercados tradicionales. Goldman Sachs ya trackea un "Basket of Geopolitical Risk Stocks" correlacionado con estos mercados.

---

## Lo que hace hoy

### Dos pipelines que se combinan en un dashboard

```
PIPELINE 1 — Automático (cron lunes-viernes 9am)
─────────────────────────────────────────────────
Polymarket API → 100 mercados → Detector de señales
→ StockCorrelator (keywords→ETFs) + RiskyCorrelator (second-order)
→ generate_dashboard.py → HTML abre en Chrome

PIPELINE 2 — Manual semanal (con agente Claude)
─────────────────────────────────────────────────
Gmail (projectpolymarket@gmail.com) → emails nuevos (deduplicados por UID)
→ Análisis con inteligencia del agente → signals_latest.json
→ se inyecta en Pipeline 1 → aparece en dashboard como sección FinSignal

Ver protocolo completo del agente: AGENT_PROMPT.md
```

### Pipeline 1 — Polymarket (4 pasos automáticos)

| Paso | Qué hace | Output |
|------|----------|--------|
| **Scraper** | Descarga los 100 mercados más activos de Polymarket via API | `data/raw/markets_YYYYMMDD.csv` |
| **Detector** | Identifica señales: spikes de volumen, momentum de precio, mercados por vencer | 185 señales típicas |
| **Correlator** | Mapea cada señal a acciones/ETFs usando knowledge base (países, sectores, keywords) | 20-30 instrumentos |
| **Signal Generator** | Genera recomendación final: BUY/SELL/WATCH con confianza y timing | CSV + HTML dashboard |

### Knowledge Base (manual, hardcodeada)
- **Países → ETFs:** Iran → XLE/USO/LMT, China → FXI/BABA, Taiwan → TSM/EWT, etc.
- **Sectores → ETFs:** Defense → ITA/LMT/NOC, Crypto → BTC/COIN/MSTR, Energy → XLE/USO, etc.
- **Keywords → Instrumentos:** "fed" → TLT/XLF, "tariff" → FXI/EWZ, "war" → ITA/GLD, etc.
- **Geopolítica específica:** russia_ukraine, china_taiwan, iran_israel mapeados explícitamente

### Filtros inteligentes
- Descarta mercados de deportes, entretenimiento, religión (no generan señales financieras)
- Word-boundary matching para evitar falsos positivos ("gold medal" no activa GLD)
- Timing model: clasifica entre `act_now`, `prepare`, `wait`, `late` según días al evento

### Dashboard HTML semanal
- Se genera y abre en browser automáticamente
- Autocontenido (sin servidor, sin internet para verlo)
- Incluye: tabla de señales con badges de color, distribución BUY/SELL/WATCH, top 20 mercados por volumen, momentum ratio (actividad hoy vs promedio semanal), historial de precios hora a hora de los top mercados (CLOB API)

### Outputs guardados
- `data/raw/markets_YYYYMMDD.csv` — snapshot diario de mercados
- `data/processed/signals_*.csv` — señales trending detectadas
- `data/processed/correlations_*.csv` — correlaciones con instrumentos
- `data/processed/investment_signals_*.csv` — señales finales de inversión
- `data/processed/dashboard_YYYY-MM-DD.html` — dashboard visual

---

## Lo que viene — Roadmap

### Prioridad Alta (próximas 2 semanas)

**1. Portfolio personal**
Cargar un `portfolio.json` con las acciones que ya se tienen y una watchlist. El sistema solo muestra SELL para lo que uno tiene en cartera, y BUY para lo que está en watchlist. Elimina el ruido de señales irrelevantes.

**2. Deltas multi-período**
Comparar el precio YES de cada mercado contra múltiples períodos anteriores, no solo contra ayer:
- Delta 24h (ayer vs hoy)
- Delta 7 días (semana pasada vs hoy)
- Delta 30 días (mes pasado vs hoy)

Un mercado que pasó de 5% → 22% en 7 días es cualitativamente distinto a uno que lleva un mes en 22%. El cambio de velocidad es la señal real. Se implementa leyendo los snapshots diarios ya guardados.

**3. Alerts automáticos (Telegram)**
Cuando aparece una señal con confianza >80% y timing `act_now`, enviar notificación automática. El sistema hoy requiere revisar el dashboard activamente — con alertas se vuelve proactivo.

### Prioridad Media (mes 2)

**4. Signal accuracy tracker**
Registrar cada señal generada y medir si el precio del stock se movió en la dirección predicha en los siguientes 1, 3 y 7 días (usando yfinance). Sin esto no sabemos si el sistema tiene edge real. Es la pieza que convierte el proyecto de "interesante" a "validado".

**5. Arbitraje en Polymarket**
En mercados multi-outcome, si la suma de todos los precios YES es menor a $1.00, comprar todos garantiza ganancia sin riesgo. Documentado en research: $40M extraídos así en 12 meses. Requiere detectar eventos con múltiples outcomes y calcular el spread.

**6. LLM classification**
Reemplazar el keyword matching hardcodeado por un LLM (Claude API) que clasifica qué instrumentos financieros afecta cada mercado y en qué dirección. Mejora la cobertura de mercados que usan vocabulario que la knowledge base no tiene. Costo: ~$0.01 por corrida.

**7. Whale tracker**
La CLOB API tiene historial de trades individuales. Detectar cuando una sola apuesta mueve >$50K en un mercado. Los whales suelen tener información adelantada. Agregar `whale_activity` como factor de boost en el scoring.

### Investigación de largo plazo — PolyCorr

**PolyCorr: Correlaciones Polymarket → Stocks (en curso)**
Proyecto de investigación separado del pipeline de producción. Objetivo: encontrar empíricamente qué patrones de volumen en Polymarket predicen movimientos de acciones, y con qué lead time.

**Dos hipótesis a validar:**
- **H1 (Spike):** Alto volumen en 24-48h → movimiento de stock en 1-7 días (someone knows something)
- **H2 (Slow Build):** Volumen creciente sostenido en 2-4 semanas → movimiento mayor más tardío (información difundiéndose antes de ser noticia mainstream)

**Estado actual:**
- 411k mercados históricos (2021-2026, $47.5B volumen total) disponibles para análisis
- 7,575 mercados non-crypto financieramente relevantes identificados (Phase 1 completado)
- EDA completo: distribución de volumen, categorías, outcomes, cobertura por ticker
- Fases de análisis definidas: coarse correlation → time-series → ML models

**Carpeta:** `research/polycorr/` — ver README.md ahí para el plan completo

**Por qué importa:** Actualmente el sistema correlaciona keywords → tickers de forma estática. PolyCorr dará evidencia empírica de cuándo y qué tipo de señales tienen edge real, para calibrar los parámetros del detector y el scoring de confianza.

### Futuro (mes 3+)

**8. Backtesting framework**
Una vez acumulados 30+ días de snapshots diarios, simular cómo habrían performado las señales históricamente. Calcular win rate por tipo de evento (geopolítica, crypto, elecciones) y ajustar los parámetros del modelo en base a resultados reales.

**9. Multi-plataforma (Kalshi)**
Kalshi opera con regulación CFTC en EEUU y cubre mercados similares. Cross-referencing permite detectar discrepancias de precio entre plataformas (arbitraje cross-platform) y validar señales: si Polymarket y Kalshi coinciden, la confianza sube. FinFeedAPI tiene una API unificada para ambas.

**10. Paper trading (Alpaca API)**
Conectar con Alpaca (API gratuita) para ejecutar trades automáticamente en modo paper (simulado) durante 30-60 días, antes de arriesgar capital real.

---

## Estado actual del stack

```
Polymarket Gamma API  →  Scraper  →  Detector  →  Correlator  →  Signal Gen  →  HTML Dashboard
Polymarket CLOB API   →  Price History (charts)
```

- **Lenguaje:** Python 3.9
- **Dependencias:** requests, pandas, matplotlib (sin ML ni LLM todavía)
- **Datos externos:** Polymarket API (gratuita, sin autenticación requerida)
- **Frecuencia sugerida:** Semanal (lunes), o con alertas → diario automático

---

*Repositorio: `/Users/santiagobattezzati/repos/Polymarket/`*
*Pipeline completo: `python generate_dashboard.py`*
*Iteraciones detalladas: `docs/ITERATIONS.md`*
*Research de mercado: `docs/research.md`*

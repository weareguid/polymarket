# PolyCorr — Polymarket-to-Stock Correlation Research

> **Estado**: Fase 0 — EDA histórico completado (Feb 2026)
> **Objetivo**: Encontrar correlaciones entre patrones de volumen en Polymarket y movimientos de acciones

---

## ¿Qué estamos investigando?

La hipótesis central: los mercados de predicción como Polymarket incorporan información *antes* que los mercados de capitales. Si podemos identificar **qué tipo de patrones de volumen/precio en Polymarket preceden movimientos de stocks**, tenemos un sistema de señales con edge real.

---

## Dos hipótesis a testear

### H1 — Spike de volumen (señal rápida)
> Alto volumen en poco tiempo → movimiento de stock en las siguientes horas/días

**Perfil:** Un mercado pasa de $50K a $2M en 48h. Algo se filtró, alguien sabe algo.

**Variables clave:**
- `spike_ratio = volume_24h / avg_daily_volume_historico`
- Umbral tentativo: ratio > 10x
- Ventana de observación de stock: 1–7 días post-spike

**Casos históricos documentados:**
- French Whale: apostó $85M en Trump → stocks "Trump Trade" (DJT, IWM, XLE) se movieron semanas antes

---

### H2 — Build sostenido (señal lenta)
> Volumen que crece gradualmente en 2–4 semanas → movimiento más grande pero más tardío

**Perfil:** Un mercado pasa de $200K a $800K en 3 semanas con pendiente positiva constante. La información se filtra lentamente antes de ser top news.

**Variables clave:**
- `vol_slope_14d` = pendiente de regresión lineal del volumen diario en ventana de 14 días
- `vol_growth_consistency` = % de días con volumen > día anterior en ventana de 21 días
- Ventana de observación de stock: 7–30 días

---

## Datos disponibles

| Dataset | Período | Filas | Columnas clave |
|---------|---------|-------|----------------|
| `markets_historical_20260220.csv` | Jul 2021 – Feb 2026 | 411,764 | volume_total, volume_24h, yes_price_final, start_date, end_date |
| `markets.parquet` | Oct 2020 – Dec 2025 | 268,706 | volume (total), outcome_prices (final), created_at, end_date |
| `markets_20260220_*.csv` (daily snapshots) | Feb 2026 → | ~100/día | volume_24h, volume_total, yes_price, snapshot_time |

### Limitación crítica
**No tenemos series de tiempo de volumen** para mercados históricos (2021-2024). Solo tenemos:
- `volume_total` al cierre del mercado
- `volume_24h` en el momento de la descarga (un snapshot)
- Precio final de resolución (`yes_price_final`)

**Para mercados recientes (~últimos 3-6 meses):** la CLOB API SÍ tiene historial de precios (series diarias/horarias). Pero NO tenemos historial de volumen granular.

**Solución arquitectural:**
1. Para análisis histórico: usar `yes_price_final` + `volume_total` como proxy (correlación gruesa)
2. Para análisis reciente: usar CLOB price series + snapshots diarios acumulados
3. **Ir hacia adelante**: los daily snapshots del pipeline producen series de volumen en el tiempo

---

## Estructura de archivos

```
research/polycorr/
├── README.md                           ← este archivo
├── notebooks/
│   ├── 00_eda.ipynb                    ← exploración inicial del dataset histórico
│   ├── 01_coarse_correlations.ipynb   ← correlaciones gruesas (datos históricos)
│   ├── 02_price_series_analysis.ipynb ← análisis de series de precio (CLOB, mercados recientes)
│   └── 03_ml_models.ipynb             ← modelos ML y validación
├── scripts/
│   ├── 01_filter_relevant_markets.py  ← filtro de 411k → ~37k financieramente relevantes
│   ├── 02_fetch_price_series.py       ← CLOB price history para mercados recientes
│   ├── 03_fetch_stock_prices.py       ← yfinance para tickers relacionados
│   ├── 04_feature_engineering.py      ← construcción de feature matrix
│   └── 05_train_models.py             ← entrenamiento y evaluación de modelos
└── outputs/
    ├── eda_summary.md                 ← hallazgos del EDA
    ├── relevant_markets.csv           ← mercados filtrados
    ├── correlations_coarse.csv        ← correlaciones históricas gruesas
    └── model_results.json             ← resultados de los modelos
```

---

## Roadmap de fases

### Fase 0: EDA ✅ En progreso
- Explorar el dataset de 411k mercados
- Entender distribución de volumen, fechas, categorías, outcomes
- Identificar qué tan representativos son los mercados financieramente relevantes
- **Output:** Conclusiones para diseñar el modelo de correlaciones

### Fase 1: Filtrado y clasificación ✅ Completado
- 411k → 37,667 mercados financieramente relevantes (umbral: $50k volumen)
- Categorías: crypto (30k), us_politics (4k), geopolitical (1.6k), macro (446), corporate (552)
- Script: `scripts/research/01_filter_relevant_markets.py`

### Fase 2: Correlación histórica gruesa (próxima)
Para cada mercado relevante cerrado:
1. Obtener `yes_price_final` (¿ocurrió el evento?)
2. Obtener precio del stock relacionado durante el período del mercado
3. Calcular: retorno del stock en ventanas de 1d, 7d, 30d post-resolución
4. Medir: ¿los mercados que resolvieron YES con alto volumen mostraron mayor movimiento de stock?

**Feature matrix (coarse):**
```
volume_total, volume_24h, yes_price_final, market_duration_days,
avg_daily_vol, event_category, market_age_days, days_to_resolution
→ target: stock_return_7d, stock_return_30d
```

### Fase 3: Análisis de series de tiempo (mercados recientes ~6 meses)
- CLOB API: price history diaria/horaria por mercado
- Calcular: price_velocity, spike_detection, slow_build_score
- Correlacionar con daily stock returns (yfinance)
- **Esta fase testa H1 y H2 directamente**

### Fase 4: ML Models
- **Baseline**: Logistic regression (¿volumen alto predice movimiento de stock?)
- **Árbol**: Random Forest / XGBoost (feature importance)
- **Temporal**: LSTM sobre series de precio + volumen
- **Validación**: time-based split (train 2022-2023, val 2024, test 2025)
- **Métrica principal**: Sharpe ratio de señales generadas

### Fase 5: Análisis de patrones comunes
¿Qué tienen en común los mercados que generan las mejores señales?
- Categoría del evento (geopolítica > macro > elecciones?)
- Tipo de activo (defensa > energía > crypto?)
- Timing: ¿cuántos días antes del evento se ve la señal?
- Nivel de probabilidad cuando aparece el volumen (YES al 30% vs 60%)

---

## Preguntas de investigación

1. ¿Cuánto tiempo de anticipación da Polymarket sobre el stock market? (lead time)
2. ¿Los spikes de volumen o los builds sostenidos predicen mejor?
3. ¿Qué categoría de evento da las señales más fuertes?
4. ¿A qué nivel de probabilidad (YES%) vale la pena actuar?
5. ¿Las señales funcionan mejor en mercados con alta o baja liquidez?
6. ¿Hay diferencia entre mercados que resuelven YES vs NO?

---

## Referencias

- [Goldman Sachs: Basket of Geopolitical Risk Stocks](https://markets.financialcontent.com/stocks/article/predictstreet-2026-1-19-from-gambling-to-gauges-wall-street-embraces-prediction-markets-as-the-new-macro-hedge) — correlación "nearly 1:1"
- `docs/research.md` — investigación completa del proyecto
- Hugging Face dataset: mercados históricos de Polymarket (fuente del parquet)

---

*Última actualización: 2026-02-21*

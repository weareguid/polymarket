# Polymarket Adviser — Iteraciones y Next Steps

> Documento vivo. Actualizar cada vez que se complete o se agregue una idea.
> Última actualización: 2026-02-20

---

## ✅ Lo que ya funciona (MVP completado)

| Feature | Detalle |
|---------|---------|
| Scraper | API Gamma, top 100 mercados por volumen 24h |
| Trending Detector | Volume spike, price momentum, closing soon |
| Stock Correlator | Knowledge base con países/sectores/keywords, filtro de deportes/entretenimiento |
| Signal Generator | BUY/SELL/WATCH con confianza y timing |
| Price History | CLOB API, historial hora a hora últimas 24h |
| Dashboard HTML | Auto-generado, se abre en browser, autocontenido |
| Weekly Runner | `python generate_dashboard.py` — pipeline + dashboard en un comando |

---

## 🔴 Alta prioridad

### 1. Portfolio personal — señales personalizadas
**Idea:** Cargar una lista de acciones que ya tenés. El sistema solo te dice SELL si la tenés, y BUY si está en tu watchlist. Sin portfolio → silent.

**Por qué importa:** Hoy te genera SELL COIN aunque no tengas Coinbase. El ruido hace que ignores las señales buenas.

**Implementación:**
- Crear `data/portfolio.json` con `{"owned": ["COIN", "NVDA"], "watchlist": ["LMT", "XLE"]}`
- En `SignalGenerator`, filtrar: SELL solo si ticker en `owned`, BUY solo si en `watchlist`
- Agregar sección "My Portfolio Signals" al dashboard con solo esas señales
- Señales sin match → movidas a sección "Other Signals" colapsada

**Esfuerzo:** Bajo. 1-2 horas.

---

### 2. Vista 72h en el dashboard — detectar tendencias de 3 días
**Idea:** El top 20 de mercados hoy solo muestra volumen de las últimas 24h. Agregar una vista paralela de 72h para capturar cosas que no son un spike sino una tendencia sostenida.

**Por qué importa:** Un mercado con 800K de vol en 72h constante no aparece en el top 24h si hoy tuvo solo 200K, pero es más relevante que un spike de un día que desaparece.

**Implementación:**
- Usar el campo `volume1wk` de la API ya disponible en los raw markets
- Calcular `volume_72h ≈ volume_1wk / 7 * 3` (estimación) — o pedir snapshot de hace 3 días si existe
- Agregar segundo gráfico en el dashboard: "Top 20 por Volumen 72h" con la misma lógica visual que el de 24h
- En el momentum chart, agregar línea de referencia 72h además del promedio semanal
- Si el mismo mercado aparece en ambos rankings → marcarlo con badge "persistente"

**Esfuerzo:** Bajo. 1-2 horas en `generate_dashboard.py`.

---

### 3. Historial de snapshots — comparar hoy vs ayer
**Idea:** Ya guardamos `data/raw/markets_YYYYMMDD.csv` cada día. Comparar el precio YES de cada mercado contra ayer para detectar movimientos bruscos.

**Por qué importa:** Un mercado que pasa de 5% a 22% en 24h es mucho más interesante que uno que lleva días en 22%. Eso es información real.

**Implementación:**
- Al correr el pipeline, cargar el snapshot más reciente anterior
- Para cada mercado, calcular `delta_yes = today_yes - yesterday_yes`
- Usar `delta_yes` como factor adicional en el scoring del TrendingDetector
- Agregar columna "Cambio 24h" en la tabla del dashboard

**Esfuerzo:** Medio. 2-3 horas.

---

### 3. Alerts automáticos — Telegram o email
**Idea:** Cuando aparece una señal de alta confianza (>80%, `act_now`), notificar automáticamente sin tener que abrir el dashboard.

**Por qué importa:** El valor del sistema es actuar antes que el mercado. Si solo revisás el dashboard los lunes, perdés señales que aparecen el miércoles.

**Implementación:**
- Crear `src/notifier/telegram_notifier.py` (Telegram Bot API es gratis y fácil)
- Trigger: señal nueva con `confidence > 0.80` AND `timing == act_now`
- Mensaje: "🔴 SELL LMT 82% | US strikes Iran 1% YES | Vol $3.9M"
- Cron job diario a las 8am y 4pm (horario NY)

**Esfuerzo:** Medio. 3-4 horas.

---

## 🟡 Media prioridad

### 4. Signal accuracy tracker — ¿las señales funcionan?
**Idea:** Trackear cada señal generada y registrar si el precio del stock se movió en la dirección predicha en los siguientes 1, 3, 7 días.

**Por qué importa:** Sin esto no sabemos si el sistema tiene edge real. Es la única forma de saber si vale la pena actuar sobre las señales.

**Implementación:**
- Guardar señales en `data/processed/signal_log.csv` con fecha
- Usar yfinance para bajar precios históricos de stocks
- Calcular: ¿el stock subió/bajó según lo predicho? ¿en cuánto?
- Dashboard section: "Signal Accuracy Last 30 Days" con win rate

**Esfuerzo:** Alto. 4-6 horas. Requiere yfinance + lógica de evaluación.

---

### 5. LLM classification — reemplazar keyword matching
**Idea:** En vez de buscar keywords hardcodeados ("iran", "war", "fed"), usar Claude para clasificar qué instrumentos financieros son relevantes para cada mercado.

**Por qué importa:** Hoy el sistema se pierde mercados válidos que no usan las palabras exactas de la knowledge base. Un LLM entendería "tensión comercial EEUU-China" aunque no diga exactamente "tariff" o "china".

**Implementación:**
- Agregar un paso opcional `--llm` al pipeline
- Para cada mercado trending, prompt: "What stocks/ETFs would be affected by this event and in which direction? Answer in JSON."
- Caché los resultados para no repetir LLM calls
- Comparar cobertura vs sistema actual

**Esfuerzo:** Medio. 3-4 horas. Costo de API: ~$0.01 por corrida.

---

### 6. Arbitraje en Polymarket — YES + NO < 100%
**Idea:** En mercados multi-outcome (ej. "¿Quién gana las elecciones?"), si la suma de todos los YES es <$1.00, comprar todos garantiza ganancia sin riesgo.

**Por qué importa:** Está documentado en research.md — se extrajeron $40M en arbitraje en 12 meses. Es profit garantizado.

**Implementación:**
- Fetch mercados de tipo `event` (grupos con múltiples outcomes)
- Para cada evento, sumar los `outcomePrices` de todos los outcomes
- Si suma < 0.97 → señal de arbitraje con spread calculado
- Mostrar como sección separada "Arb Opportunities" en el dashboard

**Esfuerzo:** Medio. 3-4 horas. Requiere entender la estructura de eventos de la API.

---

### 7. Whale tracker — movimientos grandes
**Idea:** La API CLOB tiene historial de trades. Detectar cuando alguien mueve >$50K en un mercado en una sola apuesta. Los whales suelen saber más que el mercado.

**Por qué importa:** El "French Whale" hizo $85M apostando antes que todos. Los movimientos de whales shiftean el precio y dan señal antes que las noticias.

**Implementación:**
- Fetch trades de CLOB API para top mercados
- Filtrar trades > $X (configurable, default $50K)
- Agregar campo `whale_activity` al TrendingSignal
- Boost de score cuando hay actividad de whale reciente

**Esfuerzo:** Medio. 3-4 horas.

---

## 🔬 Investigación de largo plazo — PolyCorr

### ML Research: Correlaciones Polymarket → Stocks

**Estado:** Fase 2A completada (Feb 2026). Ver `research/polycorr/README.md` para plan completo.

**Hipótesis a testear:**
- **H1 — Spike:** Alto volumen en 24-48h → movimiento de stock en 1-7 días
- **H2 — Slow Build:** Volumen creciente sostenido en 2-4 semanas → señal más fuerte

**Resultados Phase 2A (coarse correlation, 4,687 mercados, 2021-2026):**

| Hallazgo | Resultado | Interpretación |
|----------|-----------|----------------|
| YES vs NO 7d return | YES: +0.39%, NO: +0.90% | La resolución ya estaba priceada al cierre |
| Mejor categoría (YES) | Commodities +5.03%, Energy +4.77% | Señal clara en energía y materias primas |
| Mejor ticker (t-stat) | XLE t=9.76, GOLD t=7.81, DJT t=-7.42 | Energía y defensa — señal fuerte |
| Volume vs |ret_7d| | corr = -0.04 | Volumen total solo no predice tamaño de movimiento |
| Volume bucket (YES) | $100K-$500K: t=2.46 vs $50M+: t=-0.07 | Menos conocido = más alpha |

**Finding crítico:** El alpha está DURANTE el mercado (mientras la probabilidad sube), no POST-resolución. Esto confirma la premisa del sistema: Polymarket lidera al mercado de capitales.

**Next steps:**
1. Phase 2B: CLOB price series → analizar retorno de stocks MIENTRAS sube el YES%
2. Phase 3: daily snapshots acumulados → dataset para H1/H2
3. Feature engineering: `price_velocity`, `spike_ratio`, `vol_slope_14d`

**Scripts:** `research/polycorr/scripts/`
**Outputs:** `outputs/research/`
**Datos:** `data/historical/relevant_markets.csv` (37k mercados), `data/historical/stock_prices/` (57 tickers desde 2021)

---

## 🟢 Futuro / Fase 3+

### 8. Backtesting framework
Usar los snapshots diarios acumulados para simular cómo habrían performado las señales históricamente. Requiere tener al menos 30 días de data guardada.

- **Métrica clave:** Win rate por tipo de evento (geopolitical, crypto, economic)
- **Depende de:** Feature #4 (signal accuracy tracker) acumulando data

### 9. Real-time con WebSocket
Cambiar el polling diario por suscripción WebSocket de la CLOB API para latencia <50ms. Relevante solo para mercados crypto (se mueven rápido). Hoy el daily poll es suficiente para geopolítica.

### 10. Multi-platform — agregar Kalshi
Kalshi opera en EEUU con regulación CFTC, cubre muchos mercados similares. Cross-referencing con Polymarket permite:
- Detectar discrepancias de precio entre plataformas (arb)
- Validar señales: si ambas plataformas coinciden, mayor confianza
- FinFeedAPI tiene una API unificada para ambas

### 11. Sector heatmap en dashboard
Visualización tipo heatmap donde cada sector (defensa, energía, crypto, etc.) muestra cuántas señales activas tiene y en qué dirección. Vista ejecutiva de 30 segundos.

### 12. Broker API — paper trading primero
Conectar con Alpaca (gratuito, tiene API) para ejecutar trades automáticamente en paper trading mode. Antes de arriesgar capital real, validar que las señales tienen edge positivo durante 30-60 días.

---

## 📋 Orden sugerido de implementación

```
Semana 1:   #1 Portfolio personal   (impacto inmediato, bajo esfuerzo)
            #2 Delta yesterday      (mejora calidad de señales)

Semana 2:   #3 Telegram alerts      (hace el sistema proactivo)
            #6 Arbitraje básico     (profit garantizado, fácil de validar)

Semana 3-4: #4 Signal tracker       (necesario para saber si el sistema funciona)

Mes 2:      #5 LLM classification   (mejora cobertura significativamente)
            #7 Whale tracker        (mejora calidad de señales)

Mes 3+:     #8 Backtesting          (una vez que haya 30+ días de data)
            #12 Paper trading       (una vez que backtesting confirme edge)
```

---

## 💡 Ideas sueltas para explorar

- **Kalshi vs Polymarket spread**: mismo evento, precios distintos = arb gratis
- **Elon Musk tweet tracker**: sus tweets mueven stocks en minutos. Polymarket tiene mercados sobre él.
- **Earnings season boost**: activar señales de earnings con mayor agresividad en semanas de resultados
- **Geopolitical calendar**: mapear eventos conocidos (OPEC, Fed meetings, elecciones) y pre-posicionarse
- **Fear & Greed proxy**: ratio de mercados "bearish" vs "bullish" en Polymarket como indicador de sentimiento

# Business Case: Polymarket Investment Adviser

## 1. Premisa Fundamental

> Los mercados de prediccion procesan informacion ANTES que los mercados de valores.

**Evidencia:**
- Prediction markets pricean eventos geopoliticos horas antes de noticias mainstream
- Correlacion ~1:1 entre odds de conflicto y acciones de defensa
- Goldman Sachs ya trackea un "Basket of Geopolitical Risk Stocks" correlacionado con prediction markets

## 2. Oportunidad de Mercado

### El Problema
- Retail investors reciben informacion despues que instituciones
- Las noticias ya estan priceadas cuando llegan a medios tradicionales
- No hay herramientas accesibles para traducir prediction markets a acciones

### La Solucion
Un sistema automatizado que:
1. Monitorea Polymarket en tiempo real
2. Detecta cambios significativos
3. Mapea a instrumentos financieros correlacionados
4. Genera senales de inversion con timing optimo

### Mercado Objetivo
- Traders activos buscando edge
- Family offices con apetito por estrategias alternativas
- Advisers financieros que quieren incorporar data alternativa

## 3. Modelo de Monetizacion (Opciones)

### Opcion A: Uso Personal
- Zero costo externo
- Solo requiere tiempo de desarrollo y mantenimiento
- ROI depende de capital deployado

### Opcion B: Subscription Service
- $99-499/mes por senales
- Target: 100-1000 subscribers
- ARR: $120K - $6M

### Opcion C: Signal Marketplace
- Vender senales en plataformas como Collective2, TradingView
- Revenue share 20-30%
- Escalable sin limite

### Opcion D: Managed Account
- Gestionar capital de terceros
- 2/20 structure (2% management, 20% performance)
- Requiere compliance/regulatory

## 4. Step-by-Step: Como Funciona el Sistema

### Paso 1: Scraping Diario (Automatico)
```
Cada dia a las 6:00 AM:
1. Descargar todos los mercados activos de Polymarket
2. Filtrar por volumen > $10,000 24h
3. Guardar snapshot en CSV con timestamp
```

### Paso 2: Deteccion de Senales
```
Para cada mercado:
1. Calcular cambio de precio vs dia anterior
2. Detectar spikes de volumen (>2x normal)
3. Identificar mercados cerrando en <7 dias
4. Clasificar por categoria (geopolitical, crypto, etc.)
```

### Paso 3: Correlacion con Instrumentos
```
Para cada senal detectada:
1. Buscar en knowledge base:
   - Pais mencionado -> ETFs del pais
   - Sector mencionado -> Sector ETFs
   - Keywords -> Instrumentos relacionados
2. Determinar direccion de correlacion (positiva/negativa)
```

### Paso 4: Analisis de Timing
```
Para cada correlacion:
1. Calcular dias hasta el evento
2. Evaluar conviction (distancia de 50%)
3. Evaluar momentum de volumen
4. Determinar: WAIT / PREPARE / ACT_NOW / LATE
```

### Paso 5: Generacion de Senal
```
Output final:
- Ticker: LMT (Lockheed Martin)
- Accion: BUY
- Fuerza: STRONG
- Confianza: 78%
- Timing: ACT_NOW
- Rationale: "North Korea missile odds at 72%, positive correlation with defense"
- Riesgos: ["Geopolitical event - unpredictable", "Event in 3 days"]
```

### Paso 6: Ejecucion (Manual o Automatica)
```
Opciones:
A) Manual: Revisar senales, decidir, ejecutar en broker
B) Semi-auto: Alertas push, un click para ejecutar
C) Full auto: API a broker, ejecucion automatica con limits
```

## 5. Ejemplo Concreto

### Escenario: Tension China-Taiwan

**Input (Polymarket):**
- Mercado: "China military action against Taiwan in 2026"
- Precio YES: 18% -> 32% (cambio de +14% en 3 dias)
- Volumen: $50,000 -> $180,000 (spike 3.6x)
- Dias hasta resolucion: 45

**Proceso:**
1. **Deteccion:** Volume spike + price momentum detectados
2. **Clasificacion:** Geopolitical (China, Taiwan, military)
3. **Correlacion:**
   - TSM (Taiwan Semi): NEGATIVE correlation -> SELL signal
   - EWT (Taiwan ETF): NEGATIVE -> SELL signal
   - ITA (Defense ETF): POSITIVE -> BUY signal
   - SMH (Semis ETF): NEGATIVE -> SELL signal
4. **Timing:**
   - 45 dias es demasiado temprano para geopolitical
   - Pero conviction subio rapido
   - Recomendacion: PREPARE, actuar si sube a >40%

**Output:**
```
SIGNALS GENERATED:
1. ITA BUY (moderate) - 65% confidence - PREPARE
2. TSM SELL (moderate) - 62% confidence - PREPARE
3. SMH WATCH - monitoring semiconductor exposure
```

## 6. Ventajas Competitivas

### Vs. Trading Manual
- Monitoreo 24/7 automatizado
- No perdemos senales por estar dormidos
- Proceso sistematizado, no emocional

### Vs. Servicios Existentes
- EventArb solo hace arbitrage, no correlacion con stocks
- PolymarketAnalytics no genera senales de inversion
- Nuestro sistema es end-to-end

### Vs. Instituciones
- Ellos tienen mas capital pero mas restricciones
- Somos agiles, sin comite de inversion
- Podemos actuar en mercados que ellos ignoran

## 7. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigacion |
|--------|--------------|---------|------------|
| Polymarket cierra/regulado | Media | Alto | Diversificar a Kalshi |
| Correlaciones incorrectas | Media | Medio | Backtesting continuo |
| Mercados manipulados | Media | Medio | Filtrar por liquidez minima |
| Timing incorrecto | Alta | Medio | Modelo iterativo, aprender de errores |
| Black swan event | Baja | Alto | Position sizing conservador |

## 8. Roadmap de Iteracion

### Fase 1: MVP (Semanas 1-2)
**Objetivo:** Sistema funcional minimo

- [x] Arquitectura definida
- [x] Scraper basico
- [x] Knowledge base inicial
- [x] Generador de senales
- [ ] Primer snapshot real
- [ ] Primeras senales manuales

**Metricas:** Generar 5+ senales diarias

### Fase 2: Validacion (Semanas 3-4)
**Objetivo:** Verificar que senales tienen valor

- [ ] Paper trading de senales
- [ ] Tracking de accuracy
- [ ] Refinamiento de knowledge base
- [ ] Ajuste de thresholds

**Metricas:**
- Win rate >55%
- Sharpe ratio >1.0 en paper

### Fase 3: Backtesting (Semanas 5-6)
**Objetivo:** Validar con datos historicos

- [ ] Obtener datos historicos de Polymarket
- [ ] Obtener datos historicos de stocks
- [ ] Simular estrategia 2024-2025
- [ ] Identificar edge real

**Metricas:**
- Alpha sobre buy-and-hold
- Max drawdown <20%

### Fase 4: Automatizacion (Semanas 7-8)
**Objetivo:** Sistema hands-off

- [ ] Cron jobs para scraping
- [ ] Alertas automaticas (email/Telegram)
- [ ] Dashboard web basico
- [ ] Logging y monitoring

**Metricas:**
- Uptime 99%
- Latencia senal <1 hora

### Fase 5: Mejoras ML (Semanas 9-12)
**Objetivo:** Mejorar predicciones

- [ ] Modelo de timing con historico real
- [ ] NLP para clasificacion automatica
- [ ] Sentiment analysis de mercados
- [ ] Ensemble de senales

**Metricas:**
- Win rate >60%
- Sharpe >1.5

### Fase 6: Produccion (Semana 13+)
**Objetivo:** Trading real

- [ ] Integracion con broker API
- [ ] Position sizing automatico
- [ ] Risk management (stop-loss, etc.)
- [ ] Reporting de performance

**Metricas:**
- ROI positivo
- Risk-adjusted returns

## 9. Como Iterar Cada Modulo

### Scraper
1. **Baseline:** API calls basicos, CSV output
2. **V2:** WebSocket para real-time
3. **V3:** Multi-plataforma (Kalshi, Manifold)
4. **V4:** Historico propio para backtesting

### Knowledge Base
1. **Baseline:** Mapeos manuales hardcoded
2. **V2:** Expandir con mas paises/sectores
3. **V3:** LLM para sugerir correlaciones
4. **V4:** Correlaciones aprendidas de historico

### Timing Model
1. **Baseline:** Heuristicas simples (dias al evento, conviction)
2. **V2:** Incorporar velocity de precio
3. **V3:** Modelo ML con features historicos
4. **V4:** Modelo por categoria de evento

### Signal Generator
1. **Baseline:** Reglas if/then
2. **V2:** Scoring ponderado
3. **V3:** Ensemble de multiples factores
4. **V4:** Optimizacion de portfolio

## 10. Decision Framework

### Cuando ACTUAR
- Conviction >70%
- Volume spike >2x
- Dias al evento: 1-7 (geopolitical), 1-30 (elections)
- Correlacion clara en knowledge base

### Cuando ESPERAR
- Conviction 50-70%
- Volume normal
- Dias al evento >30
- Correlacion ambigua

### Cuando IGNORAR
- Conviction <50%
- Volumen bajo (<$10K)
- Categoria no correlacionada (sports, entertainment)
- Sin instrumentos mapeados

## 11. Conclusiones

### Por que esto puede funcionar
1. **Information edge real:** Prediction markets mueven antes que stocks
2. **Correlaciones documentadas:** Goldman Sachs ya lo hace
3. **Barrera de entrada baja:** API gratuita, data accesible
4. **Iteracion rapida:** Sistema modular, mejora continua

### Por que podria fallar
1. **Competencia:** Mas gente descubre el edge
2. **Regulacion:** Polymarket restringido
3. **Mercados eficientes:** El edge desaparece
4. **Ejecucion:** Malas decisiones de timing/sizing

### Siguiente Paso Inmediato
```
1. Correr el scraper por primera vez
2. Revisar los mercados trending de hoy
3. Manualmente evaluar si las correlaciones hacen sentido
4. Documentar primeras observaciones
```

---

**Creado:** Enero 2026
**Estado:** MVP en desarrollo

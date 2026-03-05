# PolyCorr — Framework de Hipótesis
 

**Última actualización:** 2026-02-21
**Estado:** Borrador activo — se actualiza a medida que encontramos evidencia en los datos

---

## Conceptos financieros básicos (leer primero)



Cuando en este documento hablamos de "tickers" como XLE, RTX, TLT — son códigos de acciones y fondos en la bolsa de EEUU:
- **RTX** = Raytheon Technologies (fabrica misiles Patriot, F-135, sistemas de defensa)
- **LMT** = Lockheed Martin (F-35, sistemas espaciales, misiles)
- **XLE** = Energy Select Sector ETF (no es una empresa, es una canasta de las 20 empresas petroleras más grandes de EEUU — Exxon, Chevron, etc. Sube cuando sube el petróleo)
- **TLT** = iShares 20+ Year Treasury Bond ETF (bonos del gobierno de EEUU a largo plazo. Sube cuando bajan las tasas de interés)
- **IWM** = Russell 2000 ETF (canasta de las 2,000 empresas más chicas de EEUU, muy sensibles a la política doméstica)
- **DJT** = Trump Media & Technology Group (la empresa de medios de Trump, muy volátil)
- **GLD** = SPDR Gold Shares ETF (sigue el precio del oro, sube en incertidumbre global)
- **KTOS** = Kratos Defense & Security Solutions (fabrica drones militares baratos, empresa mediana)

---

### ¿Qué es el Market Cap?

Market Cap (capitalización de mercado) = precio de la acción × cantidad de acciones existentes.

Es el "precio total" de una empresa en el mercado. Ejemplos:
- Apple: ~$3.5 **billones** de dólares → enorme
- RTX (Raytheon): ~$150,000 millones → grande
- Kratos Defense (KTOS): ~$5,000 millones → mediana
- Una empresa de shipping regional: ~$300 millones → pequeña

**Categorías estándar:**
- **Large cap**: más de $10,000 millones. Ejemplos: Apple, Microsoft, RTX, Exxon
- **Mid cap**: $2,000–$10,000 millones. Ejemplos: KTOS, algunas aerolíneas, empresas regionales
- **Small cap**: menos de $2,000 millones. Empresas chicas, nicho, poco conocidas

---

### ¿Por qué el tamaño importa para nuestro análisis?

Cuando querés comprar $1 millón de acciones de Apple, hay millones de vendedores esperándote. Tu compra no mueve el precio ni un centavo.

Cuando querés comprar $1 millón de acciones de una empresa pequeña que solo mueve $200,000 por día en total, tu propia compra ya empieza a mover el precio hacia arriba antes de que terminés de comprar. Eso se llama **impacto de mercado** — vos mismo sos el que mueve el precio en tu contra.

Para los robots de trading automático (HFT), esto es fatal: si el algoritmo detecta una señal y quiere comprar $10 millones de una empresa chica, para cuando termina de ejecutar, el precio ya subió tanto que la ganancia desapareció. Por eso los HFT **no operan en empresas pequeñas o medianas** — no les da el volumen para escalar.

Eso nos deja un espacio: el mismo evento que mueve RTX en milisegundos (y donde el HFT ya llegó antes que nosotros), puede tardar **días** en moverse en KTOS o en un productor de fertilizantes de $800 millones.

---

## Contexto histórico crítico: cómo cambió Polymarket en el tiempo

**⚠️ IMPORTANTE PARA INTERPRETAR LOS DATOS**

No toda la data histórica de Polymarket es igual. El mercado fue evolucionando — los precios de 2022 no son igual de confiables como señal que los de 2025. Esto afecta directamente qué conclusiones podemos sacar de cada época.

### Timeline de eventos clave:

| Período | Qué pasó | Impacto en los datos |
|---------|---------|---------------------|
| **Oct 2020 – mid 2022** | Polymarket recién fundado. Mercados muy poco líquidos, casi solo usuarios retail chicos, spreads de 15–20%. | Precios muy ruidosos. Una probabilidad del 60% podía representar "cualquier cosa entre 45% y 75%" de probabilidad real. **Datos poco confiables para señales.** |
| **Mid 2022 – 2023** | Crece el volumen, primeros traders sofisticados entran. Elecciones de medio término de EEUU en 2022 generan el primer gran ciclo de volumen. | Spreads bajan a 5–8%. Señales más limpias pero todavía ruidosas. **Usar con cautela.** |
| **2024 (elecciones Trump)** | Ciclo electoral masivo. Trump 2024 acumula $1,530 millones de volumen (el mercado más grande de la historia). Volumen mensual pasa de $100M a $1,000M+. Primeras firmas institucionales entran a mirar. | Spreads bajan a 2–3%. Para mercados de alto volumen (>$50M), los precios son ya bastante informativos. **Datos razonablemente confiables para mercados grandes.** |
| **Ene–Jun 2025** | DRW y Susquehanna (dos de las firmas de HFT más grandes del mundo) arman mesas dedicadas. Algoritmos de arbitraje automático empiezan a operar. Spreads comprimen a 1%. | El arbitraje H1 (spikes en horas) empieza a cerrarse para activos líquidos. Los gaps entre Polymarket y acciones grandes duran **horas en lugar de días**. |
| **Jul–Nov 2025** | HFT ya maduro en Polymarket. Volumen diario llega a $200–500M/día. | En mercados de alto volumen mapeados a activos grandes, el H1 ya está prácticamente arbitrado. **La señal H1 para large caps casi desapareció.** |
| **Dic 2025 – hoy** | Spreads llegan a 0.5%. ICE (Bolsa de NY) lanza producto institucional el 11 Feb 2026 basado en Polymarket. Jump Trading invierte en Polymarket y Kalshi. | El H1 para large caps está muerto. El H2 (slow build) y las capas 2, 3, 4 son las únicas señales que sobreviven. **Foco total en slow build y mercados de nicho.** |

### Implicación práctica para el análisis:

Cuando analicemos los datos históricos de quant.parquet (2022–2025), hay que segmentarlo por época:
- Si encontramos una señal H1 muy fuerte en 2023 → probablemente ya no existe en 2026
- Si encontramos una señal H2 en 2023 que también aparece en 2025 → esa es la señal durable
- Los patrones que sobreviven a través de todas las épocas son los más valiosos

---

## Las cuatro hipótesis (Capas) — explicadas desde cero

### Capa 1 — H2: El "Slow Build" (construcción gradual)

**La idea en criollo:**
Hay eventos que no ocurren de golpe — se van gestando durante semanas. Una guerra, un recorte de tasas, el resultado de unas elecciones. En Polymarket, esa gestación se ve como una probabilidad que sube gradualmente: 25% → 30% → 35% → 40%... durante 14 o más días seguidos.

El mercado de acciones también "sabe" que el evento se está acercando, pero lo va incorporando lentamente. La hipótesis es que **el Slow Build en Polymarket anticipa el movimiento acumulado del stock en esa dirección**.

**Ejemplo histórico real — Iran/Israel 2024:**
```
1 Oct:  probabilidad de represalia Israel → 35%  |  RTX: $118
7 Oct:  45%                                       |  RTX: $120  (+1.7%)
14 Oct: 58%                                       |  RTX: $123  (+4.2%)
21 Oct: 70%                                       |  RTX: $126  (+6.8%)
26 Oct: Israel ataca → 95%                        |  RTX: $130  (+10.2%)
```
Quien compró RTX el 7 de octubre, cuando el slow build llevaba una semana, ganó ~8% antes del evento. No hubo que adivinar nada — la señal estaba en Polymarket.

**Ejemplo histórico real — Fed rate cuts 2024:**
```
Jun: probabilidad recorte en Sep → 30%  |  TLT: $88
Jul: 45%                                |  TLT: $92  (+4.5%)
Ago: 62%                                |  TLT: $96  (+9.1%)
Sep: Fed recorta → 95%                  |  TLT: $99  (+12.5%)
```

**¿Cómo lo detectamos en los datos?**
- Tomamos la serie de probabilidad diaria de un mercado
- Contamos días consecutivos de subida
- Umbral: ≥10 días consecutivos subiendo + cambio total ≥15 puntos porcentuales
- Medimos: retorno del stock asociado en los 7, 14, y 30 días siguientes

**¿Por qué sobrevive al HFT?**
Porque no es un gap de precio que se pueda arbitrar en milisegundos. Es una tendencia de semanas que refleja la agregación colectiva de información de miles de personas alrededor del mundo. No se cierra con velocidad — se cierra con más información que contradiga la tendencia.

---

### Capa 2 — Mercados de Nicho sin Mapeo Automático

**La idea en criollo:**
Los algoritmos HFT tienen mapeado: "mercado de Fed → TLT, SPY, DXY". Pero no tienen mapeado: "probabilidad de que Argentina reimplante cepo → GFG (Grupo Financiero Galicia, ADR en NYSE)" o "probabilidad de guerra civil en Sudán → acciones de mineras de oro en Africa".

Esos mercados de nicho tienen señal real pero nadie los está arbitrando porque nadie hizo el trabajo de conectar la pregunta con el activo.

**Ejemplos de correlaciones de nicho a construir:**

| Mercado Polymarket | Activo afectado (no obvio) | Por qué |
|---|---|---|
| "¿Habrá acuerdo de paz en Ucrania?" | Acero y cemento europeos | Reconstrucción post-guerra |
| "¿Colombia legalizará minería en zonas protegidas?" | ETF de mineras de oro colombianas | Nuevo supply de oro |
| "¿Renovará FDA aprobación de Ozempic biosimilar?" | Biotechs chicas con el mismo pathway | Efecto domino regulatorio |
| "¿Ganará Bukele en El Salvador?" | Bonos soberanos salvadoreños | Política fiscal |
| "¿Apple lanzará iPhone plegable?" | Suppliers de vidrio flexible (japoneses) | Supply chain |
| "¿Aumentará China aranceles a soja?" | ADRs de empresas agro argentinas (AGRO) | Commodities |

**¿Cómo lo detectamos?**
Este no es un análisis estadístico puro — requiere construir primero el "mapa de consecuencias". El plan:
1. Tomar las categorías de mercados que ya tenemos (geopolítica, macro, regulación, commodities)
2. Por cada mercado, generar manualmente o con LLM un árbol de activos afectados (primarios, secundarios, terciarios)
3. Buscar en los datos históricos si esos activos se movieron cuando el mercado Polymarket se movió

---

### Capa 3 — Stocks de Mediana Capitalización (el "punto ciego del HFT")

**La idea en criollo:**
Imaginá que detectás que van a invadir un país. Todos corren a comprar Raytheon (RTX, $150,000 millones de market cap) porque es lo más obvio. El HFT ya lo ejecutó antes que vos.

Pero hay una empresa llamada **Kratos Defense (KTOS)** que vale $5,000 millones y fabrica drones militares baratos. También va a subir con ese evento — pero nadie del HFT está monitoreando la correlación entre los mercados de conflicto en Polymarket y KTOS. ¿Por qué no? Porque:

1. KTOS solo mueve ~$150 millones en acciones por día. Si el algoritmo detecta la señal y trata de comprar $50M, ya movió el precio un 10% antes de terminar. El negocio desapareció.
2. El HFT necesita poder entrar y salir en microsegundos sin mover el mercado. Solo funciona en activos ultra-líquidos.

Ese delay entre RTX (reacciona en horas) y KTOS (puede tardar días) es nuestra ventana.

**Más ejemplos del mismo patrón:**

| Evento | Large cap (ya arbitrado) | Mid cap (ventana de días) |
|---|---|---|
| Conflicto armado en Medio Oriente | RTX, LMT (misiles, F-35) | KTOS (drones baratos), AXON (tecnología policial) |
| Sube probabilidad de recorte de Fed | SPY sube, TLT sube | Empresas de real estate regional (alta deuda, sensibles a tasas) |
| Aumenta tensión en Taiwan | TSMC conocido, ya priceado | Empresas de semiconductores que diversifican fuera de Taiwan |
| Sanciones a Rusia se endurecen | Energía europea ya reaccionó | Empresas de GNL (gas natural licuado) que llenan el gap |

**¿Cómo lo detectamos en los datos?**
- Tomar el mismo mercado Polymarket
- Medir retorno de la large cap "obvia" → debería moverse rápido
- Medir retorno de la mid cap "no obvia" → debería moverse más lento, con más días de delay
- Si el delay existe y es consistente, esa es la señal: comprar la mid cap cuando el large cap ya arrancó

---

### Capa 4 — Efectos Secundarios y Terciarios (el árbol de consecuencias)

**La idea en criollo:**
Cuando sube la probabilidad de guerra, todo el mundo piensa en armas. Pero una guerra tiene decenas de efectos en cadena que el mercado tarda en pricear:

**Ejemplo: Guerra en Ucrania (Feb 2022)**
```
Evento directo: invasión rusa
↓
Efectos primarios (priceados en días):
  - Defensa sube: RTX +15%, LMT +12%
  - Gas natural europeo sube: +200%

↓
Efectos secundarios (priceados en semanas):
  - Alemania anuncia rearme → Rheinmetall (empresa alemana) +80% en 6 meses
  - Cierre espacio aéreo → aerolíneas europeas -20%
  - Corte gas ruso → fertilizantes suben (gas = input de fertilizantes)

↓
Efectos terciarios (priceados en meses):
  - Ucrania = 30% del trigo mundial → empresas de granos alternativas suben
  - Ciberseguridad: guerra híbrida → empresas de cyber +30%
  - Shipping: rutas marítimas cambian → empresas de shipping Black Sea
```

El HFT arbitraje los efectos primarios. Los secundarios y terciarios quedan para quien hizo el trabajo de razonar la cadena.

**¿Cómo lo detectamos?**
1. Primero documentar manualmente el árbol de consecuencias para eventos históricos grandes (Ucrania 2022, elecciones Trump 2024, Covid policy changes)
2. Buscar en los datos si los activos terciarios lagguearon a los primarios en días/semanas consistentes
3. Usar eso como plantilla para eventos futuros

---

## El pipeline de detección de mid caps — cómo construirlo

Esta es **la pieza más valiosa y más difícil del sistema**. El resto es análisis estadístico. Esto es inteligencia aplicada.

### El problema que resuelve

Cuando un evento empieza a tomar forma en Polymarket (slow build en Iran, en Fed, en una elección), hay dos tipos de activos que van a moverse:

1. **Los obvios** (large caps): RTX, LMT, XLE — el HFT ya los está monitoreando. Cuando vos te enterás, ya tarde.
2. **Los no obvios** (mid/small caps): empresas que se ven afectadas por el mismo evento pero por razones más indirectas. Estas tardan días. Ahí está la ventana.

El problema es que identificar esos "no obvios" requiere razonamiento complejo: "si sube la probabilidad de un conflicto armado en Medio Oriente... ¿qué empresas de $500M–$5B de market cap se benefician o perjudican?"

Esto no se puede hacer con reglas fijas. Se hace con LLMs.

---

### Arquitectura del pipeline (a construir)

```
ENTRADA: Señal Polymarket
 → Mercado: "Will Israel strike Iran nuclear sites in 2024?"
 → Señal: slow build, probabilidad subió 30pp en 15 días
 → Volumen: $45M acumulado

         ↓

PASO 1: LLM — "Árbol de consecuencias"
 Prompt al LLM con:
   - El texto de la pregunta
   - La categoría (geopolítica, energía, etc.)
   - El contexto del evento
 Output del LLM:
   - Efectos primarios: defensa, petróleo
   - Efectos secundarios: ciberseguridad, shipping, gas natural
   - Efectos terciarios: fertilizantes, cereales, aerolíneas
   - Dirección: sube / baja / incierto
   - Confianza del razonamiento: alta / media / baja

         ↓

PASO 2: LLM — "Búsqueda de empresas mid cap"
 Por cada efecto identificado:
   Prompt: "Para el sector [ciberseguridad israelí],
   dame empresas listadas en bolsa con market cap entre $500M y $10B
   que estén directamente expuestas a [conflicto Iran/Israel]"
 Output:
   - Lista de tickers con justificación
   - Por ejemplo: CHKP (Check Point Software, $17B — israelí, ciberseguridad)
   - ESLT (Elbit Systems, $7B — defensa israelí, mid cap)

         ↓

PASO 3: Validación de liquidez
 Para cada ticker sugerido por el LLM:
   - Verificar que tenga datos disponibles (yfinance)
   - Verificar volumen diario promedio (descartar si < $10M/día)
   - Calcular market cap actual
   - Clasificar: large (>$10B) / mid ($2B–$10B) / small (<$2B)
 Quedarse solo con mid caps con liquidez suficiente para operar

         ↓

PASO 4: Análisis de correlación histórica
 Para cada mid cap validada:
   - Buscar eventos similares anteriores en Polymarket
   - Medir: ¿se movió esta acción cuando ese evento pasó antes?
   - Calcular: ¿con cuántos días de delay?
   - Calcular: ¿en qué magnitud?
 Output: score de "relevancia histórica" por empresa

         ↓

SALIDA: Señal accionable
 Ranking de mid caps por:
   1. Relevancia del razonamiento (calidad del árbol LLM)
   2. Correlación histórica (evidencia empírica)
   3. Liquidez (operable)
   4. Delay estimado (cuándo comprar)
```

---

### Cómo estructurar el prompt al LLM

**Prompt A — Árbol de consecuencias**
```
Sos un analista de riesgo geopolítico con experiencia en mercados financieros.

EVENTO: {texto del mercado Polymarket}
CONTEXTO: La probabilidad pasó de {X}% a {Y}% en los últimos {N} días.
VOLUMEN APOSTADO: ${V} millones.

Tarea: Construí un árbol de consecuencias económicas si este evento OCURRE.
Organizalo en tres niveles:
- PRIMARIO: efectos directos e inmediatos (primeras 48h)
- SECUNDARIO: efectos derivados (1-2 semanas)
- TERCIARIO: efectos de cadena larga (1-3 meses)

Para cada efecto: sector afectado | dirección SUBE/BAJA | razonamiento 1-2 oraciones | confianza ALTA/MEDIA/BAJA
```

**Prompt B — Identificación de mid caps**
```
Sos un analista de equity con foco en empresas de mediana capitalización.

SECTOR AFECTADO: {sector del árbol de consecuencias}
DIRECCIÓN: {SUBE / BAJA}
EVENTO DETONADOR: {texto del evento}

Tarea: Identificá empresas listadas en bolsas de EEUU o Europa con:
- Market cap entre $500M y $8,000M
- Exposición DIRECTA al sector mencionado
- No las primeras que vienen a la mente (esas ya las cubren los grandes bancos)

Para cada empresa: ticker | bolsa | market cap aprox | por qué está expuesta | cuál es el "punto ciego" del mercado
```

---

### Por qué los LLMs son clave acá y no una simple base de datos

Una base de datos de "empresa → sector" no alcanza. El razonamiento tiene que ser causal y contextual:

- ¿Por qué una empresa de fertilizantes se ve afectada por una guerra en Ucrania? Porque Rusia exporta gas natural → el gas es el insumo principal de los fertilizantes nitrogenados → si se corta el gas, suben los costos → las empresas que producen fertilizantes alternativos se benefician.
- Esa cadena no está en ninguna base de datos. Está en el razonamiento.

Los LLMs pueden hacer ese razonamiento de cadena con alta calidad si el prompt está bien diseñado. El sistema usa la evidencia histórica (Paso 4) para validar o descartar las sugerencias del LLM.

---

### Validación del pipeline

Se valida cuando, para un evento histórico conocido:
1. El LLM identifica correctamente las empresas que se movieron
2. El delay estimado coincide con el delay real en los datos
3. Al menos 60% de las mid caps sugeridas se movieron en la dirección predicha

**Evento de test ideal: Invasión de Ucrania, Feb 2022** — hay datos completos, movimientos documentados, y consecuencias bien conocidas (Rheinmetall, fertilizantes, gas europeo, aerolíneas).

---

### Próximos pasos para construir esto

1. Testear prompt A y B manualmente en 3 eventos históricos conocidos
2. Construir función `generate_consequence_tree(market_text, category, prob_change)` → API de Claude
3. Construir `identify_midcap_candidates(sector, direction, context)` → segunda llamada al LLM
4. Integrar yfinance para validar liquidez y market cap de cada sugerencia
5. Conectar con el análisis histórico para calcular correlación empírica
6. Integrar al pipeline principal como módulo de señales de segundo nivel

---

## Plan de acción: cómo testeamos todo esto en los datos

### Datos disponibles

| Dataset | Qué tiene | Para qué sirve |
|---------|---------|----------------|
| `data/historical/markets.parquet` (68MB) | 268,706 mercados Oct 2020 - Dic 2025 con volumen total y fecha | Identificar qué mercados existieron y cuándo |
| HuggingFace `quant.parquet` (21GB, streaming) | 170M trades individuales con datetime, price, usd_amount | Reconstruir series de probabilidad diaria + volumen diario por mercado |
| `data/historical/stock_prices/*.parquet` | 57 tickers con precios diarios 2021-2026 | Medir retornos de acciones en ventanas específicas |
| `data/historical/price_series/*.parquet` (79 archivos) | Series de precio recientes del CLOB API | Solo últimos 60 días, para mercados activos |

### Fase 1 — Testear H2 (Slow Build) con datos históricos 2022–2025

**Mercados objetivo** (seleccionar de markets.parquet con criterios):
- Categorías: geopolítica, macro, energía, defensa
- Volumen total > $2M (señal suficientemente líquida)
- Duración > 30 días (para que pueda haber slow build)
- Período: 2024-2025 (datos más confiables)

**Para cada mercado:**
1. Extraer todos sus trades de quant.parquet via streaming
2. Resamplear a probabilidad diaria (precio promedio ponderado por volumen)
3. Detectar períodos con ≥10 días consecutivos de subida + cambio ≥15pp
4. Medir retorno del stock asociado en ventanas: +7d, +14d, +30d desde el inicio del slow build
5. Acumular en tabla: mercado, ticker, inicio del build, magnitud, retorno posterior

**¿Cómo sabremos si funcionó?**
- H2 se confirma si: promedio retorno +7d > 0%, estadísticamente significativo (t-test, p < 0.05)
- H2 se refuta si: retorno no distinguible de 0% o aleatorio
- Distinguir por época (2022-23 vs 2024 vs 2025) para ver si la señal se degrada con el tiempo

### Fase 2 — Testear Capa 3 (Mid cap vs Large cap delay)

**Para cada señal H1 o H2 que encontremos:**
1. Medir retorno del large cap "obvio" (primer activo que reacciona)
2. Medir retorno de mid caps relacionadas (construir lista manualmente)
3. Calcular: ¿cuántos días después del movimiento del large cap empieza a moverse el mid cap?
4. Si el delay es consistente en múltiples eventos → señal tradeable

### Fase 3 — Construir árbol de consecuencias (Capa 4)

Para los 5 eventos históricos más grandes (por volumen Polymarket):
1. Ucrania (Feb 2022)
2. Elecciones EEUU 2022 (medio término)
3. Ciclo Fed 2023-2024
4. Conflicto Iran/Israel 2024
5. Elecciones EEUU 2024 (Trump)

Por cada evento:
- Documentar árbol primario → secundario → terciario
- Medir en datos si los activos terciarios se movieron y con qué delay
- Si hay patrón consistente → plantilla para eventos futuros

---

## Resultados empíricos confirmados (22 Feb 2026)

**Dataset**: 813 mercados descargados de HuggingFace quant.parquet, 618 con datos suficientes para análisis.
**Pipeline acumulativo**: `data/historical/correlation_db.parquet` — 273,072 filas, 618 mercados × 90 tickers × 5 lags.

### Scorecard de las 4 Capas

| Capa | Veredicto | Estadística | Notas |
|------|-----------|-------------|-------|
| **Capa 1 Slow Build** | ✅ CONFIRMADA | +0.56% 7d, **t=9.13, p<0.0001** | N=13,632 señales en 278 mercados |
| **Capa 2 Niche** | ⚠️ PARCIAL | Correlaciones brutas detectadas, falta beta-adjust por categoría | Pipeline acumulativo construido |
| **Capa 3 Mid cap delay** | ❌ NO CONFIRMADA | Necesita datos intradía (hourly) — no visible a granularidad diaria | |
| **Capa 4 Terciarios** | ⚠️ DÉBIL | Lag promedio +2.6 días (N=2 eventos). Ukraine fertilizantes: case study válido | |

---

### Capa 1 — Resultados detallados

**Definición de señal**: probabilidad YES sube ≥5 días consecutivos con cambio total ≥8pp.

**Por categoría** (mínimo 10 señales):

| Categoría | N señales | Retorno 7d | % Positivo | p-value |
|-----------|-----------|-----------|------------|---------|
| Geopolítica | 2,760 | **+0.93%** | 55% | <0.0001 |
| Macro | 4,104 | **+0.85%** | 56% | <0.0001 |
| US Politics | 2,064 | **+0.68%** | 51% | 0.0008 |
| Commodities | 660 | **+0.78%** | 55% | 0.0001 |
| Corporate | 2,040 | +0.23% | 53% | 0.055 |
| AI | 1,464 | **-0.60%** | 50% | <0.0001 — **CONTRARIA** |

**Por ticker** (señal posterior al slow build):

| Ticker | Qué es | Retorno 7d | Win rate | p-value |
|--------|--------|-----------|----------|---------|
| **COIN** | Coinbase (crypto) | **+3.41%** | 53% | <0.0001 |
| **ITA** | ETF defensa/aero | **+0.91%** | **61%** | <0.0001 |
| **GLD** | ETF oro físico | **+0.64%** | **62%** | <0.0001 |
| **EWG** | ETF acciones alemanas | **+0.53%** | 57% | <0.0001 |
| **BA** | Boeing | **+0.66%** | 54% | <0.0001 |
| LMT | Lockheed | +0.28% | 56% | 0.006 |
| TLT | Bonos del Tesoro | -0.07% | 47% | 0.19 — no significativo |
| DJT | Trump Media | +0.09% | 44% | 0.84 — ruido |

**La señal se mantiene en todas las épocas:**

| Época | N | Retorno 7d | p-value |
|-------|---|-----------|---------|
| 2022-2023 | 648 | +1.00% | <0.0001 |
| 2024 | 3,540 | +0.82% | <0.0001 |
| 2025 | 9,444 | +0.43% | <0.0001 |

El efecto se debilita levemente con el tiempo (HFT comprimiendo parte de la señal) pero **no desaparece**.

---

### Capa 2 — Correlaciones empíricas (top señales significativas)

Tickers con mayor correlación vs mercados Polymarket (p<0.05, N≥50 días, 3+ mercados):

| Categoría | Ticker | N mercados | avg\|r\| | % top-5 |
|-----------|--------|------------|---------|---------|
| Macro | **GOLD** | 11 | 0.318 | 73% |
| US Politics | **MRCY** | 12 | 0.292 | 75% |
| US Politics | **COIN** | 17 | 0.290 | 88% |
| US Politics | **LMT** | 15 | 0.282 | 87% |
| Macro | **NEXT** | 10 | 0.287 | 90% |
| US Politics | **AXON** | 7 | 0.282 | 100% |

**5 tickers que sobreviven tanto 2024 como 2025** (los más durables):
GOLD (minera de oro), COIN (crypto), CACI (IT defensa), DRS (electrónica defensa), BAESY (BAE Systems).

**Hallazgo importante**: los tickers asignados manualmente en el pipeline original (TLT para Fed, DJT para Trump) son débiles o no significativos. Los tickers empíricamente correctos son distintos a los intuitivos.

---

### Señales contrarias descubiertas

- **AI markets son contrarios**: slow build en mercados de AI → stock de AI **baja** 7 días después (-0.60%, p<0.0001). Posible mecanismo: el hype ya está priceado cuando Polymarket lo detecta.
- **TLT no responde al slow build** en mercados de la Fed (p=0.19). La respuesta viene en otros instrumentos (GOLD, NEXT).

---

### Archivos de datos clave

| Archivo | Contenido |
|---------|-----------|
| `data/historical/price_series_historical/` | 813 series de precio diario (parquet por mercado) |
| `data/historical/correlation_db.parquet` | 273,072 correlaciones acumulativas |
| `data/historical/stock_prices/*.parquet` | 90 tickers con precios diarios 2021-2026 |
| `outputs/research/capa1_slow_build_full.csv` | 13,632 señales Capa 1 con retornos por ticker |
| `outputs/research/correlation_summary.csv` | Rankings por categoría |
| `outputs/research/beta_adjusted_correlations.csv` | Correlaciones ajustadas por beta de mercado |
| `scripts/research/correlation_pipeline.py` | Pipeline incremental — correr cuando haya datos nuevos |
| `scripts/research/full_analysis.py` | Análisis estadístico completo |

---

## Señales concretas a detectar (resumen operativo)

### Patrón A — Geopolítica → energía/defensa (slow build)
```
Condición: mercado geopolítico sube ≥10 días seguidos + total ≥20pp + volumen >$5M
Activos primarios: XLE (energía), LMT/RTX (defensa), GLD (oro)
Activos mid cap: KTOS (drones), AXON, empresas de ciberseguridad chicas
Señal: comprar mid cap cuando la probabilidad lleva 7+ días subiendo
```

### Patrón B — Política monetaria → sensibles a tasas (slow build)
```
Condición: mercado Fed sube ≥14 días + probabilidad de recorte supera 50%
Activos primarios: TLT (bonos largos)
Activos mid cap: REITs regionales, utilities pequeñas, empresas con mucha deuda
Señal: comprar cuando Polymarket da >50% de probabilidad de recorte
```

### Patrón C — Elecciones → sectores temáticos (slow build)
```
Condición: candidato X sube ≥15pp en 2 semanas en mercado electoral
Activos: sector favorecido por políticas de ese candidato
Señal: el candidato "pro-energía" sube → XLE; "pro-defensa" → LMT; etc.
```

### Patrón D — Regulación específica → empresa afectada (spike)
```
Condición: mercado de decisión regulatoria spike ≥20pp en 48h
Activos: empresa directamente afectada + sus competidores inmediatos
Señal: el spike en Polymarket precede el movimiento de la empresa en ≥1 día
```

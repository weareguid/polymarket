# Polymarket Agent — Prompt de Corrida Semanal

> Cuando Santiago diga **"corre el pipeline de Polymarket"** (o similar), ejecutá este protocolo completo.

---

## Contexto del Proyecto

**Ubicación:** `/Users/santiagobattezzati/repos/Polymarket/`
**Python:** `/Users/santiagobattezzati/.pyenv/versions/3.11.12/bin/python3`
**Objetivo:** Leer newsletters financieros del Gmail del proyecto, analizarlos con inteligencia, cruzarlos con Polymarket, y generar un dashboard HTML que se abre en Chrome.

---

## Paso 1 — Verificar emails nuevos (deduplicación)

Antes de analizar nada, leer el archivo de UIDs ya procesados:

```python
import json
from pathlib import Path

UIDS_FILE = Path("/Users/santiagobattezzati/repos/Polymarket/data/finsignal/processed_uids.json")
processed = set(json.loads(UIDS_FILE.read_text()).get("processed_uids", []))
```

Luego conectarse a Gmail y filtrar solo los emails NO procesados:

```python
# Al iterar emails:
uid_str = uid.decode()
if uid_str in processed:
    print(f"  [SKIP] UID {uid_str} ya procesado en corrida anterior")
    continue
# Si es nuevo → analizar
```

Al terminar la corrida, guardar los nuevos UIDs analizados:

```python
processed.update(nuevos_uids_analizados)
UIDS_FILE.write_text(json.dumps({"processed_uids": sorted(processed)}, indent=2))
```

**Archivo de tracking:** `data/finsignal/processed_uids.json`
Si el archivo no existe o está vacío, procesar todos los emails disponibles (primera corrida).

---

## Paso 2 — Leer los emails de Gmail

Conectarse a Gmail via IMAP y traer los emails de los últimos 7 días:

```python
import imaplib, email, re
from email.header import decode_header

ADDR = "projectpolymarket@gmail.com"
PASS = "fcgh ptso jpls hdji"  # Gmail App Password (actualizado Feb 2026 — leer del .env si falla)
```

**Cómo extraer el cuerpo limpio:**
```python
def extract_body(msg):
    plain, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            payload = part.get_payload(decode=True)
            if not payload: continue
            text = payload.decode("utf-8", errors="replace")
            if part.get_content_type() == "text/plain": plain += text
            elif part.get_content_type() == "text/html": html += text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            text = payload.decode("utf-8", errors="replace")
            if msg.get_content_type() == "text/plain": plain = text
            else: html = text
    if plain: return plain
    return re.sub(r"<[^>]+>", " ", html)
```

**Limpiar el texto para lectura:**
```python
body_clean = re.sub(r'<https?://[^>]+>', '', body)
body_clean = re.sub(r'https?://\S+', '', body_clean)
body_clean = re.sub(r'\[image:[^\]]+\]', '', body_clean)
body_clean = re.sub(r'[ \t]+', ' ', re.sub(r'\n{3,}', '\n\n', body_clean)).strip()
```

**IMPORTANTE — Filtros de emails:**

1. **Ignorar `google`**: Emails de `google` o `google.com` son alertas de seguridad, skip.

2. **Patrón de emails financieros — "Fwd:"**: Casi todos los newsletters financieros llegan como reenvíos de Rodrigo García Reséndiz. El asunto casi siempre empieza con `Fwd:`. Esto es una señal fuerte de que el email es financiero. Ejemplos:
   - `Fwd: ☕ Overturned` → Morning Brew
   - `Fwd: 🍻 Keeping up with the Mag 7` → Brew Markets
   - `Fwd: The Bitcoin Bottom: Why It's Falling and When to Buy` → The Pomp Letter
   - `Fwd: 4 Stocks to Buy Before Their Big Discounts Disappear | Morningstar`

3. **Emails sin "Fwd:" también pueden ser financieros**: Algunos llegan directamente (ej: Seeking Alpha, LPL Financial). No descartar por falta del prefijo.

4. **Emails con cuerpo vacío o solo firma**: Si el cuerpo es solo `-- Rodrigo` o similar → skip, no hay contenido analizable.

5. **Fuentes conocidas de newsletters**: Morning Brew, Brew Markets, The Pomp Letter, Seeking Alpha, Morningstar, LPL Financial.

---

## Paso 2 — Analizar los emails CON TU PROPIA INTELIGENCIA

Leer el contenido de cada email y extraer señales financieras. NO usar regex ni parsers — usar comprensión real del texto.

**Para cada email, identificar:**
- ¿Qué tickers/empresas se mencionan? (incluir nombres de empresa aunque no tenga ticker explícito)
- ¿Cuál es el sentimiento? → BUY / SELL / HOLD / WATCH
- ¿Por qué? → contexto en una frase
- ¿Qué confianza tenés? (0.0 a 1.0)

**Ejemplos de señales a detectar:**
- "UnitedHealth plummeted 19.72%" → UNH SELL 0.91
- "Amazon got a boost after tariffs struck down" → AMZN BUY 0.82
- "Goldman raises price target to $1000" → BUY alta confianza
- "consider trimming your position" → SELL moderada confianza
- "Mag 7" → expandir a AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA

**Contexto importante del mercado actual:**
- Tarifas de Trump: en disputa legal (Suprema Corte las anuló en Feb 2026, Trump impuso nuevas)
- DeepSeek shock (27 Ene 2026): afectó a toda la cadena de chips AI
- Medicare Advantage rates planas 2027: malo para HUM, UNH, CVS, ELV

---

## Paso 3 — Guardar el JSON de señales

Guardar en `/Users/santiagobattezzati/repos/Polymarket/data/finsignal/signals_latest.json`:

```json
{
  "collected_at": "YYYY-MM-DDTHH:MM:SS",
  "emails_processed": N,
  "tickers_found": N,
  "mode": "live_claude_analysis",
  "signals": [
    {
      "ticker": "AMZN",
      "direction": "BUY",
      "confidence": 0.82,
      "context": "Frase explicando por qué",
      "source": "Nombre del newsletter — fecha",
      "date": "YYYY-MM-DD",
      "polymarket_matches": [],
      "has_pm_signal": false,
      "pm_confirms": false
    }
  ]
}
```

---

## Ciclo de vida de señales — Diseño (documentado Feb 2026)

### El problema
Con cada corrida se acumulan señales. Sin control de antigüedad, el dashboard se llena de ruido:
señales de hace 3 meses mezcladas con señales frescas de hoy.

### Taxonomía de señales por tipo de vigencia

| Tipo | Ejemplo | TTL sugerido |
|------|---------|-------------|
| **Event-driven** | "SCOTUS anuló tarifas → AMZN BUY" | 7–14 días |
| **Structural/sector** | "Medicare rates planas → UNH SELL" | 60–90 días |
| **Macro/tendencia** | "Gold safe haven por tarifas" | 30–60 días |
| **Earnings/reacción puntual** | "Corning +15% por deal con Meta" | 14–30 días |

### Estrategia de acumulación — DECISIONES DE DISEÑO (Feb 2026)

**Regla 1 — NO deduplicar por ticker**: Si el mismo ticker aparece en múltiples emails,
conservar TODAS las menciones. La repetición entre newsletters distintos es una señal de
convergencia — indica que el tema está siendo cubierto por múltiples fuentes al mismo tiempo.
El dashboard muestra un badge `×N` cuando un ticker aparece N veces.

**Regla 2 — MERGE al escribir el JSON**: Al terminar cada corrida, NO reemplazar
`signals_latest.json` con solo las señales nuevas. En cambio, leer el JSON existente y
agregar las señales nuevas al array. Así el historial se acumula y es siempre visible.

```python
# Patrón correcto al guardar:
existing = json.loads(SIGNALS_FILE.read_text()).get("signals", []) if SIGNALS_FILE.exists() else []
all_signals = existing + new_signals_this_run
json.dump({"collected_at": now, "emails_processed": N, "signals": all_signals}, ...)
```

**Regla 3 — El dashboard separa activas vs históricas** (YA IMPLEMENTADO):
- **Activas** (≤30 días): tabla visible al abrir el dashboard
- **Históricas** (>30 días): sección colapsable con `<details>`, clic para expandir
- Colores por antigüedad: 🟢 ≤7 días · 🟠 8–30 días · 🔴 >30 días

**Regla 4 — Convergencia** (YA IMPLEMENTADO en dashboard):
Tickers mencionados por múltiples fuentes muestran badge `×N` en morado.
Un ticker que aparece en Morning Brew Y en Pomp Letter en la misma semana es más relevante
que uno que solo aparece una vez.

### Estado actual (Feb 2026)
- ✅ Color de antigüedad implementado
- ✅ Sección históricas colapsable implementada
- ✅ Badge de convergencia (×N) implementado
- ⏳ Merge al escribir JSON: pendiente (actualmente se reemplaza el JSON en cada corrida)

---

## Paso 4 — Correr el dashboard completo

```bash
cd /Users/santiagobattezzati/repos/Polymarket
/Users/santiagobattezzati/.pyenv/versions/3.11.12/bin/python3 generate_dashboard.py
```

Este comando:
1. Descarga los 100 mercados más activos de Polymarket
2. Detecta señales de momentum y volumen
3. Cruza con el `signals_latest.json` que escribiste en el Paso 3
4. Genera el HTML y lo abre en Chrome automáticamente

---

## Paso 5 — Reportar al usuario

Al terminar, decirle a Santiago:
- Cuántos emails procesaste
- Las señales más importantes encontradas (BUY/SELL con confianza alta)
- Si alguna señal de newsletter es confirmada por Polymarket (🟢)
- Cualquier novedad macroeconómica relevante que hayas visto en los emails

---

## Estructura de archivos clave

```
Polymarket/
├── generate_dashboard.py        # Pipeline completo → HTML
├── scripts/
│   ├── run_dashboard_chrome.sh  # Cron script (lunes-viernes 9am)
│   └── finsignal_collect.py     # Pipeline FinSignal (legacy parser)
├── data/
│   ├── finsignal/
│   │   ├── signals_latest.json   # ← VOS escribís acá en Paso 3
│   │   └── processed_uids.json   # ← tracking de emails ya analizados
│   └── processed/
│       └── dashboard_YYYY-MM-DD.html
├── .env                         # Credenciales (NO commitear)
└── AGENT_PROMPT.md              # Este archivo
```

---

## Cron configurado

```
0 9 * * 1-5  →  run_dashboard_chrome.sh
```
Corre lunes a viernes a las 9am. Abre el dashboard en Chrome automáticamente.
El pipeline de FinSignal (Gmail → análisis → Polymarket) se hace manualmente una vez por semana con Santiago.

---

## Frase de activación

Santiago puede decir cualquiera de estas frases para activar este protocolo:
- *"corre el pipeline de Polymarket"*
- *"revisemos los emails de Polymarket"*
- *"análisis semanal de Polymarket"*
- *"qué dicen los newsletters esta semana"*

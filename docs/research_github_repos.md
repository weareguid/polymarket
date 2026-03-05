# Polymarket — Investigación de Repos Existentes en GitHub
> Generado: 2026-02-20

## Resumen ejecutivo
El ecosistema de Polymarket en GitHub es enorme (94 repos oficiales + cientos de la comunidad).
Lo que SÍ está resuelto: trading bots, whale tracking, arbitraje, dashboards.
Lo que NO está bien resuelto: **correlación Polymarket → stocks/ETFs**, **parsing de newsletters financieras**, **portfolio tracking personal**.

---

## Repos más relevantes para nuestro proyecto

### Datos e infraestructura
| Repo | Qué hace | Interés |
|------|----------|---------|
| [Polymarket/py-clob-client](https://github.com/Polymarket/py-clob-client) | SDK Python oficial para CLOB API | ⭐ Reemplazar nuestro requests manual |
| [Polymarket/agents](https://github.com/Polymarket/agents) | Framework para agentes autónomos que tradean | ⭐ Referencia de arquitectura |
| [warproxxx/poly_data](https://github.com/warproxxx/poly_data) | Pipeline de data: markets + trades + order events | ⭐ Para recolección histórica |
| [Jon-Becker/prediction-market-analysis](https://github.com/Jon-Becker/prediction-market-analysis) | 36GB de datos históricos Polymarket + Kalshi | ⭐⭐ Dataset histórico GRATIS |
| [pmxt-dev/pmxt](https://github.com/pmxt-dev/pmxt) | "CCXT de prediction markets" — API unificada Polymarket + Kalshi | ⭐ Si quisiéramos agregar Kalshi |

### Signal detection
| Repo | Qué hace | Interés |
|------|----------|---------|
| [NavnoorBawa/polymarket-prediction-system](https://github.com/NavnoorBawa/polymarket-prediction-system) | ML con XGBoost/LightGBM, RSI, order book imbalance | ⭐ Ideas para scoring |
| [Trust412/Polymarket-spike-bot-v1](https://github.com/Trust412/Polymarket-spike-bot-v1) | Spike detection en real-time (≥1.5 score jump) | ⭐ Referencia para nuestro detector |
| [yorkeccak/Polyseer](https://github.com/yorkeccak/Polyseer) | Multi-agent con Bayesian probability | Inspiración |

### Trading bots
| Repo | Qué hace | Interés |
|------|----------|---------|
| [ent0n29/polybot](https://github.com/ent0n29/polybot) | Reverse-engineer estrategias, backtesting | Referencia |
| [Trust412/polymarket-copy-trading-bot-version-3](https://github.com/Trust412/polymarket-copy-trading-bot-version-3) | Copia trades de wallets target en real-time | Futuro |

### MCP Server (muy relevante)
| Repo | Qué hace | Interés |
|------|----------|---------|
| [caiovicentino/polymarket-mcp-server](https://github.com/caiovicentino/polymarket-mcp-server) | **45 tools** para Claude: análisis, trading, portfolio, WebSocket | ⭐⭐ REVISAR — podría reemplazar parte de nuestro stack |

### Frameworks completos
| Repo | Qué hace | Interés |
|------|----------|---------|
| [PredictionXBT/PredictOS](https://github.com/PredictionXBT/PredictOS) | All-in-one: análisis, bots, wallet tracking, multi-agent | Referencia |

### Curated lists
- [aarora4/Awesome-Prediction-Market-Tools](https://github.com/aarora4/Awesome-Prediction-Market-Tools) — 100+ tools
- [0xperp/awesome-prediction-markets](https://github.com/0xperp/awesome-prediction-markets)

---

## Gaps que NADIE resolvió bien (nuestra ventaja)

1. **Correlación Polymarket → Stocks/ETFs** — nadie lo hace sistemáticamente. Nosotros sí.
2. **Newsletter parsing pipeline** — existe análisis de sentimiento de noticias pero no parsear newsletters específicas
3. **Trade tracker personal** — hay portfolio tracking para wallets cripto, no para acciones tradicionales
4. **Second-order correlations** — los efectos de segundo orden (competidores, supply chain) no están en ningún repo

---

## Acción recomendada: revisar `caiovicentino/polymarket-mcp-server`

Tiene 45 tools que se integran con Claude como MCP. Podría ser interesante para la fase 2 del proyecto cuando queramos automatizar más. Por ahora nuestra arquitectura Python es más flexible para el objetivo de correlación con stocks.

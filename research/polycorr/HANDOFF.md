# PolyCorr — Handoff

> **Última actualización:** 2026-02-22
> **Estado:** Análisis histórico completado. Resultados empíricos confirmados.

---

## Leer primero

**Todo el contexto, hipótesis y resultados empíricos están en:**
`research/polycorr/HYPOTHESIS_FRAMEWORK.md`

---

## Estado rápido (22 Feb 2026)

- **813 mercados** descargados de HuggingFace `quant.parquet`
- **Capa 1 (Slow Build) CONFIRMADA**: +0.56% 7d retorno, p<0.0001 sobre 13,632 señales
- **Pipeline acumulativo** construido: `scripts/research/correlation_pipeline.py`
- **Descarga pausada** — reanudar con `scripts/research/09_extract_historical_series_v7.py` cuando sea necesario

## Próximos pasos cuando se retome

1. **Actualizar knowledge base del pipeline de producción** con tickers empíricos:
   - ITA y GLD como señales de slow build (61-62% win rate)
   - COIN para política americana
   - Eliminar TLT y DJT como señales primarias (no son significativos)

2. **Testear Capa 3 con datos intradía** — yfinance `interval='1h'` — el delay mid cap/large cap es intradiario, no visible en OHLC diario

3. **Construir árbol de consecuencias con LLM** para validar Capa 4 con más de N=2 eventos

4. **Integrar al pipeline de producción**: cuando `trending_detector.py` detecta un slow build, lookear `correlation_db.parquet` para señal empírica por categoría

5. **Reanudar descarga si se necesita más data**: mismo patrón que scripts anteriores (`volume_total >= 25_000`, categorías faltantes)

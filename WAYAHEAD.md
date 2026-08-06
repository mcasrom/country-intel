# WAYAHEAD — Country Intelligence OSINT

**Objetivo**: dashboards de inteligencia geopolitica por pais (datos abiertos + IA). Microservicio ligero del ecosistema viajeinteligencia.
**Stack**: FastAPI + SQLite + cron + JSON estatico + PWA. **Live**: (pendiente nginx/cloudflare).
**Server**: deploy@178.105.80.193 — PM2 `country-intel-api` (puerto 8710, pendiente).

## Estado (06-Ago-2026)
- **Scaffold Opción A**: FastAPI /health + /api/country, core (CachedClient + BaseCollector), colector World Bank (poblacion/PIB/inflacion), pipeline a JSON, frontend minimo PWA. **Sin desplegar aun** (se mide impacto RAM/swap).
- Reutilizable: patrón eclipse/nearme. `src/core/` = embrión vi-core.

## Backlog
- [ ] Medir impacto RAM/swap/disco y desplegar (PM2 + nginx + CF).
- [ ] Resumen IA por país (Gemini/DeepSeek, 1/día).
- [ ] Alertas (FIRMS, EMSC, ReliefWeb) por país.
- [ ] Timeline + mapa + Chart.js.
- [ ] 10 → 50 → 200 países.
- [ ] Comparador + informes PDF + API pública (PRO).

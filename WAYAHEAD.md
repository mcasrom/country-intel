# WAYAHEAD — Country Intelligence OSINT

**Objetivo**: dashboards de inteligencia geopolitica por pais (datos abiertos). Microservicio ligero del ecosistema viajeinteligencia.
**Stack**: FastAPI + SQLite + cron + JSON estatico + PWA. **Live**: https://country.viajeinteligencia.com
**Server**: deploy@178.105.80.193 — PM2 `country-intel-api` (puerto 8710, ~46MB RAM, <2% CPU).

## Estado (08-Ago-2026)
- **Desplegado en produccion** (nginx + Cloudflare, PM2 online, `/api/health` 200). **217 paises** con JSON estatico por pais servido directo (SEO excelente).
- **v0.8.0**: cobertura WB (region 217, moneda/IDH 188 via enrich.json, urbanizacion/fertilidad 217, internet 184, pib_ppa 197, gasto_educacion 134, gini 70). `sleep_worldbank=8s` evita throttling.
- **Tendencias de busqueda**: nombre real del pais desde `geo.json` (fallback a los 15 curados), chips 🔍 a buscador (Google/Bing/Startpage), copiar prompt, ranking de fichas abiertas.
- **SEO completo**: 217 paginas `/pais/{code}` con indicadores reales + title unico + JSON-LD Country + canonical + hreflang es. `sitemap.xml` (218 urls) + `robots.txt`.
- **Tema claro/oscuro** (body.light + localStorage + boton 🌙/☀️). Fix contraste comparador en tema claro.
- **Rate-limit anti-bots**: 60 req/min por IP en `/api/country`, `/api/news`, `/api/trending` (en memoria, respeta X-Forwarded-For). Googlebot indexa las paginas `/pais` sin limitar (no estan rate-limited).

## Hito reciente (08-Ago-2026) — SEO 217 paises + proteccion de recursos (commit `6dae21c`)
- **217 paginas `/pais/{code}`** (antes solo 15 curados): nombre real via `geo.json`, indicadores reales del JSON estatico (poblacion, PIB, IDH, inflacion, desempleo, internet, esperanza de vida, urbanizacion, moneda), title unico por pais, JSON-LD Country con poblacion/continente, canonical + hreflang es.
- **Sitemap 218 urls** (antes 16) — todos los paises indexables.
- **Rate-limit anti-bots** 60 req/min/IP en las APIs de datos (protege CPU de los ~4.240 bots/scrapers que martilleaban /api/country). Verificado: rafaga de 70 → 55 OK + 15 x 429.
- **Coste de recursos: ~0** (datos ya en disco, se generan en el request). RAM bajo de 52.6 → 45.9MB.
- Verificado en produccion: `/pais/{ar,es,pe,jp,br}` 200 con Googlebot UA, sitemap XML valido, robots OK.

## Backlog
- [ ] Resumen IA por país (LLM 1/día) + monitor uptime-kuma sobre `/api/health` (frescura).
- [ ] Alertas (FIRMS, EMSC, ReliefWeb) por país.
- [ ] Timeline + mapa + Chart.js.
- [ ] Comparador + informes PDF + API publica (PRO).
- [ ] Enviar sitemap a Google Search Console.
- [ ] Cobertura: co₂ pc y esperanza vida saludable siguen 0 (escasos/throttle, reintenta el cron).

## Fix — Rate-limit rompía comparador/popups (8 Ago 2026)

- **Síntoma**: tras añadir el rate-limit anti-bots, el **comparador y el heatmap no mostraban datos**, y los **popups del mapa** (ej. Italia) salían "Población: — PIB: — Renta pc: —".
- **Causa raíz**: el frontend carga los **217 países en ráfaga** (`load()` y `ensureAll()` hacen `fetch('/api/country/{cc}')` en paralelo). El rate-limit a **60 req/min** (luego 500) cortaba la ráfaga → peticiones 61+ devolvían **429** → `ALL` incompleto → comparador/heatmap/popups sin datos. Además, Cloudflare agrupa a todos los usuarios tras pocas IPs, así que varios visitantes comparten cuota y agotan el límite.
- **Fix**: **3000 req/min por IP** en `/api/country`, `/api/news`, `/api/trending`. Suficiente para frenar a un bot martilleando en bucle (los ~4.240 bots hacían cientos de miles en 15 días, no miles por minuto) pero SIEMPRE deja pasar la carga legítima (217 países × N usuarios).
- **Verificado**: 2 cargas completas seguidas (434 requests) → 0 errores. Italia: población 59.0M · PIB 2.38T · renta $40.430. Commit `cf6bbf9`.

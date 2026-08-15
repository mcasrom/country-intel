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
## Sprint SEO — Country: posicionamiento para usuarios reales (10 Ago 2026)

- **Objetivo**: atacar el problema de cero usuarios con SEO + distribución (plan 30 días, prioridad: Country por tener 219 URLs ya indexables).
- **Copy sin "OSINT"**: títulos de home y de las 217 fichas país pasan de "Country Intelligence OSINT" a "Datos e indicadores de X | Viaje Inteligencia" (público masivo, no técnico).
- **3 artículos comparativos SEO** (con datos reales del Banco Mundial):
  - `/comparativa-espana-marruecos-portugal` — población, PIB, IDH, inflación de los 3.
  - `/top-10-paises-mas-seguros-2026` — ranking por tasa de homicidios (Singapur 0.07 → Italia 0.57).
  - `/paises-mas-baratos-viajar-2026` — renta per cápita (Burundi 216$ → Liechtenstein 220k$).
- **Sitemap**: 219 → 222 URLs (3 posts añadidos). IndexNow enviado (HTTP 202).
- **Verificado**: home 200, fichas 200 sin OSINT, posts 200 en URLs limpias, vacaciones intacto, resto del ecosistema intacto.
- **Commit**: `7f3f321`. Coste ~0.

## Sprint — Fichas país: +9 IDH PNUD + snippet SEO + nota territorios (11 Ago 2026)

- **Problema**: 29 países/territorios mostraban "IDH n/d, inflación n/d, internet n/d, moneda n/d" en Google (site:country.viajeinteligencia.com), quedando las fichas pobres.
- **Fix 1 — +9 IDH reales del PNUD (HDR 2022)** en enrich.json: Mónaco 0.956, Hong Kong 0.956, Liechtenstein 0.942, Andorra 0.884, Antigua 0.826, Sint Maarten 0.812, Kosovo 0.762, Dominica 0.740, Palestina 0.716. Los 19 territorios dependientes (French Polynesia, Guam...) no tienen IDH del PNUD — no se inventan.
- **Fix 2 — description SEO reordenada**: ahora pone PRIMERO los datos disponibles (población, PIB, desempleo, esperanza de vida, urbanización) y al final la nota "Datos de IDH, internet, moneda no publicados por los organismos para territorios dependientes" → mejor snippet en Google.
- **Fix 3 — nota visible en la ficha** para los que tienen n/d.
- **Verificado**: 9 fichas con IDH real, French Polynesia con snippet mejorado, ecosistema intacto.
- **Commit**: `fc2780f`. Coste ~0.


## Sprint — Semáforo coste de vida (13 Ago 2026) — commit `a80fcc2`

- **Feature**: nuevo indicador `coste_vida` (price level relativo a EE.UU., US=1) + semáforo 🟢/🟡/🟠/🔴 en `/vacaciones` y en todas las fichas `/pais/{code}`.
- **Fuente real**: `PA.NUS.PPPC.RF` del Banco Mundial está **archivado** (API: "indicator not found") → se usó el equivalente de **Our World in Data** (`gdp-price-levels-relative-to-the-us`, datos WB rebasados a US=1). CSV fuente en `data/static/price_level_owid.csv`; refresco con `scripts/refresh_coste_vida.py`.
- **Umbrales** (los pedidos): <0.5 🟢 Muy barato · 0.5–0.8 🟡 Moderado · 0.8–1.1 🟠 Similar a España · >1.1 🔴 Caro.
- **Datos reales (2024)**: India 0.24 🟢 · México 0.54 🟡 · Portugal 0.56 🟡 · España 0.61 🟡 · Japón 0.62 🟡 · EE.UU. 1.0 🟠 · Suiza 1.08 🟠. (Las cifras "de memoria" iniciales estaban desviadas; la fuente oficial manda.)
- **Cobertura**: 202 países (203 con dato en el CSV).
- **Incidente reparado**: el venv de country-intel estaba corrupto (sin `bin/`, fastapi/uvicorn incompletos) → el API quedó en 502 al reiniciar. Reconstruido desde cero (`python3 -m venv venv` + `venv/bin/pip install -r requirements.txt`). API online, `/api/health` 200, RAM ~46MB.
- **Verificado**: `/api/country/es` → coste_vida 0.608414, `/vacaciones` (JS válido), `/pais/es` → "🟡 Moderado (0.6)". Diff de datos puramente aditivo (6 líneas por país).
- **Commit**: `a80fcc2`. Coste ~0.

## Backlog pendiente (sin cambios)
- Resumen IA por país (LLM 1/día) + monitor uptime-kuma sobre `/api/health`.
- Alertas (FIRMS, EMSC, ReliefWeb) por país.
- Timeline + mapa + Chart.js.
- Comparador + informes PDF + API pública (PRO).
- Enviar sitemap a Google Search Console.

## Fix coste_vida desaparecía (14/Ago)
- **Problema**: el semáforo de coste de vida salía "—". La inyección inicial solo tocaba
  data/json, y el pipeline nocturno (03:00) regenera esos JSON desde la BD → lo borraba.
- **Fix robusto**: `coste_vida` integrado como indicador ESTÁTICO oficial (OWID/WB):
  `scripts/import_static.py` genera `data/static/coste_vida.csv` + `sources.json`;
  `static_official.py` lo emite (202 países). El pipeline diario ya lo incluye SIEMPRE.
- Verificado: /api/country/* devuelve coste_vida, /vacaciones muestra el semáforo.

## Salvaguarda coste_vida (14/Ago)
- `scripts/check_coste_vida.py` + cron 03:35 UTC (tras pipeline 03:00): verifica cobertura
  de coste_vida en los JSON y alerta si cae. Baseline esperado: ~6% países sin dato
  (cobertura OWID 202/217); si el fallo volviera (pipeline borrando el indicador) subiría
  a ~100% y saltaría la alerta.

## Botones de compartir en /vacaciones (15/Ago)
- WhatsApp/Telegram/X con mensaje dinámico según países comparados + mejor valor
  (renta/IDH/coste de vida) + enlace. frontend/vacaciones.html.

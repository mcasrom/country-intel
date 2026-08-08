# Country Intelligence OSINT

Dashboards de inteligencia geopolitica por pais, con datos abiertos. Microservicio
ligero del ecosistema viajeinteligencia.com.

**Live**: https://country.viajeinteligencia.com · **Repo**: github.com/mcasrom/country-intel

## Estado

- **217 paises** con ficha completa (indicadores World Bank + moneda/IDH estaticos).
- Desplegado en produccion (nginx + Cloudflare, PM2 `country-intel-api` :8710).
- v0.8.0 en el pie. Tema claro/oscuro, comparador, tendencias de busqueda.

## Stack (ligero)

- Python + FastAPI
- SQLite (persistencia del colector) + JSON estatico por pais (SEO excelente)
- Cron 03:00 (pipeline nocturno, `sleep_worldbank=8s` anti-throttling)
- Frontend PWA estatica

## Endpoints

| Endpoint | Funcion |
|---|---|
| `/api/health` | Salud + frescura de datos |
| `/api/country/{cc}` | Ficha del pais (JSON estatico) |
| `/api/countries` | Listado de codigos |
| `/api/travel/{cc}` | Avisos de viaje FCDO (cache 24h) |
| `/api/news/{cc}` | Noticias GDELT/Google News (cache 1h) |
| `/api/trending/{cc}` · `/api/trending/all` | Tendencias de busqueda Google (cache 6h) |
| `/api/trends` · `/api/trends/view/{cc}` | Conteo anonimo de fichas abiertas |
| `/pais/{cc}` | Pagina SEO estatica por pais (217) |
| `/sitemap.xml` · `/robots.txt` | SEO |

## SEO

- **217 paginas `/pais/{code}`** con indicadores reales, title unico, JSON-LD
  `Country`, canonical + hreflang es.
- **Sitemap** con las 218 URLs + robots.txt.

## Proteccion de recursos

- **Rate-limit** 60 req/min por IP en `/api/country`, `/api/news`, `/api/trending`
  (en memoria, sin dependencias, respeta `X-Forwarded-For`). Las paginas `/pais`
  (Googlebot) no estan limitadas.

## Despliegue

```bash
venv/bin/pip install -r requirements.txt
venv/bin/python scripts/pipeline.py      # recolecta y genera JSON
pm2 start ecosystem.config.cjs           # uvicorn :8710
```

## Embrion vi-core

`src/core/` (http.py, collector.py) es el nucleo reutilizable del ecosistema.

## Contacto

- Email: country@viajeinteligencia.com
- Repo: https://github.com/mcasrom/country-intel

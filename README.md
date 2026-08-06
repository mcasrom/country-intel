# Country Intelligence OSINT

Dashboards de inteligencia geopolitica por pais, con datos abiertos y resumen IA diario.

## Stack (Opción A - ligera)

- Python + FastAPI (servidor minimo: /health, /api/country/{cc})
- SQLite (persistencia del colector)
- JSON estatico por pais (servido directo, SEO excelente)
- Cron 03:00 (pipeline nocturno)
- Frontend PWA estatica

## Uso

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python scripts/pipeline.py      # recolecta y genera JSON
venv/bin/uvicorn src.server:app --port 8710
```

## Embrion vi-core

`src/core/` (http.py, collector.py) es el nucleo reutilizable del ecosistema viajeinteligencia.

## Contacto

- Email: country@viajeinteligencia.com (Cloudflare Email Routing)
- Repo: https://github.com/mcasrom/country-intel
- Live: https://country.viajeinteligencia.com

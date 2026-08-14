#!/usr/bin/env python3
"""Vigilancia: verifica que coste_vida está en los JSON por país tras el pipeline
nocturno (03:00). Si falta en >5% de países, alerta. Log en data/coste_vida_health.log.
Cron sugerido: 35 3 * * * (tras el pipeline de las 03:00)."""
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
JSON_DIR = BASE / "data" / "json"
LOG = BASE / "data" / "coste_vida_health.log"

missing = total = 0
for fp in sorted(JSON_DIR.glob("*.json")):
    total += 1
    try:
        d = json.loads(fp.read_text())
        if "coste_vida" not in (d.get("indicators") or {}):
            missing += 1
    except Exception:
        missing += 1

pct = (missing * 100) // max(total, 1)
line = f"{datetime.now(timezone.utc).isoformat()} total={total} sin_coste_vida={missing} ({pct}%)"
with open(LOG, "a", encoding="utf-8") as f:
    f.write(line + "\n")
print(line)
if pct >= 5:
    print(f"ALERTA: coste_vida ausente en {pct}% de los países — revisar import_static/static_official")

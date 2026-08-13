#!/usr/bin/env python3
"""Inyecta SOLO coste_vida (price level relativo a EEUU, fuente OWID=WB) en los
JSON por pais. Puramente aditivo. Guarda el CSV fuente en data/static/."""
import csv
import json
import os
import urllib.request
from datetime import datetime, timezone

BASE = "/home/deploy/country-intel"
JSON_DIR = os.path.join(BASE, "data", "json")
CSV_PATH = os.path.join(BASE, "data", "static", "price_level_owid.csv")
URL = "https://ourworldindata.org/grapher/gdp-price-levels-relative-to-the-us.csv"

os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
if not os.path.exists(CSV_PATH):
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        open(CSV_PATH, "wb").write(r.read())
    print("CSV OWID descargado")

geo = json.loads(open(os.path.join(BASE, "data", "geo.json")).read())
iso3_to_iso2 = {v.get("iso3"): k for k, v in geo.items() if v.get("iso3")}

best = {}
with open(CSV_PATH) as f:
    r = csv.DictReader(f)
    for row in r:
        code = (row.get("Code") or "").strip()
        if not code:
            continue
        y, v = row.get("Year"), row.get("GDP price levels relative to the US")
        if not y or not v:
            continue
        try:
            yi, vf = int(y), float(v)
        except (TypeError, ValueError):
            continue
        cur = best.get(code)
        if cur is None or yi > cur[0]:
            best[code] = (yi, vf)
print(f"paises con dato (ultimo anio): {len(best)}")

now = datetime.now(timezone.utc).isoformat()
added = skipped = 0
for code, (y, v) in best.items():
    iso2 = iso3_to_iso2.get(code)
    if not iso2:
        continue
    fp = os.path.join(JSON_DIR, f"{iso2}.json")
    if not os.path.exists(fp):
        continue
    d = json.loads(open(fp).read())
    ind = d.setdefault("indicators", {})
    if "coste_vida" in ind:
        skipped += 1
        continue
    ind["coste_vida"] = {"value": f"{v:.6f}", "updated": now,
                         "source": "World Bank via OWID", "year": str(y)}
    open(fp, "w").write(json.dumps(d, ensure_ascii=False, indent=1))
    added += 1
print(f"JSON actualizados: {added} (ya existian: {skipped})")

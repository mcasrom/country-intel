"""Backfill sin red: siembra el seed en la BD (solo donde no hay valor WB vivo)
y regenera los JSON. Usa geo.json existente. No toca WB."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import DB_PATH, BASE_DIR
from src.collectors.worldbank import STATIC_SOURCE, WorldBank
from scripts.pipeline import write_json

seed = json.loads((BASE_DIR / "data" / "seed_countries.json").read_text())
geo = json.loads((BASE_DIR / "data" / "geo.json").read_text())

conn = sqlite3.connect(str(DB_PATH))
live = {}
for row in conn.execute("SELECT country, indicator, source FROM indicators"):
    live[(row[0], row[1])] = row[2]

items = []
for cc, inds in seed.items():
    for label, value in inds.items():
        if live.get((cc, label)) == "worldbank":
            continue
        items.append({"country": cc, "indicator": label, "value": value, "source": STATIC_SOURCE.get(label, "seed")})

WorldBank().save(conn, items)
write_json(conn, geo)
conn.close()
print(f"backfill OK: {len(items)} items sembrados | paises: {len(seed)}")

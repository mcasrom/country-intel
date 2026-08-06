"""Pipeline nocturno (cron 03:00): recolectar -> SQLite -> JSON por pais + warmup de busquedas."""
import json
import sqlite3
import sys
import time as _time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DB_PATH, JSON_DIR, DATA_DIR

COLLECTORS = [
    # importar y ejecutar los colectores registrados
    __import__("src.collectors.worldbank", fromlist=["WorldBank"]).WorldBank(),
]


def write_json(conn):
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country FROM indicators")
    for (cc,) in cur.fetchall():
        cur.execute("SELECT indicator, value, updated_at, source FROM indicators WHERE country=?", (cc,))
        rows = cur.fetchall()
        payload = {"country": cc, "generated": __import__("datetime").datetime.now().isoformat(),
                   "indicators": {r[0]: {"value": r[1], "updated": r[2], "source": r[3]} for r in rows}}
        (JSON_DIR / f"{cc}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"[pipeline] JSON escritos: {len(list(JSON_DIR.glob('*.json')))}")


def warmup_trending():
    try:
        from src.server import NAMES, _refresh_trending
        for cc in sorted(NAMES):
            _refresh_trending(cc)
            _time.sleep(0.3)
        print(f"[pipeline] trending warmup: {len(NAMES)} paises")
    except Exception as e:
        print(f"[pipeline] trending warmup fallo: {e}")


def run():
    conn = sqlite3.connect(str(DB_PATH))
    for col in COLLECTORS:
        print(f"[pipeline] {col.name}...")
        items = col.fetch()
        col.save(conn, items)
        print(f"  {len(items)} items")
    write_json(conn)
    conn.close()
    warmup_trending()


if __name__ == "__main__":
    run()

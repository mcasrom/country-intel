"""Pipeline nocturno (cron 03:00): recolectar vivos -> SQLite -> JSON por pais (con geo)
+ warmup de busquedas + last_run + auto-commit de datos."""
import json
import sqlite3
import subprocess
import sys
import time as _time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DB_PATH, JSON_DIR, BASE_DIR

COLLECTORS = [
    __import__("src.collectors.worldbank", fromlist=["WorldBank"]).WorldBank(),
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def write_json(conn, geo):
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country FROM indicators")
    codes = [r[0] for r in cur.fetchall()]
    for cc in codes:
        cur.execute("SELECT indicator, value, updated_at, source FROM indicators WHERE country=?", (cc,))
        rows = cur.fetchall()
        g = geo.get(cc, {})
        payload = {
            "country": cc,
            "generated": _now(),
            "geo": {"name": g.get("name", cc.upper()), "lat": g.get("lat"), "lon": g.get("lon"), "iso2": cc},
            "indicators": {r[0]: {"value": r[1], "updated": r[2], "source": r[3]} for r in rows},
        }
        (JSON_DIR / f"{cc}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    for fp in JSON_DIR.glob("*.json"):
        if fp.stem not in codes:
            fp.unlink()
    print(f"[pipeline] JSON escritos: {len(codes)}")
    return codes


def max_age_days():
    now = datetime.now(timezone.utc)
    mx = 0
    for fp in JSON_DIR.glob("*.json"):
        try:
            d = json.loads(fp.read_text())
            for ind in d.get("indicators", {}).values():
                try:
                    age = (now - datetime.fromisoformat(ind.get("updated", ""))).days
                    if age > mx:
                        mx = age
                except Exception:
                    pass
        except Exception:
            pass
    return mx


def warmup_trending():
    try:
        from src.server import NAMES, _refresh_trending
        for cc in sorted(NAMES):
            _refresh_trending(cc)
            _time.sleep(0.3)
        print(f"[pipeline] trending warmup: {len(NAMES)} paises")
    except Exception as e:
        print(f"[pipeline] trending warmup fallo: {e}")


def auto_commit():
    try:
        subprocess.run(["git", "add", "data/json", "data/geo.json", "data/seed_countries.json", "data/last_run.json"], cwd=str(BASE_DIR), check=False, capture_output=True)
        st = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(BASE_DIR))
        if st.returncode != 0:
            subprocess.run(["git", "commit", "-m", "data: pipeline nocturno", "-q"], cwd=str(BASE_DIR), check=True, capture_output=True)
            subprocess.run(["git", "pull", "--rebase", "origin", "main", "-q"], cwd=str(BASE_DIR), check=False, capture_output=True)
            subprocess.run(["git", "push", "origin", "main", "-q"], cwd=str(BASE_DIR), check=False, capture_output=True)
            print("[pipeline] auto-commit data OK")
        else:
            print("[pipeline] sin cambios de datos")
    except Exception as e:
        print(f"[pipeline] auto-commit fallo: {e}")


def run():
    conn = sqlite3.connect(str(DB_PATH))
    geo = {}
    errors = []
    for col in COLLECTORS:
        print(f"[pipeline] {col.name}...")
        items = col.fetch()
        geo.update(getattr(col, "geo", {}))
        errors.extend(getattr(col, "errors", []))
        col.save(conn, items)
        print(f"  {len(items)} items")
    codes = write_json(conn, geo)
    conn.close()
    last = {"run_at": _now(), "countries": len(codes), "max_age_days": max_age_days(), "errors": errors[:20]}
    (BASE_DIR / "data" / "last_run.json").write_text(json.dumps(last, ensure_ascii=False, indent=1))
    print(f"[pipeline] last_run: {last}")
    warmup_trending()
    auto_commit()


if __name__ == "__main__":
    run()

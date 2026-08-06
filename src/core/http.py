"""Cliente HTTP con cache de disco reutilizable (embrion vi-core)."""
import hashlib
import json
import time
from pathlib import Path

import httpx


class CachedClient:
    """GET con cache en fichero JSON. Evita re-llamar APIs en cada ciclo."""
    def __init__(self, cache_dir: Path, ttl: int = 3600, timeout: float = 30.0):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self.timeout = timeout

    def _key(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest() + ".json"

    def get_json(self, url: str, **kw):
        fp = self.cache_dir / self._key(url)
        if fp.exists():
            try:
                d = json.loads(fp.read_text())
                if time.time() - d.get("ts", 0) < self.ttl:
                    return d["data"]
            except Exception:
                pass
        r = httpx.get(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        data = r.json()
        fp.write_text(json.dumps({"ts": int(time.time()), "data": data}, ensure_ascii=False))
        return data

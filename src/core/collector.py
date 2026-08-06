"""Base de colector OSINT (embrion vi-core)."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class BaseCollector(ABC):
    name = "base"

    @abstractmethod
    def fetch(self):
        """Devuelve lista de items normalizados (dicts)."""

    def stamp(self, item: dict) -> dict:
        item.setdefault("source", self.name)
        item.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
        return item

    def save(self, conn, items: list[dict]):
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS indicators (
                country TEXT, source TEXT, indicator TEXT, value TEXT,
                updated_at TEXT, year TEXT, PRIMARY KEY(country, indicator)
            )""")
        cols = [r[1] for r in cur.execute("PRAGMA table_info(indicators)").fetchall()]
        if "year" not in cols:
            cur.execute("ALTER TABLE indicators ADD COLUMN year TEXT")
        for i in items:
            it = self.stamp(i)
            year = it.get("year", "")
            cur.execute("""
                INSERT INTO indicators (country, source, indicator, value, updated_at, year)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(country, indicator) DO UPDATE SET value=excluded.value,
                    updated_at=excluded.updated_at, source=excluded.source, year=excluded.year""",
                (it["country"], it["source"], it["indicator"], str(it["value"]), it["updated_at"], year))
        conn.commit()

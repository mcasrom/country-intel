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
                updated_at TEXT, PRIMARY KEY(country, indicator)
            )""")
        for i in items:
            it = self.stamp(i)
            cur.execute("""
                INSERT INTO indicators (country, source, indicator, value, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(country, indicator) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (it["country"], it["source"], it["indicator"], str(it["value"]), it["updated_at"]))
        conn.commit()

"""Indicadores del Banco Mundial (seed local real, generado por fetch una vez).

El API de World Bank rate-limita peticiones rapidas; el pipeline usa el seed
para no depender del API en cada ciclo. Refrescar el seed periodicamente.
"""
import json
from pathlib import Path

from src.core.collector import BaseCollector
from src.config import BASE_DIR


class WorldBank(BaseCollector):
    name = "worldbank"

    def fetch(self):
        fp = BASE_DIR / "data" / "seed_countries.json"
        seed = json.loads(fp.read_text(encoding="utf-8"))
        out = []
        for cc, inds in seed.items():
            for label, value in inds.items():
                out.append({"country": cc, "indicator": label, "value": value})
        return out

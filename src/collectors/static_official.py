"""Collector estatico oficial: co2_pc (GCP), edad_mediana (UN WPP), corrupcion (TI CPI),
libertad_prensa (RSF), democracia (EIU), titulados (UNESCO UIS). Lee los CSVs
normalizados de data/static/ (generados por scripts/import_static.py) y publica
con fuente primaria para todos los paises. Debe correr DESPUES de worldbank."""
import csv
import json

from src.config import BASE_DIR
from src.core.collector import BaseCollector

STATIC = BASE_DIR / "data" / "static"
DECIMALS = {"co2_pc": 3, "edad_mediana": 1, "corrupcion": 1,
            "libertad_prensa": 1, "democracia": 2, "titulados": 1,
            "coste_vida": 4}


class StaticOfficial(BaseCollector):
    name = "static_official"

    def __init__(self):
        self.geo = {}
        self.errors = []
        self.sources = {}
        try:
            self.sources = json.loads((STATIC / "sources.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    def fetch(self):
        out = []
        for label, meta in self.sources.items():
            fp = STATIC / f"{label}.csv"
            if not fp.exists():
                continue
            src = meta.get("source", label)
            d = DECIMALS.get(label, 2)
            n = 0
            for r in csv.DictReader(fp.open(encoding="utf-8")):
                if not r.get("value"):
                    continue
                try:
                    v = float(r["value"])
                except ValueError:
                    continue
                out.append({"country": r["country"], "indicator": label,
                            "value": f"{v:.{d}f}", "year": r.get("year") or meta.get("year", ""),
                            "source": src})
                n += 1
            print(f"  {label}: {n} paises", flush=True)
        return out

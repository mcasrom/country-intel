"""Collector Banco Mundial VIVO: trae todos los paises por indicador (all-countries),
con retry/backoff y throttle; construye geo (lat/lon) de todos los paises;
fallback al seed de referencia; conserva valores previos si el API falla.
"""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.config import BASE_DIR, CFG
from src.core.collector import BaseCollector

WB = "https://api.worldbank.org/v2/"
INDICATORS = {
    "poblacion": "SP.POP.TOTL",
    "pib": "NY.GDP.MKTP.CD",
    "inflacion": "FP.CPI.TOTL.ZG",
    "desempleo": "SL.UEM.TOTL.ZS",
    "renta_pc": "NY.GDP.PCAP.CD",
    "alfabetizacion": "SE.ADT.LITR.ZS",
    "titulados": "SE.TER.CUAT.TL.ZS",
    "net_mig": "SM.POP.NETM",
    "migrant_pct": "SM.POP.TOTL.ZS",
}
FALLBACK_GEO = {
    "es": ["España", 40.4, -3.7], "fr": ["Francia", 48.8, 2.3], "de": ["Alemania", 52.5, 13.4],
    "it": ["Italia", 41.9, 12.5], "gb": ["Reino Unido", 51.5, -0.1], "us": ["EE.UU.", 39.8, -98.6],
    "cn": ["China", 35.9, 104.2], "br": ["Brasil", -14.2, -51.9], "in": ["India", 20.6, 79.0],
    "mx": ["México", 23.6, -102.5], "ma": ["Marruecos", 31.8, -7.1], "dz": ["Argelia", 28.0, 1.7],
    "eg": ["Egipto", 26.8, 30.8], "pt": ["Portugal", 39.4, -8.2], "au": ["Australia", -25.3, 133.8],
}


def _get_json(url, retries=2):
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "country-intel/0.8 (research)"})
            with urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8-sig"))
        except (URLError, HTTPError, OSError, ValueError):
            if attempt == retries - 1:
                return None
            time.sleep(1.2 * (attempt + 1))
    return None


def _all_rows(url):
    d = _get_json(url)
    if not d or len(d) < 2:
        return []
    meta, rows = d[0], d[1]
    out = list(rows)
    for p in range(2, int(meta.get("pages", 1)) + 1):
        extra = _get_json(url + f"&page={p}")
        if extra and len(extra) > 1:
            out.extend(extra[1])
        time.sleep(float(CFG.get("sleep_worldbank", 1.2)))
    return out


def build_geo():
    """Mapa {iso2: {name, lat, lon, iso3}} de todos los paises reales. Cache a data/geo.json."""
    geo_path = BASE_DIR / "data" / "geo.json"
    if geo_path.exists():
        return json.loads(geo_path.read_text())
    geo = {k: {"name": v[0], "lat": v[1], "lon": v[2], "iso3": ""} for k, v in FALLBACK_GEO.items()}
    d = _get_json(WB + "country/all?format=json&per_page=320")
    if d and len(d) > 1:
        for c in d[1]:
            if not c.get("iso2Code") or c.get("region", {}).get("value") == "Aggregates":
                continue
            try:
                lat = float(c.get("latitude") or 0)
                lon = float(c.get("longitude") or 0)
            except (TypeError, ValueError):
                continue
            geo[c["iso2Code"].lower()] = {"name": c.get("name", ""), "lat": lat, "lon": lon, "iso3": c.get("id", "")}
    geo_path.write_text(json.dumps(geo, ensure_ascii=False, indent=1))
    return geo


class WorldBank(BaseCollector):
    name = "worldbank"

    def __init__(self):
        self.geo = {}
        self.errors = []

    def fetch(self):
        self.geo = build_geo()
        iso3_to_iso2 = {v.get("iso3"): k for k, v in self.geo.items()}
        seed = json.loads((BASE_DIR / "data" / "seed_countries.json").read_text(encoding="utf-8"))

        vals = {}
        for label, code in INDICATORS.items():
            rows = _all_rows(WB + f"country/all/indicator/{code}?format=json&per_page=100&date=2024")
            found = {}
            for r in rows:
                if r.get("value") is None:
                    continue
                iso2 = iso3_to_iso2.get(r.get("countryiso3code"))
                if iso2:
                    found[iso2] = r["value"]
            vals[label] = found
            print(f"  {label}: {len(found)} paises")
            time.sleep(float(CFG.get("sleep_worldbank", 1.2)))

        max_c = int(CFG.get("max_countries", 0))
        codes = sorted(self.geo)
        if max_c and len(codes) > max_c:
            keep = sorted(set(codes) & set(seed))
            codes = keep + [c for c in codes if c not in keep][: max_c - len(keep)]

        out = []
        for cc in codes:
            seed_ind = seed.get(cc, {})
            got = False
            for label in INDICATORS:
                live = vals[label].get(cc)
                if live is not None:
                    out.append({"country": cc, "indicator": label, "value": live, "source": self.name})
                    got = True
                elif label in seed_ind:
                    out.append({"country": cc, "indicator": label, "value": seed_ind[label], "source": "seed"})
                    got = True
            for label, value in seed_ind.items():
                if label not in INDICATORS:
                    out.append({"country": cc, "indicator": label, "value": value, "source": "seed"})
            if not got and not seed_ind:
                self.errors.append(cc)
        return out

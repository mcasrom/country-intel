"""Collector Banco Mundial VIVO: all-countries por indicador, periodo 2023-2024
(ultimo año disponible por pais, persistido), geo de todos los paises,
retry/backoff/throttle, fallback al seed, conserva valores previos si falla."""
import hashlib
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.config import BASE_DIR, CFG
from src.core.collector import BaseCollector

WB = "https://api.worldbank.org/v2/"
WB_CACHE = BASE_DIR / "data" / "wb_cache"
WB_CACHE_TTL = int(CFG.get("wb_cache_ttl", 7 * 24 * 3600))
WB_DATE = CFG.get("wb_year", "2024")
INDICATORS = {
    "poblacion": "SP.POP.TOTL",
    "pib": "NY.GDP.MKTP.CD",
    "pib_ppa_pc": "NY.GDP.PCAP.PP.CD",
    "renta_pc": "NY.GDP.PCAP.CD",
    "inflacion": "FP.CPI.TOTL.ZG",
    "desempleo": "SL.UEM.TOTL.ZS",
    "alfabetizacion": "SE.ADT.LITR.ZS",
    "net_mig": "SM.POP.NETM",
    "migrant_pct": "SM.POP.TOTL.ZS",
    "esperanza_vida": "SP.DYN.LE00.IN",
    "homicidios": "VC.IHR.PSRC.P5",
    "gini": "SI.POV.GINI",
    "deuda_pib": "GC.DOD.TOTL.GD.ZS",
    "gasto_salud": "SH.XPD.CHEX.GD.ZS",
    "gasto_educacion": "SE.XPD.TOTL.GD.ZS",
    "internet_pct": "IT.NET.USER.ZS",
    "urbanizacion": "SP.URB.TOTL.IN.ZS",
    "fertilidad": "SP.DYN.TFRT.IN",
    "menores": "SP.POP.0014.TO.ZS",
    "adultos": "SP.POP.1564.TO.ZS",
    "mayores": "SP.POP.65UP.TO.ZS",
    "defensa_pct": "MS.MIL.XPND.GD.ZS",
}
STATIC_SOURCE = {
    "corrupcion": "Transparency Intl 2024",
    "libertad_prensa": "RSF 2024",
    "democracia": "EIU 2024",
}
# Indicadores que NUNCA emite este collector: los cubre el collector estatico
# oficial (static_official) con datos de fuente primaria para todos los paises.
STATIC_LIVE = {"co2_pc", "titulados", "edad_mediana",
               "corrupcion", "libertad_prensa", "democracia"}
FALLBACK_GEO = {
    "es": ["España", 40.4, -3.7], "fr": ["Francia", 48.8, 2.3], "de": ["Alemania", 52.5, 13.4],
    "it": ["Italia", 41.9, 12.5], "gb": ["Reino Unido", 51.5, -0.1], "us": ["EE.UU.", 39.8, -98.6],
    "cn": ["China", 35.9, 104.2], "br": ["Brasil", -14.2, -51.9], "in": ["India", 20.6, 79.0],
    "mx": ["México", 23.6, -102.5], "ma": ["Marruecos", 31.8, -7.1], "dz": ["Argelia", 28.0, 1.7],
    "eg": ["Egipto", 26.8, 30.8], "pt": ["Portugal", 39.4, -8.2], "au": ["Australia", -25.3, 133.8],
}


def _get_json(url, retries=1):
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "country-intel/0.9 (research)"})
            with urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode("utf-8-sig"))
        except (URLError, HTTPError, OSError, ValueError):
            if attempt >= retries:
                return None
            time.sleep(0.8 * (attempt + 1))
    return None


def _all_rows(url):
    WB_CACHE.mkdir(parents=True, exist_ok=True)
    cache = WB_CACHE / f"{hashlib.md5(url.encode()).hexdigest()[:16]}.json"
    if cache.exists() and (time.time() - cache.stat().st_mtime) < WB_CACHE_TTL:
        try:
            return json.loads(cache.read_text())
        except Exception:
            pass
    d = _get_json(url)
    if not d or len(d) < 2:
        return []
    meta, rows = d[0], d[1]
    out = list(rows)
    for p in range(2, int(meta.get("pages", 1)) + 1):
        extra = _get_json(url + f"&page={p}")
        if extra and len(extra) > 1:
            out.extend(extra[1])
        time.sleep(float(CFG.get("sleep_worldbank", 0.8)))
    try:
        cache.write_text(json.dumps(out, ensure_ascii=False))
    except Exception:
        pass
    return out


def build_geo():
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
            geo[c["iso2Code"].lower()] = {"name": c.get("name", ""), "lat": lat, "lon": lon, "iso3": c.get("id", ""),
                                          "region": c.get("region", {}).get("value", "")}
    geo_path.write_text(json.dumps(geo, ensure_ascii=False, indent=1))
    return geo


class WorldBank(BaseCollector):
    name = "worldbank"

    def __init__(self):
        self.geo = {}
        self.errors = []
        self.enrich = {}
        try:
            self.enrich = json.loads((BASE_DIR / "data" / "enrich.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    def fetch(self):
        self.geo = build_geo()
        iso3_to_iso2 = {v.get("iso3"): k for k, v in self.geo.items()}
        seed = json.loads((BASE_DIR / "data" / "seed_countries.json").read_text(encoding="utf-8"))

        vals = {}
        for label, code in INDICATORS.items():
            rows = _all_rows(WB + f"country/all/indicator/{code}?format=json&per_page=100&date={WB_DATE}")
            found = {}
            for r in rows:
                if r.get("value") is None or not r.get("date"):
                    continue
                iso2 = iso3_to_iso2.get(r.get("countryiso3code"))
                if not iso2:
                    continue
                cur = found.get(iso2)
                if cur is None or r["date"] > cur["year"]:
                    found[iso2] = {"value": r["value"], "year": r["date"]}
            vals[label] = found
            print(f"  {label}: {len(found)} paises", flush=True)
            time.sleep(float(CFG.get("sleep_worldbank", 0.8)))

        # net_mig (SM.POP.NETM) es el valor ABSOLUTO de migración neta (personas);
        # se convierte a tasa por 1000 habitantes usando la población para que sea
        # consistente con el seed (por mil).
        pops = vals.get("poblacion", {})
        for cc, v in vals.get("net_mig", {}).items():
            p = pops.get(cc, {}).get("value")
            if p:
                v["value"] = v["value"] / (float(p) / 1000.0)

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
                if live:
                    out.append({"country": cc, "indicator": label, "value": live["value"], "year": live["year"], "source": self.name})
                    got = True
                elif label in seed_ind:
                    out.append({"country": cc, "indicator": label, "value": seed_ind[label], "source": "seed"})
                    got = True
            for label, value in seed_ind.items():
                if label not in INDICATORS and label not in STATIC_LIVE:
                    out.append({"country": cc, "indicator": label, "value": value, "source": STATIC_SOURCE.get(label, "seed")})
            en = self.enrich.get(cc, {})
            if en.get("moneda") and "moneda" not in seed_ind:
                out.append({"country": cc, "indicator": "moneda", "value": en["moneda"], "source": "static"})
            if en.get("idh") and "idh" not in seed_ind:
                out.append({"country": cc, "indicator": "idh", "value": en["idh"], "source": "PNUD 2022"})
            reg = self.geo.get(cc, {}).get("region")
            if reg and "region" not in seed_ind:
                out.append({"country": cc, "indicator": "region", "value": reg, "source": "Banco Mundial"})
            if not got and not seed_ind:
                self.errors.append(cc)
        return out

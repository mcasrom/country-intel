"""Importa datasets oficiales -> data/static/*.csv normalizado (country iso2, value, year)
+ sources.json (procedencia). Stdlib puro. Uso: venv/bin/python scripts/import_static.py
Fuentes:
  co2_pc         Global Carbon Project via OWID (owid-co2-data.csv)
  edad_mediana   UN WPP 2024 via OWID (grapher median-age)
  corrupcion     Transparency Intl CPI 2024 via OWID
  libertad_prensa RSF 2024 (espejo DW)
  democracia     EIU Democracy Index 2024 (World Bank Data360)
  titulados      UNESCO UIS / Banco Mundial SE.TER.CUAT.ST.ZS
Los CSVs normalizados se commitean; el collector static_official solo los lee."""
import csv
import io
import json
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent.parent
STATIC = BASE / "data" / "static"
RAW = STATIC / "raw"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 country-intel/1.0"}

SOURCES = {
    "co2_pc": {
        "url": "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv",
        "source": "Global Carbon Project (OWID) 2024", "decimals": 3},
    "edad_mediana": {
        "url": "https://ourworldindata.org/grapher/median-age.csv",
        "source": "UN WPP 2024 (OWID)", "decimals": 1},
    "corrupcion": {
        "url": "https://ourworldindata.org/grapher/ti-corruption-perception-index.csv",
        "source": "Transparency Intl CPI 2024", "decimals": 1},
    "libertad_prensa": {
        "url": "https://raw.githubusercontent.com/dw-data/world-press-freedom-2026/main/csvs/rsf-files/2024.csv",
        "source": "RSF Press Freedom 2024", "decimals": 1},
    "democracia": {
        "url": "https://data360files.worldbank.org/data360-data/data/EIU_DI/EIU_DI_INDEX_WIDEF.csv",
        "source": "EIU Democracy Index 2024", "decimals": 2},
    "titulados": {
        "url": "https://api.worldbank.org/v2/country/all/indicator/SE.TER.CUAT.ST.ZS?downloadformat=csv",
        "source": "UNESCO UIS (Banco Mundial) 2023", "decimals": 1},
}
YEAR_FIX = {"libertad_prensa": 2024, "democracia": 2024}


def _download(url):
    with urlopen(Request(url, headers=UA), timeout=120) as r:
        return r.read()


def _write_csv(label, rows, decimals):
    with (STATIC / f"{label}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["country", "value", "year"])
        for cc, v, y in sorted(rows):
            w.writerow([cc, f"{float(v):.{decimals}f}", y])
    return len(rows)


def _text(raw):
    return raw.decode("utf-8-sig", "replace")


def parse_co2(raw, iso3_to_iso2):
    r = csv.DictReader(io.StringIO(_text(raw)))
    best = {}
    for row in r:
        cc = iso3_to_iso2.get((row.get("iso_code") or "").upper())
        if not cc or not row.get("co2_per_capita"):
            continue
        y = row.get("year", "")
        if cc not in best or y > best[cc][1]:
            best[cc] = (row["co2_per_capita"], y)
    return [(cc, v, y) for cc, (v, y) in best.items()]


def parse_owid_latest(raw, iso3_to_iso2, value_col):
    r = csv.DictReader(io.StringIO(_text(raw)))
    best = {}
    for row in r:
        cc = iso3_to_iso2.get((row.get("Code") or "").upper())
        if not cc or not row.get(value_col):
            continue
        y = row.get("Year", "")
        if cc not in best or y > best[cc][1]:
            best[cc] = (row[value_col], y)
    return [(cc, v, y) for cc, (v, y) in best.items()]


def parse_median_age(raw, iso3_to_iso2):
    r = csv.DictReader(io.StringIO(_text(raw)))
    obs, proj = {}, {}
    for row in r:
        cc = iso3_to_iso2.get((row.get("Code") or "").upper())
        if not cc:
            continue
        y = row.get("Year", "")
        vo = row.get("Median age")
        if vo:
            if cc not in obs or y > obs[cc][1]:
                obs[cc] = (vo, y)
        vp = row.get("Median age (Projected)")
        if vp and 2024 <= int(y or 0) <= 2026:
            if cc not in proj or y > proj[cc][1]:
                proj[cc] = (vp, y)
    best = {}
    for cc, (v, y) in obs.items():
        best[cc] = (v, y)
    for cc, (v, y) in proj.items():
        if cc not in best:
            best[cc] = (v, y)
    return [(cc, v, y) for cc, (v, y) in best.items()]


def parse_press(raw, iso3_to_iso2):
    r = csv.DictReader(io.StringIO(_text(raw)), delimiter=";")
    out = []
    for row in r:
        cc = iso3_to_iso2.get((row.get("ISO") or "").upper())
        if not cc or not row.get("Score"):
            continue
        v = row["Score"].replace(",", ".")
        out.append((cc, v, 2024))
    return out


def parse_democracy(raw, iso3_to_iso2):
    r = csv.DictReader(io.StringIO(_text(raw)))
    out = []
    for row in r:
        cc = iso3_to_iso2.get((row.get("REF_AREA") or "").upper())
        if not cc or not row.get("2024"):
            continue
        out.append((cc, row["2024"], 2024))
    return out


def parse_tertiary(raw, iso3_to_iso2):
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next((n for n in z.namelist() if n.startswith("API_")), None)
    if not name:
        return []
    lines = _text(z.read(name)).splitlines()
    hdr = next((i for i, l in enumerate(lines) if l.lstrip().startswith('"Country Name"')), 0)
    r = csv.DictReader(io.StringIO("\n".join(lines[hdr:])))
    best = {}
    for row in r:
        cc = iso3_to_iso2.get((row.get("Country Code") or "").upper())
        if not cc:
            continue
        for y in range(1960, 2030):
            v = row.get(str(y))
            if v not in (None, ""):
                if cc not in best or y > best[cc][1]:
                    best[cc] = (v, y)
    return [(cc, v, y) for cc, (v, y) in best.items()]


def main():
    geo = json.loads((BASE / "data" / "geo.json").read_text(encoding="utf-8"))
    iso3_to_iso2 = {v.get("iso3", "").upper(): k for k, v in geo.items()}
    STATIC.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {}
    total = 0
    for label, meta in SOURCES.items():
        print(f"[import_static] {label}...", flush=True)
        raw = _download(meta["url"])
        (RAW / f"{label}.bin").write_bytes(raw)
        if label == "co2_pc":
            rows = parse_co2(raw, iso3_to_iso2)
        elif label == "edad_mediana":
            rows = parse_median_age(raw, iso3_to_iso2)
        elif label == "libertad_prensa":
            rows = parse_press(raw, iso3_to_iso2)
        elif label == "democracia":
            rows = parse_democracy(raw, iso3_to_iso2)
        elif label == "titulados":
            rows = parse_tertiary(raw, iso3_to_iso2)
        else:
            rows = parse_owid_latest(raw, iso3_to_iso2, "Corruption Perceptions Index")
        n = _write_csv(label, rows, meta["decimals"])
        total += n
        manifest[label] = {"source": meta["source"], "url": meta["url"], "year": YEAR_FIX.get(label, ""), "countries": n}
        print(f"  -> {n} paises", flush=True)
    (STATIC / "sources.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"[import_static] OK: {len(SOURCES)} indicadores, {total} filas")


if __name__ == "__main__":
    sys.exit(main())

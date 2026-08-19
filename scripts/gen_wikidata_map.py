import json
import urllib.request
from pathlib import Path

BASE = Path("/home/deploy/country-intel")
JSON_DIR = BASE / "data" / "json"
OUT = BASE / "src" / "wikidata_map.py"

QUERY = """SELECT ?qid ?iso WHERE { ?qid wdt:P297 ?iso. ?qid wdt:P31 wd:Q6256. }"""
url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": QUERY})
req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json", "User-Agent": "country-intel/1.0 (build-time)"})
data = json.loads(urllib.request.urlopen(req, timeout=60).read())
rows = data["results"]["bindings"]
wd = {r["iso"]["value"]: r["qid"]["value"].rsplit("/", 1)[-1] for r in rows}

codes = sorted(p.stem for p in JSON_DIR.glob("*.json") if p.suffix == ".json")
map_ = {}
missing = []
for c in codes:
    q = wd.get(c.upper())
    if q:
        map_[c] = q
    else:
        missing.append(c)

lines = ['"""Mapa estatico ISO2 -> Wikidata QID (generado por scripts/gen_wikidata_map.py)."""',
         "WIKIDATA = {"]
for c in sorted(map_):
    lines.append(f'    "{c}": "{map_[c]}",')
lines.append("}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"OK: {len(map_)} paises mapeados -> {OUT}")
print(f"sin QID en wikidata: {len(missing)} {missing[:15]}")

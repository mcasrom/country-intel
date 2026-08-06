import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import JSON_DIR, BASE_DIR

app = FastAPI(title="Country Intelligence", version="0.3.0")

TRAVEL_DIR = BASE_DIR / "data" / "travel"
NEWS_DIR = BASE_DIR / "data" / "news"
TRAVEL_TTL = 24 * 3600
NEWS_TTL = 3600
NEWS_QUERY = {
    "es": "España OR Spain", "fr": "Francia OR France", "de": "Alemania OR Germany",
    "it": "Italia OR Italy", "gb": "Reino Unido OR United Kingdom", "us": "United States OR USA",
    "cn": "China", "br": "Brasil OR Brazil", "in": "India", "mx": "México OR Mexico",
    "ma": "Marruecos OR Morocco", "dz": "Argelia OR Algeria", "eg": "Egipto OR Egypt",
    "pt": "Portugal", "au": "Australia",
}
TRAVEL_SLUGS = {
    "es": "spain", "fr": "france", "de": "germany", "it": "italy",
    "gb": None, "us": "usa", "cn": "china", "br": "brazil", "in": "india",
    "mx": "mexico", "ma": "morocco", "dz": "algeria", "eg": "egypt", "pt": "portugal",
    "au": "australia",
}
FCDO_URL = "https://www.gov.uk/api/content/foreign-travel-advice/{slug}"

TRENDS_FILE = BASE_DIR / "data" / "trends.json"
TRENDING_DIR = BASE_DIR / "data" / "trending"
TRENDING_TTL = 6 * 3600
TOPICS = ["hoteles", "precios", "trabajo", "vacaciones", "vuelos", "comida", "seguridad", "alquiler"]
AC_URL = "https://suggestqueries.google.com/complete/search?client=firefox&hl=es&q={q}"
NAMES = {
    "es": "España", "fr": "Francia", "de": "Alemania", "it": "Italia", "gb": "Reino Unido",
    "us": "Estados Unidos", "cn": "China", "br": "Brasil", "in": "India", "mx": "México",
    "ma": "Marruecos", "dz": "Argelia", "eg": "Egipto", "pt": "Portugal", "au": "Australia",
}


def _clean(html: str, limit: int = 600):
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _fetch_fcdo(slug: str):
    req = urllib.request.Request(
        FCDO_URL.format(slug=slug),
        headers={"User-Agent": "country-intel/0.2 (research)"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


@app.get("/health")
def health():
    return {"ok": True, "service": "country-intel"}


@app.get("/api/countries")
def countries():
    files = sorted(JSON_DIR.glob("*.json")) if JSON_DIR.exists() else []
    return {"countries": [f.stem for f in files]}


@app.get("/api/country/{code}")
def country(code: str):
    fp = JSON_DIR / f"{code.lower()}.json"
    if not fp.exists():
        raise HTTPException(404, "Pais no encontrado o sin datos")
    return json.loads(fp.read_text())


@app.get("/api/travel/{code}")
def travel(code: str):
    slug = TRAVEL_SLUGS.get(code.lower())
    if slug is None:
        return {"country": code.lower(), "slug": None, "note": "País sin aviso FCDO propio (Reino Unido).", "alerts": []}
    TRAVEL_DIR.mkdir(parents=True, exist_ok=True)
    cache = TRAVEL_DIR / f"{code.lower()}.json"
    if cache.exists() and (time.time() - cache.stat().st_mtime) < TRAVEL_TTL:
        return json.loads(cache.read_text())
    try:
        data = _fetch_fcdo(slug)
        alerts = [
            {"title": a.get("title", ""), "type": a.get("type", ""), "body": a.get("body", "")[:900]}
            for a in (data.get("details", {}).get("alerts", []) or [])
        ]
        key_parts = ["summary", "safety-and-security", "terrorism", "natural-disasters", "entry-requirements", "health"]
        parts = []
        for pt in (data.get("details", {}).get("parts", []) or []):
            slug_pt = (pt.get("slug") or "").lower()
            if slug_pt in key_parts or slug_pt.startswith("summary"):
                parts.append({"title": pt.get("title", ""), "slug": slug_pt, "body": _clean(pt.get("body") or "")})
        out = {
            "country": code.lower(),
            "slug": slug,
            "updated": data.get("updated_at", ""),
            "title": data.get("title", ""),
            "alert_status": data.get("details", {}).get("alert_status", []),
            "change": (data.get("details", {}).get("change_description") or "")[:300],
            "alerts": alerts,
            "parts": parts,
        }
        cache.write_text(json.dumps(out, ensure_ascii=False))
        return out
    except Exception as e:
        return {"country": code.lower(), "slug": slug, "error": str(e), "alerts": []}


def _gdelt(q: str):
    url = "https://api.gdeltproject.org/api/v2/doc/doc?query=" + urllib.parse.quote(q) + "&mode=artlist&format=json&maxrecords=6&sort=updateddesc"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "country-intel/0.3 (research)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))
            return [{"title": a.get("title", ""), "url": a.get("url", "")} for a in d.get("articles", [])]
    except Exception:
        return None


def _gnews_rss(q: str):
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=es&gl=ES&ceid=ES:es"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            root = ET.fromstring(r.read())
            items = []
            for it in root.iter("item"):
                items.append({"title": it.findtext("title") or "", "url": it.findtext("link") or ""})
                if len(items) >= 6:
                    break
            return items
    except Exception:
        return []


@app.get("/api/news/{code}")
def news(code: str):
    q = NEWS_QUERY.get(code.lower(), code.upper())
    cache = NEWS_DIR / f"{code.lower()}.json"
    if cache.exists() and (time.time() - cache.stat().st_mtime) < NEWS_TTL:
        return json.loads(cache.read_text())
    arts = _gdelt(q)
    src = "gdelt"
    if arts is None or not arts:
        arts = _gnews_rss(q)
        src = "google-news-rss"
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    out = {"country": code.lower(), "source": src, "articles": arts or []}
    cache.write_text(json.dumps(out, ensure_ascii=False))
    return out


def _autocomplete(q: str):
    url = AC_URL.format(q=urllib.parse.quote(q))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
        return data[1] if isinstance(data, list) and len(data) > 1 else []


def _refresh_trending(cc: str):
    name = NAMES.get(cc, cc.upper()).lower()
    cache = TRENDING_DIR / f"{cc}.json"
    if cache.exists() and (time.time() - cache.stat().st_mtime) < TRENDING_TTL:
        return json.loads(cache.read_text())
    topics = {}
    base = f"{name} "
    for t in TOPICS:
        try:
            sugs = _autocomplete(base + t)
            topics[t] = [s for s in sugs if s.strip().lower() != (base + t).strip().lower()][:5]
        except Exception:
            topics[t] = []
    TRENDING_DIR.mkdir(parents=True, exist_ok=True)
    out = {"country": cc, "name": name, "topics": topics}
    cache.write_text(json.dumps(out, ensure_ascii=False))
    return out


@app.get("/api/trending/all")
def trending_all():
    for cc in sorted(NAMES):
        cache = TRENDING_DIR / f"{cc}.json"
        fresh = cache.exists() and (time.time() - cache.stat().st_mtime) < TRENDING_TTL
        if not fresh:
            _refresh_trending(cc)
            time.sleep(0.3)
    countries = {}
    for cc in sorted(NAMES):
        try:
            d = json.loads((TRENDING_DIR / f"{cc}.json").read_text())
            countries[cc] = d.get("topics", {})
        except Exception:
            countries[cc] = {}
    return {"countries": countries}


@app.get("/api/trending/{code}")
def trending(code: str):
    return _refresh_trending(code.lower())


def _load_trends():
    try:
        return json.loads(TRENDS_FILE.read_text())
    except Exception:
        return {}


def _save_trends(t):
    TRENDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRENDS_FILE.write_text(json.dumps(t, ensure_ascii=False, indent=1))


@app.get("/api/trends")
def trends():
    t = _load_trends()
    rows = [{"code": cc, "name": NAMES.get(cc, cc.upper()), "views": v} for cc, v in t.items()]
    rows.sort(key=lambda r: r["views"], reverse=True)
    return {"trends": rows}


@app.get("/api/trends/view/{code}")
def trend_view(code: str):
    t = _load_trends()
    cc = code.lower()
    t[cc] = t.get(cc, 0) + 1
    _save_trends(t)
    return {"code": cc, "views": t[cc]}


def _seo_page(code: str) -> str:
    cc = code.lower()
    name = NAMES.get(cc, cc.upper())
    fp = JSON_DIR / f"{cc}.json"
    data = {}
    if fp.exists():
        data = json.loads(fp.read_text())
    ind = data.get("indicators", {})
    def gv(k):
        v = ind.get(k, {}).get("value") if ind.get(k) else None
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return v
    pobl = gv("poblacion")
    pib = gv("pib")
    pobl_txt = f"{(pobl / 1e6):.1f} millones" if isinstance(pobl, float) else "n/d"
    pib_txt = f"{pib / 1e12:.2f} billones de USD" if isinstance(pib, float) and pib >= 1e12 else (f"{pib / 1e9:.1f} mil millones de USD" if isinstance(pib, float) else "n/d")
    desc = f"Ficha de inteligencia OSINT de {name}: población {pobl_txt}, PIB {pib_txt}, inflación, desempleo, defensa, estructura etaria, riesgo de visita, avisos de viaje, noticias y alertas."
    url = f"https://country.viajeinteligencia.com/pais/{cc}"
    ld = {
        "@context": "https://schema.org",
        "@type": "Country",
        "name": name,
        "description": desc,
        "url": url,
    }
    region = gv("region")
    if region:
        ld["containedInPlace"] = {"@type": "Continent", "name": region}
    if pobl:
        ld["population"] = {"@type": "QuantitativeValue", "value": int(pobl)}
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} · Inteligencia OSINT | Country Intelligence</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:title" content="{name} · Inteligencia OSINT">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" hreflang="es" href="{url}">
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False, indent=1)}
</script>
</head>
<body>
<h1>{name}</h1>
<p>{desc}</p>
<p>Información orientativa para investigación. Ver el dashboard interactivo:</p>
<p><a href="https://country.viajeinteligencia.com/?c={cc}">Abrir ficha interactiva de {name}</a> · <a href="https://country.viajeinteligencia.com/">Inicio</a></p>
</body>
</html>"""


@app.get("/pais/{code}")
def pais(code: str):
    cc = code.lower()
    if cc not in NAMES:
        raise HTTPException(404, "Pais no encontrado")
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_seo_page(cc))


@app.get("/sitemap.xml")
def sitemap():
    urls = ["https://country.viajeinteligencia.com/"]
    urls += [f"https://country.viajeinteligencia.com/pais/{cc}" for cc in sorted(NAMES)]
    body = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    from fastapi.responses import Response
    return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{body}
</urlset>""", media_type="application/xml")


@app.get("/robots.txt")
def robots():
    from fastapi.responses import Response
    return Response(content="User-agent: *\nAllow: /\nSitemap: https://country.viajeinteligencia.com/sitemap.xml", media_type="text/plain")


FRONTEND = BASE_DIR / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")

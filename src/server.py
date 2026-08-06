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


FRONTEND = BASE_DIR / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")

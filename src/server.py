import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from src.config import JSON_DIR, BASE_DIR, CFG

app = FastAPI(title="Country Intelligence", version="0.8.0")

# ---------------------------------------------------------------------------
# Rate limit simple por IP (en memoria, sin dependencias). Protege los
# endpoints que los bots martillean (scraping /api/country) sin añadir carga.
# ---------------------------------------------------------------------------
from collections import defaultdict, deque
import time as _time

class _RateLimiter:
    def __init__(self, limit=30, window=60):
        self.limit = limit
        self.window = window
        self.hits = defaultdict(deque)

    def allow(self, key):
        now = _time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


# 3000 req/min por IP: deja pasar SIEMPRE la carga legitima del frontend
# (217 paises en rafaga al cargar mapa/comparador/heatmap/rank; varios usuarios
# comparten la IP de Cloudflare y la rafaga inicial puede superar los cientos).
# Solo frena a un bot/scraper martilleando en bucle (los ~4.240 bots hacian
# cientos de miles de peticiones en 15 dias, no miles por minuto).
LIMITER = _RateLimiter(limit=3000, window=60)

def _client_ip(request):
    # respeta el X-Forwarded-For que pone nginx
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limited(request):
    return not LIMITER.allow(_client_ip(request))


def rate_limit_response():
    return Response(content=json.dumps({"ok": False, "reason": "too many requests"}), status_code=429, media_type="application/json")

TRAVEL_DIR = BASE_DIR / "data" / "travel"
NEWS_DIR = BASE_DIR / "data" / "news"
TRENDS_FILE = BASE_DIR / "data" / "trends.json"
TRENDING_DIR = BASE_DIR / "data" / "trending"

TRAVEL_TTL = CFG.get("ttl", {}).get("travel", 86400)
NEWS_TTL = CFG.get("ttl", {}).get("news", 3600)
TRENDING_TTL = CFG.get("ttl", {}).get("trending", 21600)
SLEEP_TRENDING = CFG.get("sleep_trending", 0.3)
TOPICS = CFG.get("topics", ["hoteles", "precios", "trabajo", "vacaciones", "vuelos", "comida", "seguridad", "alquiler"])
FCDO_PARTS = CFG.get("fcdo_parts", ["summary", "safety-and-security", "terrorism", "natural-disasters", "entry-requirements", "health"])
LIMITS = CFG.get("limits", {"news_max": 6, "body_part": 600, "alerts_body": 900})
NAMES = CFG.get("names", {})
TRAVEL_SLUGS = CFG.get("travel_slugs", {})
NEWS_QUERY = CFG.get("news_query", {})

FCDO_URL = "https://www.gov.uk/api/content/foreign-travel-advice/{slug}"
AC_URL = "https://suggestqueries.google.com/complete/search?client=firefox&hl=es&q={q}"


def _clean(html: str, limit: int = LIMITS.get("body_part", 600)):
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _fetch_fcdo(slug: str):
    req = urllib.request.Request(
        FCDO_URL.format(slug=slug),
        headers={"User-Agent": "country-intel/0.7 (research)"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


@app.get("/health")
def health():
    return {"ok": True, "service": "country-intel"}


@app.get("/api/health")
def api_health():
    last = {}
    try:
        last = json.loads((BASE_DIR / "data" / "last_run.json").read_text())
    except Exception:
        pass
    now = datetime.now(timezone.utc)
    ages = {}
    for fp in JSON_DIR.glob("*.json"):
        try:
            d = json.loads(fp.read_text())
            upds = [i.get("updated") for i in d.get("indicators", {}).values() if i.get("updated")]
            if upds:
                try:
                    ages[fp.stem] = (now - datetime.fromisoformat(max(upds))).days
                except Exception:
                    pass
        except Exception:
            pass
    max_age = max(ages.values()) if ages else -1
    stale = sorted(cc for cc, a in ages.items() if a >= int(CFG.get("stale_days", 7)))
    return {
        "ok": True,
        "service": "country-intel",
        "last_run": last.get("run_at"),
        "countries": len(list(JSON_DIR.glob("*.json"))),
        "max_data_age_days": max_age,
        "stale_countries": stale,
        "errors": last.get("errors", []),
    }


@app.get("/api/config")
def api_config():
    return CFG


@app.get("/api/countries")
def countries():
    files = sorted(JSON_DIR.glob("*.json")) if JSON_DIR.exists() else []
    return {"countries": [f.stem for f in files]}


@app.get("/api/country/{code}")
def country(code: str, request: Request):
    if rate_limited(request):
        return rate_limit_response()
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
            {"title": a.get("title", ""), "type": a.get("type", ""), "body": _clean(a.get("body", ""), LIMITS.get("alerts_body", 900))}
            for a in (data.get("details", {}).get("alerts", []) or [])
        ]
        parts = []
        for pt in (data.get("details", {}).get("parts", []) or []):
            slug_pt = (pt.get("slug") or "").lower()
            if slug_pt in FCDO_PARTS or slug_pt.startswith("summary"):
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
    url = "https://api.gdeltproject.org/api/v2/doc/doc?query=" + urllib.parse.quote(q) + "&mode=artlist&format=json&maxrecords=" + str(LIMITS.get("news_max", 6)) + "&sort=updateddesc"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "country-intel/0.7 (research)"})
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
                if len(items) >= LIMITS.get("news_max", 6):
                    break
            return items
    except Exception:
        return []


@app.get("/api/news/{code}")
def news(code: str, request: Request):
    if rate_limited(request):
        return rate_limit_response()
    q = NEWS_QUERY.get(code.lower()) or (json.loads((BASE_DIR / "data" / "geo.json").read_text()).get(code.lower(), {}) or {}).get("name", "") or code.upper()
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
    # Nombre real del país: NAMES curado (15) o nombre WB de geo.json (217), nunca el código ISO.
    geo_name = ""
    try:
        geo_name = (json.loads((BASE_DIR / "data" / "geo.json").read_text()).get(cc, {}) or {}).get("name", "")
    except Exception:
        geo_name = ""
    name = (NAMES.get(cc) or geo_name or cc.upper()).lower()
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
            time.sleep(SLEEP_TRENDING)
    countries = {}
    for cc in sorted(NAMES):
        try:
            d = json.loads((TRENDING_DIR / f"{cc}.json").read_text())
            countries[cc] = d.get("topics", {})
        except Exception:
            countries[cc] = {}
    return {"countries": countries}


@app.get("/api/trending/{code}")
def trending(code: str, request: Request):
    if rate_limited(request):
        return rate_limit_response()
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


def _country_name(cc):
    """Nombre real del país: NAMES curado (15) o geo.json (217), nunca el código."""
    if cc in NAMES:
        return NAMES[cc]
    try:
        geo = json.loads((BASE_DIR / "data" / "geo.json").read_text())
        return (geo.get(cc, {}) or {}).get("name", cc.upper())
    except Exception:
        return cc.upper()


def _seo_page(code: str) -> str:
    cc = code.lower()
    name = _country_name(cc)
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
    def fmt_num(v, dec=1):
        if v is None:
            return "n/d"
        if isinstance(v, float) and abs(v) >= 1e12:
            return f"{v / 1e12:.2f} billones de USD"
        if isinstance(v, float) and abs(v) >= 1e9:
            return f"{v / 1e9:.1f} mil millones de USD"
        if isinstance(v, float) and abs(v) >= 1e6:
            return f"{v / 1e6:.1f} millones"
        return f"{v:.{dec}f}" if isinstance(v, float) else str(v)
    pobl = gv("poblacion")
    pib = gv("pib")
    idh = gv("idh")
    infl = gv("inflacion")
    des = gv("desempleo")
    internet = gv("internet_pct")
    esp = gv("esperanza_vida")
    urban = gv("urbanizacion")
    coste = gv("coste_vida")
    def semaforo_vida(v):
        if v is None:
            return "n/d"
        if v < 0.5:
            return "🟢 Muy barato"
        if v < 0.8:
            return "🟡 Moderado"
        if v < 1.1:
            return "🟠 Similar a España"
        return "🔴 Caro"
    region = gv("region")
    moneda = ind.get("moneda", {}).get("value") if ind.get("moneda") else None
    region_txt = f", en {region}" if region else ""
    año = datetime.now().year
    # Description orientada a SEO: primero los datos disponibles, luego los n/d
    desc_parts = []
    if pobl is not None: desc_parts.append(f"población {fmt_num(pobl)}")
    if pib is not None: desc_parts.append(f"PIB {fmt_num(pib)}")
    if idh is not None: desc_parts.append(f"IDH {fmt_num(idh, 3)}")
    if infl is not None: desc_parts.append(f"inflación {fmt_num(infl)}%")
    if des is not None: desc_parts.append(f"desempleo {fmt_num(des)}%")
    if internet is not None: desc_parts.append(f"internet {fmt_num(internet)}%")
    if esp is not None: desc_parts.append(f"esperanza de vida {fmt_num(esp)} años")
    if urban is not None: desc_parts.append(f"urbanización {fmt_num(urban)}%")
    desc = f"Población de {name} en {año}{region_txt}: " + ", ".join(desc_parts) + "."
    # Nota para territorios sin datos de organismos (IDH/internet/moneda)
    falta = []
    if idh is None: falta.append("IDH")
    if internet is None: falta.append("internet")
    if moneda is None: falta.append("moneda")
    nota_nd = ""
    if falta:
        nota_nd = " Datos de " + ", ".join(falta) + " no publicados por los organismos para territorios dependientes."
    desc += nota_nd
    url = f"https://country.viajeinteligencia.com/pais/{cc}"
    KPI_PIB = {"ad", "bo", "br", "fr", "ve"}
    KPI_IDH = {"be"}
    if cc in KPI_PIB:
        seo_title = f"{name}: PIB, Población e IDH {año} | Viaje Inteligencia"
    elif cc in KPI_IDH:
        seo_title = f"{name}: IDH, Población y PIB {año} | Viaje Inteligencia"
    else:
        seo_title = f"{name}: Población, PIB e IDH {año} | Viaje Inteligencia"
    ld = {
        "@context": "https://schema.org",
        "@type": "Country",
        "name": name,
        "description": desc,
        "url": url,
    }
    if region:
        ld["containedInPlace"] = {"@type": "Continent", "name": region}
    if pobl:
        ld["population"] = {"@type": "QuantitativeValue", "value": int(pobl)}
    ind_rows = ""
    facts = [
        ("Población", fmt_num(pobl)),
        ("PIB (nominal)", fmt_num(pib)),
        ("IDH", fmt_num(idh, 3)),
        ("Inflación anual", f"{fmt_num(infl)}%"),
        ("Desempleo", f"{fmt_num(des)}%"),
        ("Internet (% población)", f"{fmt_num(internet)}%"),
        ("Esperanza de vida", f"{fmt_num(esp)} años"),
        ("Urbanización", f"{fmt_num(urban)}%"),
        ("Moneda", str(moneda) if moneda else "n/d"),
        ("Coste de vida (EE.UU.=1)", semaforo_vida(coste) if coste is None else f"{semaforo_vida(coste)} ({fmt_num(coste)})"),
    ]
    ind_rows = "\n".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in facts)
    nota_html = ""
    if falta:
        nota_html = ('<p style="font-size:.75em;color:#64748b;margin-top:8px;">' +
                     'Nota: ' + ", ".join(falta) + ' no están publicados por los organismos (PNUD, UIT, FMI) para territorios dependientes. Los datos disponibles provienen del Banco Mundial.</p>')
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{seo_title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:title" content="{seo_title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="es_ES">
<meta name="twitter:card" content="summary_large_image">
<meta property="og:image" content="https://country.viajeinteligencia.com/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{name} · Viaje Inteligencia">
<link rel="alternate" hreflang="es" href="{url}">
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False, indent=1)}
</script>
</head>
<body>
<h1>{name}: población, PIB, IDH y datos</h1>
<p>{desc}</p>
<table>
<thead><tr><th>Indicador</th><th>Valor</th></tr></thead>
<tbody>
{ind_rows}
 </tbody>
 </table>
 {nota_html}
 <p>Datos orientativos para investigación (fuentes: World Bank y organismos abiertos).</p>
<p><a href="https://country.viajeinteligencia.com/?c={cc}">Abrir ficha interactiva de {name}</a> · <a href="https://country.viajeinteligencia.com/">Inicio</a></p>
</body>
</html>"""


@app.get("/pais/{code}")
def pais(code: str):
    cc = code.lower()
    if cc not in NAMES and not (JSON_DIR / f"{cc}.json").exists():
        raise HTTPException(404, "Pais no encontrado")
    return HTMLResponse(_seo_page(cc))


@app.get("/vacaciones")
def vacaciones():
    page = BASE_DIR / "frontend" / "vacaciones.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return {"error": "Page not found"}


@app.get("/sitemap.xml")
def sitemap():
    codes = sorted(c.stem for c in JSON_DIR.glob("*.json")) if JSON_DIR.exists() else []
    urls = ["https://country.viajeinteligencia.com/"]
    urls += ["https://country.viajeinteligencia.com/vacaciones"]
    urls += ["https://country.viajeinteligencia.com/comparativa-espana-marruecos-portugal"]
    urls += ["https://country.viajeinteligencia.com/top-10-paises-mas-seguros-2026"]
    urls += ["https://country.viajeinteligencia.com/paises-mas-baratos-viajar-2026"]
    urls += ["https://country.viajeinteligencia.com/paises-mejor-calidad-vida-2026"]
    urls += ["https://country.viajeinteligencia.com/paises-mas-internet-2026"]
    urls += ["https://country.viajeinteligencia.com/paises-mas-caros-vivir-2026"]
    urls += [f"https://country.viajeinteligencia.com/pais/{cc}" for cc in codes]
    body = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{body}
</urlset>""", media_type="application/xml")


@app.get("/robots.txt")
def robots():
    return Response(content="User-agent: *\nAllow: /\nSitemap: https://country.viajeinteligencia.com/sitemap.xml", media_type="text/plain")



@app.get("/comparativa-espana-marruecos-portugal")
def post_espana_ma_pt():
    page = BASE_DIR / "frontend" / "comparativa-espana-marruecos-portugal.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return {"error": "Page not found"}


@app.get("/top-10-paises-mas-seguros-2026")
def post_top_seguros():
    page = BASE_DIR / "frontend" / "top-10-paises-mas-seguros-2026.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return {"error": "Page not found"}


@app.get("/paises-mas-baratos-viajar-2026")
def post_baratos():
    page = BASE_DIR / "frontend" / "paises-mas-baratos-viajar-2026.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return {"error": "Page not found"}



@app.get("/paises-mejor-calidad-vida-2026")
def post_calidad_vida():
    page = BASE_DIR / "frontend" / "paises-mejor-calidad-vida-2026.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return {"error": "Page not found"}


@app.get("/paises-mas-internet-2026")
def post_internet():
    page = BASE_DIR / "frontend" / "paises-mas-internet-2026.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return {"error": "Page not found"}


@app.get("/paises-mas-caros-vivir-2026")
def post_caros():
    page = BASE_DIR / "frontend" / "paises-mas-caros-vivir-2026.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return {"error": "Page not found"}


FRONTEND = BASE_DIR / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import JSON_DIR, BASE_DIR

app = FastAPI(title="Country Intelligence", version="0.1.0")


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


FRONTEND = BASE_DIR / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")

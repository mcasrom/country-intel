import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
JSON_DIR = DATA_DIR / "json"
DB_PATH = DATA_DIR / "country.db"
PORT = int(os.environ.get("PORT", 8710))
COUNTRIES = os.environ.get("COUNTRIES", "esp,fra,deu,ita,gbr,usa,chn,bra,ind,mex").split(",")
CACHE_TTL = int(os.environ.get("CACHE_TTL", 86400))

CONFIG_PATH = DATA_DIR / "config.json"


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


CFG = load_config()

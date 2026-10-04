import os
from pathlib import Path
from dotenv import load_dotenv

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
load_dotenv(SRC / ".env")

DATA = ROOT / "data"                    # gitignored
RAW = DATA / "raw"                      # downloaded datasets
RUNS = DATA / "runs"                    # analysis output, one folder per dataset
STREAMS = DATA / "streams"              # rolling-window stream state
DEMO_RUNS = ROOT / "demo_data" / "runs" # pre-loaded demo datasets
BOB_RULES = ROOT / ".bob" / "rules-osint-analyst"
WEB_DIST = SRC / "web" / "dist"

APP_HOST = os.getenv("APP_HOST", "0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
APP_PORT = int(os.getenv("PORT", os.getenv("APP_PORT", "8000")))
APP_ENV = os.getenv("APP_ENV", "development")
APP_AUTH_USERNAME = os.getenv("APP_AUTH_USERNAME", "")
APP_AUTH_PASSWORD = os.getenv("APP_AUTH_PASSWORD", "")
TIME_WINDOW = int(os.getenv("TIME_WINDOW_SECONDS", "60"))
MIN_EDGE_WEIGHT = int(os.getenv("MIN_EDGE_WEIGHT", "2"))
# 3 h: rumour networks post in bursts spread over hours; a 15-minute window never saw the demo incidents
STREAM_WINDOW_SECONDS = int(os.getenv("STREAM_WINDOW_SECONDS", "10800"))
STREAM_RETENTION_SECONDS = int(os.getenv("STREAM_RETENTION_SECONDS", "86400"))
BOB_API_KEY = os.getenv("BOB_API_KEY", "")
BOB_MAX_COST = os.getenv("BOB_MAX_COST", "0.25")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")  # optional: pull posts from X recent search

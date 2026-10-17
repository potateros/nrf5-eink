"""Where things live in the repo, in one place (every other module imports from here)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.toml"
ENV = ROOT / ".env"
CACHE = ROOT / ".cache"          # gitignored: fetched data, logs, the built CalendarExport.app
ASSETS = ROOT / "assets"         # fonts/, proverbs.json
WEB = ROOT / "web"               # static files for the local web tool
SCREENSHOTS = ROOT / "docs" / "images"

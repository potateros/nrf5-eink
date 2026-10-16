"""Tiny cached JSON fetcher (data.gov.sg rate-limits aggressively)."""
import hashlib
import json
import time
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / ".cache"


def fetch_json(url: str, ttl: int = 600) -> dict:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return json.loads(path.read_text())
    req = urllib.request.Request(url, headers={"User-Agent": "nrf5-eink/0.1"})
    for attempt in range(3):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=15))
            if data.get("code") == 24:  # data.gov.sg TOO_MANY_REQUESTS
                raise RuntimeError("rate limited")
            path.write_text(json.dumps(data))
            return data
        except Exception:
            if attempt == 2:
                if path.exists():
                    return json.loads(path.read_text())
                raise
            time.sleep(11)

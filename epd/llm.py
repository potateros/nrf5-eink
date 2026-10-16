"""Minimal OpenRouter chat client (stdlib only). Settings come from .env at the repo root."""
import json
import os
import urllib.request
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"
URL = "https://openrouter.ai/api/v1/chat/completions"


def load_env() -> dict[str, str]:
    """KEY=value lines from .env (no quoting rules), overridden by real environment variables."""
    out = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                out[key.strip()] = value.strip()
    return out | {k: v for k, v in os.environ.items() if k.startswith("OPENROUTER_")}


def configured() -> bool:
    return bool(load_env().get("OPENROUTER_API_KEY"))


def chat(system: str, user: str, max_tokens: int = 600, timeout: float = 45) -> tuple[str, str]:
    """Return (reply text, model that answered). Raises on HTTP/API errors or an empty reply."""
    env = load_env()
    key = env.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")
    body = {
        "model": env.get("OPENROUTER_MODEL") or "openrouter/free",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": 0.9,
        "reasoning": {"exclude": True},  # free pool includes reasoning models; we only want the answer
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Title": "nrf5-eink",
    })
    resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    if "error" in resp:
        raise RuntimeError(f"OpenRouter error: {resp['error']}")
    text = (resp["choices"][0]["message"].get("content") or "").strip()
    if not text:
        raise RuntimeError("empty reply")
    return text, resp.get("model", body["model"])

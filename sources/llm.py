"""Minimal OpenRouter chat client (stdlib only). Settings come from .env at the repo root."""
import json
import os
import urllib.request

from eink.paths import ENV
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


def chat(system: str, user: str, max_tokens: int = 4000, timeout: float = 90,
         model: str | None = None) -> tuple[str, str]:
    """Return (reply text, model that answered). `model` overrides OPENROUTER_MODEL.
    Raises on HTTP/API errors or an empty reply."""
    env = load_env()
    key = env.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")
    body = {
        "model": model or env.get("OPENROUTER_MODEL") or "openrouter/free",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": 0.9,
        # The free pool includes reasoning models that can spend the whole budget thinking: keep the
        # effort low, the budget generous, and leave the reasoning out of the reply.
        "reasoning": {"effort": "low", "exclude": True},
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Title": "nrf5-eink",
    })
    resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    if "error" in resp:
        raise RuntimeError(f"OpenRouter error: {resp['error']}")
    choice = resp["choices"][0]
    text = (choice["message"].get("content") or "").strip()
    model = resp.get("model", body["model"])
    if not text:
        raise RuntimeError(f"empty reply from {model} (finish: {choice.get('finish_reason')})")
    return text, model

"""Async LLM client: Google Gemini (default, with proxies / key rotation / retries) or Ollama."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from typing import Callable

import httpx

from ai import proxy_scheme
from ai.gemini_pool import env_settings, mask_proxy

log = logging.getLogger("ai")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_URL = "/models/{model}:generateContent"
FIRST_SLEEP = 2          # seconds before the 2nd attempt
SLEEP_STEP = 2           # each following pause is 2 s longer
CONNECT_TIMEOUT = 10.0   # a dead proxy should fail fast, not after the full read timeout


class LLMUnavailable(Exception):
    """LLM is disabled, not configured, or every attempt failed."""


def settings() -> dict:
    g = env_settings()
    return {
        "enabled": os.getenv("LLM_ENABLED", "false").lower() == "true",
        "provider": os.getenv("LLM_PROVIDER", "gemini").lower(),
        "gemini_keys": g["keys"],
        "gemini_proxies": g["proxies"],
        "gemini_models": g["models"],
        "gemini_model": g["models"][0],
        "retries": g["retries"],
        "ollama_url": os.getenv("OLLAMA_URL", "http://localhost:11434"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "codellama:7b"),
    }


def is_configured() -> bool:
    s = settings()
    if not s["enabled"]:
        return False
    return bool(s["gemini_keys"]) if s["provider"] == "gemini" else True


def _scrub(text: str, s: dict) -> str:
    """Remove API keys and proxy credentials from any message that may reach the UI/logs."""
    for key in s["gemini_keys"]:
        text = text.replace(key, "***")
    for url in s["gemini_proxies"]:
        for scheme in ("auto", "http", "https", "socks5", "socks5h"):
            text = text.replace(proxy_scheme.with_scheme(url, scheme), mask_proxy(url))
        creds = url.split("://", 1)[-1].rsplit("@", 1)[0]
        if "@" in url and creds:
            text = text.replace(creds, "***")
    return text


def _select_unused(items: list[str], used: set[str], what: str = "key") -> str:
    """Random item not used yet; when all were tried, start over with a random one."""
    available = [k for k in items if k not in used]
    if not available:
        log.warning("All %ss were used, resetting and selecting a random one", what)
        return random.choice(items)
    return random.choice(available)


_select_key = _select_unused


async def generate(
    prompt: str,
    *,
    as_json: bool = True,
    validate: Callable[[str], bool] | None = None,
    timeout: float = 30.0,
) -> str:
    """Return the model's text answer or raise :class:`LLMUnavailable`.

    Gemini: up to ``retries`` attempts; each uses a different random key (until they run out),
    a random proxy, a progressively lighter model, with a linearly growing pause in between.
    An answer rejected by *validate* counts as a failed attempt.
    """
    s = settings()
    if not is_configured():
        raise LLMUnavailable("LLM отключён или не настроен (LLM_ENABLED / GEMINI_API_KEY)")

    if s["provider"] == "ollama":
        text = await _ollama(prompt, s, as_json, timeout)
        if validate and not validate(text):
            raise LLMUnavailable("Ollama вернул ответ в неожиданном формате")
        return text

    retries, models = s["retries"], s["gemini_models"]
    used: set[str] = set()
    used_proxies: set[str] = set()
    tried_schemes: dict[str, set[str]] = {}     # per proxy: protocols already attempted in this call
    sleep_time = FIRST_SLEEP
    last_error = ""

    for attempt in range(retries):
        model = models[min(attempt, len(models) - 1)]
        key = _select_key(s["gemini_keys"], used)
        used.add(key)
        proxy = candidate = None
        if s["gemini_proxies"]:
            candidate = _select_unused(s["gemini_proxies"], used_proxies, "proxy")
            used_proxies.add(candidate)
            tried = tried_schemes.setdefault(candidate, set())
            proxy = await proxy_scheme.resolve(candidate, tried)    # auto:// → http / socks5
            tried.add(proxy_scheme.scheme_of(proxy))
        log.info("Gemini attempt %d/%d: model=%s key=...%s proxy=%s",
                 attempt + 1, retries, model, key[-4:], mask_proxy(proxy))
        try:
            text = await _gemini(key, model, prompt, as_json, proxy, timeout)
            if candidate and proxy_scheme.is_auto(candidate):
                proxy_scheme.remember(candidate, proxy_scheme.scheme_of(proxy))   # this protocol works
            if validate and not validate(text):
                raise _AttemptFailed("ответ пустой или в неожиданном формате")
            return text
        except _AttemptFailed as exc:
            if candidate and proxy_scheme.is_auto(candidate):
                proxy_scheme.forget(candidate)
            last_error = _scrub(str(exc), s)
            log.warning("Gemini attempt %d/%d failed: %s", attempt + 1, retries, last_error)
        if attempt < retries - 1:
            await asyncio.sleep(sleep_time)
            sleep_time += SLEEP_STEP

    if retries == 1:
        raise LLMUnavailable(last_error)
    raise LLMUnavailable(f"Все {retries} попытки исчерпаны. Последняя ошибка: {last_error}")


class _AttemptFailed(Exception):
    pass


async def _gemini(key: str, model: str, prompt: str, as_json: bool, proxy: str | None, timeout: float) -> str:
    body: dict = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2}}
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    client_kw: dict = {"timeout": httpx.Timeout(timeout, connect=min(timeout, CONNECT_TIMEOUT))}
    if proxy:
        client_kw["proxy"] = proxy
    base = os.getenv("GEMINI_BASE_URL", GEMINI_BASE).rstrip("/")
    try:
        async with httpx.AsyncClient(**client_kw) as client:
            # key travels in a header, never in the URL, so it can't leak into logs/errors.
            # wait_for is a hard deadline: a SOCKS/HTTP handshake mismatch can stall below httpx's timers.
            r = await asyncio.wait_for(
                client.post(base + GEMINI_URL.format(model=model), json=body, headers={"x-goog-api-key": key}),
                timeout + 5,
            )
        if r.status_code != 200:
            raise _AttemptFailed(_describe(r))
        data = r.json()
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"].get("parts", []))
        if not text.strip():
            raise _AttemptFailed("пустой ответ модели")
        return text
    except _AttemptFailed:
        raise
    except asyncio.TimeoutError:
        raise _AttemptFailed(f"таймаут {timeout:.0f} с: прокси/сеть не отвечает") from None
    except httpx.TimeoutException as exc:
        raise _AttemptFailed(f"{_timeout_text(exc)} (за {timeout:.0f} с) — прокси/сеть не отвечает, "
                             f"проверьте GEMINI_PROXY_SCHEME") from None
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        detail = str(exc).strip()
        raise _AttemptFailed(f"не удалось получить ответ ({type(exc).__name__}{': ' + detail if detail else ''})") from None


async def _ollama(prompt: str, s: dict, as_json: bool, timeout: float) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{s['ollama_url']}/api/generate",
                json={"model": s["ollama_model"], "prompt": prompt, "stream": False,
                      **({"format": "json"} if as_json else {})},
            )
        r.raise_for_status()
        return r.json().get("response", "")
    except (httpx.HTTPError, ValueError) as exc:
        raise LLMUnavailable(f"Ollama недоступен ({type(exc).__name__})") from None


def _timeout_text(exc: Exception) -> str:
    return {"ConnectTimeout": "не удалось подключиться", "ReadTimeout": "нет ответа",
            "WriteTimeout": "не удалось отправить запрос", "PoolTimeout": "нет свободного соединения"}.get(
        type(exc).__name__, "таймаут")


def _describe(resp: httpx.Response) -> str:
    """'LLM вернул ошибку 400: <message from the API>'."""
    msg = ""
    try:
        err = resp.json()
        err = err[0] if isinstance(err, list) and err else err
        msg = str(err.get("error", {}).get("message", ""))
    except Exception:  # noqa: BLE001
        msg = ""
    msg = msg.strip().replace("\n", " ")[:200]
    return f"LLM вернул ошибку {resp.status_code}" + (f": {msg}" if msg else "")


def parse_json(text: str) -> dict:
    """Lenient JSON extraction (strips ``` fences / surrounding prose)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t.lower().startswith("json") else t
    start, end = t.find("{"), t.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(t[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}

"""Parsing of the Gemini key / proxy lists from the environment."""

from __future__ import annotations

import os
import re
from urllib.parse import quote, urlparse

_SPLIT = re.compile(r"[,;\s]+")


def split_list(raw: str) -> list[str]:
    """Split a comma / semicolon / whitespace separated env value, dropping empties and duplicates."""
    seen: list[str] = []
    for item in _SPLIT.split(raw or ""):
        item = item.strip().strip("\"'")
        if item and item not in seen:
            seen.append(item)
    return seen


def parse_keys(raw: str, count: str | int | None = None) -> list[str]:
    """GEMINI_API_KEY is a list; GEMINI_KEYS_COUNT (optional) caps how many of them are used."""
    keys = split_list(raw)
    try:
        n = int(count) if count not in (None, "") else 0
    except ValueError:
        n = 0
    return keys[:n] if n > 0 else keys


def parse_proxy(entry: str, scheme: str = "http", default_port: str = "") -> str | None:
    """'ip:login:password' (or 'ip:port:login:password', or a full URL) → proxy URL.

    The login/password are percent-encoded; a password may itself contain ':'.
    Returns None for entries that can't be interpreted.
    """
    entry = entry.strip()
    if not entry:
        return None
    if "://" in entry:
        return entry if urlparse(entry).hostname else None

    parts = entry.split(":")
    if len(parts) >= 4:                         # host:port:login:password[:with:colons]
        host, port, login, password = parts[0], parts[1], parts[2], ":".join(parts[3:])
    elif len(parts) == 3:                       # host:login:password  (port comes from env)
        host, login, password = parts
        port = default_port
    else:
        return None
    if not host or not login:
        return None
    netloc = host + (f":{port}" if port else "")
    return f"{scheme or 'auto'}://{quote(login, safe='')}:{quote(password, safe='')}@{netloc}"


def parse_proxies(raw: str, scheme: str = "http", default_port: str = "") -> list[str]:
    out = []
    for entry in split_list(raw):
        url = parse_proxy(entry, scheme, default_port)
        if url and url not in out:
            out.append(url)
    return out


def mask_proxy(url: str | None) -> str:
    """scheme + host:port only – safe for logs."""
    if not url:
        return "direct"
    p = urlparse(url)
    return f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")


def env_settings() -> dict:
    keys = parse_keys(os.getenv("GEMINI_API_KEY", ""), os.getenv("GEMINI_KEYS_COUNT"))
    proxies = parse_proxies(
        os.getenv("GEMINI_PROXIES", ""),
        os.getenv("GEMINI_PROXY_SCHEME", "auto") or "auto",   # auto = detect / rotate http, socks5
        os.getenv("GEMINI_PROXY_PORT", ""),
    )
    primary = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    fallbacks = split_list(os.getenv("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite"))
    models = [primary] + [m for m in fallbacks if m != primary]
    try:
        retries = int(os.getenv("GEMINI_MAX_RETRIES", "") or 0)
    except ValueError:
        retries = 0
    if retries <= 0:  # enough attempts to try every key and every proxy×protocol combination (3..6)
        candidates = sum(2 if p.startswith("auto://") else 1 for p in proxies)
        retries = min(max(len(keys), candidates, 3), 6)
    return {"keys": keys, "proxies": proxies, "models": models, "retries": retries}

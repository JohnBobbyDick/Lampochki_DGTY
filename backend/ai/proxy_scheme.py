"""Automatic detection / rotation of the proxy protocol (http, socks5, …).

A proxy entry without an explicit scheme is stored as ``auto://login:pass@host:port``. Before a request we
*sniff* the port (no credentials are sent): a SOCKS5 server answers the greeting with byte 0x05, an HTTP proxy
answers a CONNECT with ``HTTP/…``. If sniffing gives nothing (silent port) the schemes are simply tried in turn
on successive attempts. A scheme that worked is remembered; one that failed is forgotten.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse, urlunparse

AUTO = "auto"
FALLBACK_ORDER = ("http", "socks5", "https")   # tried in this order when sniffing can't decide
SNIFF_TIMEOUT = 3.0
CACHE_TTL = 600.0

_cache: dict[str, tuple[str, float]] = {}      # "host:port" -> (scheme, timestamp)


def is_auto(url: str) -> bool:
    return url.startswith(f"{AUTO}://")


def _key(url: str) -> str:
    p = urlparse(url)
    return f"{p.hostname}:{p.port}"


def with_scheme(url: str, scheme: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(scheme=scheme))


async def _read(host: str, port: int, payload: bytes, timeout: float) -> bytes:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (OSError, asyncio.TimeoutError):
        return b""
    try:
        writer.write(payload)
        await writer.drain()
        return await asyncio.wait_for(reader.read(16), timeout)
    except (OSError, asyncio.TimeoutError):
        return b""
    finally:
        writer.close()


async def sniff(host: str, port: int, timeout: float = SNIFF_TIMEOUT) -> str | None:
    """'socks5' / 'http' or None when the port stays silent or speaks something else."""
    reply = await _read(host, port, b"\x05\x01\x00", timeout)            # SOCKS5 greeting (no credentials)
    if reply[:1] == b"\x05":
        return "socks5"
    if reply.startswith(b"HTTP/"):
        return "http"
    reply = await _read(
        host, port,
        b"CONNECT generativelanguage.googleapis.com:443 HTTP/1.1\r\nHost: generativelanguage.googleapis.com:443\r\n\r\n",
        timeout,
    )
    return "http" if reply.startswith(b"HTTP/") else None


async def resolve(url: str, tried: set[str]) -> str:
    """Concrete proxy URL for *url*; *tried* holds the schemes already used for this proxy in this call."""
    if not is_auto(url):
        return url
    key = _key(url)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[1] < CACHE_TTL and cached[0] not in tried:
        return with_scheme(url, cached[0])

    p = urlparse(url)
    detected = await sniff(p.hostname or "", p.port or 0)
    if detected and detected not in tried:
        return with_scheme(url, detected)

    for scheme in FALLBACK_ORDER:                 # silent / already tried: rotate through the rest
        if scheme not in tried:
            return with_scheme(url, scheme)
    tried.clear()                                 # everything was tried → start the cycle again
    return with_scheme(url, detected or FALLBACK_ORDER[0])


def remember(url: str, scheme: str) -> None:
    _cache[_key(url)] = (scheme, time.monotonic())


def forget(url: str) -> None:
    _cache.pop(_key(url), None)


def scheme_of(url: str) -> str:
    return urlparse(url).scheme

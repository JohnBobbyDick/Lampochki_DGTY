"""Runtime configuration shared by HTTP and WebSocket layers."""

import os
from pathlib import Path
from urllib.parse import urlparse


def _load_dotenv() -> None:
    """Tiny .env reader (no extra dependency); real environment variables win."""
    f = Path(__file__).parent / ".env"
    if os.getenv("JB_NO_DOTENV") or not f.is_file():  # tests set JB_NO_DOTENV to stay hermetic
        return
    for raw in f.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            v = v.strip()
            if v[:1] in "\"'":  # quoted value: keep everything inside the quotes
                v = v[1:].split(v[0], 1)[0]
            else:  # unquoted: drop trailing " # comment"
                v = v.split(" #", 1)[0].split("\t#", 1)[0].strip()
            os.environ.setdefault(k.strip(), v)


_load_dotenv()

# Browser origins allowed to call the API (dev servers by default). Same-origin
# requests (UI served by nginx on the same host) are always allowed.
ALLOWED_ORIGINS = {
    o.strip().rstrip("/")
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost,http://127.0.0.1",
    ).split(",")
    if o.strip()
}


def origin_allowed(origin: str | None, host: str | None) -> bool:
    """Browsers always send Origin on WebSocket handshakes; non-browser clients don't
    (and aren't subject to cross-site attacks), so a missing Origin is accepted."""
    if origin is None:
        return True
    origin = origin.rstrip("/")
    if origin in ALLOWED_ORIGINS:
        return True
    return bool(host) and urlparse(origin).netloc == host

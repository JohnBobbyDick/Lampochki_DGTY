"""In-memory state of the last parsed source: one Session per browser tab (X-Session-Id)."""

from __future__ import annotations

import contextvars
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

from fastapi import HTTPException


@dataclass
class Session:
    code: str = ""
    ast: dict = field(default_factory=dict)
    line_map: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    language: str = "java"


MAX_SESSIONS = 200
IDLE_SECONDS = 3600


class SessionStore:
    """Sessions by id: LRU-evicted above *max_sessions*, dropped after *idle_seconds* unused.

    Thread-safe (sync endpoints run in a threadpool). The default session (no header) is never evicted."""

    def __init__(self, max_sessions: int = MAX_SESSIONS, idle_seconds: float = IDLE_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self.default = Session()
        self._max = max_sessions
        self._idle = idle_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._items: OrderedDict[str, tuple[Session, float]] = OrderedDict()  # oldest first

    def get(self, sid: str) -> Session:
        now = self._clock()
        with self._lock:
            while self._items:
                oldest = next(iter(self._items))
                if now - self._items[oldest][1] <= self._idle:
                    break
                del self._items[oldest]
            entry = self._items.pop(sid, None)
            session = entry[0] if entry else Session()
            self._items[sid] = (session, now)
            while len(self._items) > self._max:
                self._items.popitem(last=False)
            return session

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def __contains__(self, sid: str) -> bool:
        with self._lock:
            return sid in self._items


STORE = SessionStore()
_current: contextvars.ContextVar[Session] = contextvars.ContextVar("jb_session", default=STORE.default)


def parse_sid(raw: str | None) -> str | None:
    """Canonical UUID text, None when no header (or empty); ValueError when it is not a UUID."""
    if not raw:
        return None
    return str(uuid.UUID(raw))


def use(sid: str | None) -> contextvars.Token:
    """Select the session for the current request context (None → the shared default)."""
    return _current.set(STORE.get(sid) if sid else STORE.default)


def reset(token: contextvars.Token) -> None:
    _current.reset(token)


def current() -> Session:
    return _current.get()


def load(code: str, language: str | None = None) -> Session:
    from core import lang as langs
    from core.runner import is_python_code
    lang = "python" if is_python_code(code, language) else "java"
    parsed = langs.get(lang).parse(code)
    s = current()
    s.code = code
    s.ast = parsed["ast"]
    s.line_map = parsed["line_map"]
    s.errors = parsed["errors"]
    s.language = lang
    return s


def require(code: str | None = None, language: str | None = None) -> Session:
    """Return the current session, (re)parsing *code* when given."""
    s = current()
    if code is not None and (code != s.code or (language and language != s.language)):
        load(code, language)
    if not s.code:
        raise HTTPException(status_code=409, detail="Сначала отправьте код через POST /api/parse")
    return s


def method_names(ast: dict) -> list[str]:
    names = []
    for c in ast.get("classes", []):
        for m in c.get("methods", []):
            if c["name"] in ("Module", ""):
                names.append(m["name"])
            else:
                names.append(f"{c['name']}.{m['name']}")
    return names


def find_method(ast: dict, ref: str | None) -> tuple[dict, dict] | None:
    """Resolve 'Class.method' / 'method' (or the first method with a body).

    Python nested defs are methods named 'outer.inner', so 'Module.outer.inner' is split after the
    class name (first dot) when such a class exists; otherwise by the last dot as before."""
    ref = ref or ""
    head, dot, tail = ref.partition(".")
    if dot and any(c.get("name") == head for c in ast.get("classes", [])):
        cls_name, name = head, tail
    else:
        cls_name, _, name = ref.rpartition(".")
    found = _find(ast, ref, cls_name, name)
    if found is None and "." in ref:  # 'outer.inner' as listed by method_names() for Module
        found = _find(ast, ref, "", ref)
    return found


def _find(ast: dict, ref: str, cls_name: str, name: str) -> tuple[dict, dict] | None:
    """The class named *cls_name* first; then (or with no *cls_name* — any class) the Python
    module pseudo-class, so a module function never shadows a same-named method of the class."""
    classes = ast.get("classes", [])
    if cls_name:
        found = _scan([c for c in classes if c["name"] == cls_name], ref, name)
        if found is not None:
            return found
        classes = [c for c in classes if c["name"] in ("Module", "")]
    return _scan(classes, ref, name)


def _scan(classes: list[dict], ref: str, name: str) -> tuple[dict, dict] | None:
    for cls in classes:
        for m in cls.get("methods", []) + cls.get("constructors", []):
            if (not name) or m["name"] == name:
                if ref or m.get("body"):
                    return cls, m
    return None

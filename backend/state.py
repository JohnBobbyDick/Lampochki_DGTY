"""In-memory state of the last parsed source (single-user demo server)."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException


@dataclass
class Session:
    code: str = ""
    ast: dict = field(default_factory=dict)
    line_map: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    language: str = "java"


SESSION = Session()


def load(code: str, language: str | None = None) -> Session:
    from core import lang as langs
    from core.runner import is_python_code
    lang = "python" if is_python_code(code, language) else "java"
    parsed = langs.get(lang).parse(code)
    SESSION.code = code
    SESSION.ast = parsed["ast"]
    SESSION.line_map = parsed["line_map"]
    SESSION.errors = parsed["errors"]
    SESSION.language = lang
    return SESSION


def require(code: str | None = None, language: str | None = None) -> Session:
    """Return the session, (re)parsing *code* when given."""
    if code is not None and (code != SESSION.code or (language and language != SESSION.language)):
        load(code, language)
    if not SESSION.code:
        raise HTTPException(status_code=409, detail="Сначала отправьте код через POST /api/parse")
    return SESSION


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
    for cls in ast.get("classes", []):
        if cls_name and cls["name"] != cls_name and cls["name"] not in ("Module", ""):
            continue
        for m in cls.get("methods", []) + cls.get("constructors", []):
            if (not name) or m["name"] == name:
                if ref or m.get("body"):
                    return cls, m
    return None

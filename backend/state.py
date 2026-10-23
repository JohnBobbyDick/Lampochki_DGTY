"""In-memory state of the last parsed source (single-user demo server)."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException

from core.parser import parse_java


@dataclass
class Session:
    code: str = ""
    ast: dict = field(default_factory=dict)
    line_map: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


SESSION = Session()


def load(code: str) -> Session:
    parsed = parse_java(code)
    SESSION.code = code
    SESSION.ast = parsed["ast"]
    SESSION.line_map = parsed["line_map"]
    SESSION.errors = parsed["errors"]
    return SESSION


def require(code: str | None = None) -> Session:
    """Return the session, (re)parsing *code* when given."""
    if code is not None and code != SESSION.code:
        load(code)
    if not SESSION.code:
        raise HTTPException(status_code=409, detail="Сначала отправьте код через POST /api/parse")
    return SESSION


def method_names(ast: dict) -> list[str]:
    return [m["name"] for c in ast.get("classes", []) for m in c["methods"]]


def find_method(ast: dict, ref: str | None) -> tuple[dict, dict] | None:
    """Resolve 'Class.method' / 'method' (or the first method with a body)."""
    cls_name, _, name = (ref or "").rpartition(".")
    for cls in ast.get("classes", []):
        if cls_name and cls["name"] != cls_name:
            continue
        for m in cls["methods"] + cls.get("constructors", []):
            if (not name) or m["name"] == name:
                if ref or m.get("body"):
                    return cls, m
    return None

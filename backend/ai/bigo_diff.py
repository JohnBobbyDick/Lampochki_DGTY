"""Big O «было → станет» for a patch: complexity of the affected methods before and after applying it."""
from __future__ import annotations

from core.bigo_analyzer import analyze_ast
from core.parser import parse_java


def _labels(code: str) -> dict[str, str]:
    ast = parse_java(code)["ast"]
    return {k: v for k, v in analyze_ast(ast).items() if "." in k}


def affected_methods(code: str, start: int, end: int) -> set[str]:
    """``Class.method`` whose span intersects lines [start, end]."""
    out: set[str] = set()
    for cls in (parse_java(code)["ast"] or {}).get("classes", []):
        for m in cls.get("methods", []) + cls.get("constructors", []):
            span = m.get("span") or {}
            s, e = span.get("start"), span.get("end")
            if s is not None and e is not None and s <= end and start <= e:
                out.add(f"{cls['name']}.{m['name']}")
    return out


def bigo_change(code: str, patched: str, start: int, end: int) -> tuple[dict[str, str], dict[str, str]]:
    """(before, after): methods touched by the patch plus any method whose label changed."""
    before_all, after_all = _labels(code), _labels(patched)
    names = affected_methods(code, start, end) | {
        k for k in before_all.keys() & after_all.keys() if before_all[k] != after_all[k]
    }
    names = {n for n in names if n in before_all and n in after_all}
    return {n: before_all[n] for n in names}, {n: after_all[n] for n in names}

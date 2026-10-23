"""Static Big-O estimation from loop nesting and recursion."""

from __future__ import annotations

import re

LOOP_TYPES = ("ForStatement", "WhileStatement", "DoStatement")
_SORT_CALLS = ("sort(", "Collections.sort", "Arrays.sort", ".sorted(")


def _children(stmt: dict):
    for key in ("body", "then", "else", "finally"):
        v = stmt.get(key)
        if isinstance(v, list):
            yield from v
    for case in stmt.get("cases", []) or []:
        yield from case.get("body", [])
    for c in stmt.get("catches", []) or []:
        yield from c.get("body", [])


def loop_depth(stmts: list[dict]) -> int:
    """Maximum loop nesting depth in a statement list."""
    best = 0
    for s in stmts:
        d = loop_depth(list(_children(s)))
        if s.get("type") in LOOP_TYPES:
            d += 1
        best = max(best, d)
    return best


def find_loops(stmts: list[dict], depth: int = 0, out: list | None = None) -> list[tuple[dict, int]]:
    """All loops with their nesting depth (outermost = 1)."""
    out = [] if out is None else out
    for s in stmts:
        d = depth + (1 if s.get("type") in LOOP_TYPES else 0)
        if s.get("type") in LOOP_TYPES:
            out.append((s, d))
        find_loops(list(_children(s)), d, out)
    return out


def _walk_exprs(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, str) and k in ("expression", "condition", "control", "initializer", "raw"):
                yield v
            elif isinstance(v, (dict, list)):
                yield from _walk_exprs(v)
    elif isinstance(o, list):
        for i in o:
            yield from _walk_exprs(i)


def is_recursive(method: dict) -> bool:
    name = method["name"]
    pat = re.compile(rf"(?<![\w.]){re.escape(name)}\s*\(|this\.{re.escape(name)}\s*\(")
    return any(pat.search(t) for t in _walk_exprs(method.get("body", [])))


def _loop_is_logarithmic(loop: dict) -> bool:
    """Loop whose variable is halved / doubled each iteration."""
    text = " ".join(
        [loop.get("condition", ""), loop.get("control", "")] + list(_walk_exprs(loop.get("body", [])))
    )
    return bool(re.search(r"[*/]=\s*2\b|<<=|>>=|=\s*\w+\s*[*/]\s*2\b", text))


def complexity_label(power: int, log: bool = False, rec: bool = False) -> str:
    if rec:
        return "O(?) рекурсия"
    if power == 0 and not log:
        return "O(1)"
    if power == 0 and log:
        return "O(log n)"
    base = "n" if power == 1 else f"n{'²³⁴⁵'[power - 2] if power <= 5 else '^' + str(power)}"
    return f"O({base}{' log n' if log else ''})"


def analyze_method(method: dict) -> str:
    body = method.get("body", [])
    loops = find_loops(body)
    depth = loop_depth(body)
    has_sort = any(any(s in t for s in _SORT_CALLS) for t in _walk_exprs(body))
    only_log = bool(loops) and all(_loop_is_logarithmic(l) for l, _ in loops)

    if is_recursive(method) and depth == 0:
        return "O(?) рекурсия"
    if only_log and depth == 1:
        return "O(log n)"
    power = depth
    if has_sort and power <= 1:
        return "O(n log n)"
    return complexity_label(power)


def analyze_ast(ast: dict) -> dict[str, str]:
    """Return {'Class.method': 'O(...)'} plus bare 'method' keys when unambiguous."""
    result: dict[str, str] = {}
    counts: dict[str, int] = {}
    for cls in ast.get("classes", []):
        for m in cls["methods"] + cls.get("constructors", []):
            result[f"{cls['name']}.{m['name']}"] = analyze_method(m)
            counts[m["name"]] = counts.get(m["name"], 0) + 1
    for cls in ast.get("classes", []):
        for m in cls["methods"]:
            if counts[m["name"]] == 1:
                result[m["name"]] = result[f"{cls['name']}.{m['name']}"]
    return result

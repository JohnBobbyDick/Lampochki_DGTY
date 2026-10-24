"""Call graph: which method calls which (inside a class and between classes)."""

from __future__ import annotations

import re

from models.schemas import GraphEdge, GraphNode

_CALL_RE = re.compile(r"(?:(\b[A-Za-z_]\w*(?:\([^()]*\))?)\s*\.\s*)?\b([A-Za-z_]\w*)\s*\(")


def all_classes(ast: dict) -> list[dict]:
    return ast.get("classes", [])


def method_key(cls: dict, method: dict) -> str:
    if cls["name"] in ("Module", ""):
        return method["name"]
    return f"{cls['name']}.{method['name']}"


def collect_calls(stmts) -> list[tuple[str | None, str]]:
    """Return (qualifier, method-name) pairs found in expression strings."""
    found: list[tuple[str | None, str]] = []

    def scan(text: str) -> None:
        for m in _CALL_RE.finditer(text):
            q, name = m.group(1), m.group(2)
            if name in ("if", "for", "while", "switch", "catch", "new", "return", "super", "this", "print", "input", "range", "len"):
                continue
            found.append((q, name))

    def walk(o) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and k in ("expression", "condition", "control", "initializer", "raw", "items"):
                    scan(v)
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(o, list):
            for i in o:
                walk(i)

    walk(stmts)
    return found


def resolve_calls(ast: dict) -> dict[str, set[str]]:
    """Map 'Class.method' -> set of 'Class.method' it (probably) calls."""
    classes = all_classes(ast)
    by_class = {c["name"]: {m["name"] for m in c["methods"]} for c in classes}
    result: dict[str, set[str]] = {}
    for cls in classes:
        for m in cls["methods"] + cls.get("constructors", []):
            key = method_key(cls, m)
            callees = result.setdefault(key, set())
            for qualifier, name in collect_calls(m.get("body", [])):
                if qualifier is None or qualifier in ("this", "super", "self"):
                    if name in by_class.get(cls["name"], set()):
                        callees.add(method_key(cls, {"name": name}))
                    elif "Module" in by_class and name in by_class["Module"]:
                        callees.add(name)
                elif qualifier in by_class and name in by_class[qualifier]:
                    callees.add(f"{qualifier}.{name}")
                elif qualifier == cls["name"] and name in by_class[cls["name"]]:
                    callees.add(f"{cls['name']}.{name}")
    return result


def build_call_graph(ast: dict, bigo: dict[str, str] | None = None) -> tuple[list[GraphNode], list[GraphEdge]]:
    bigo = bigo or {}
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    calls = resolve_calls(ast)
    for cls in all_classes(ast):
        for m in cls["methods"]:
            key = method_key(cls, m)
            snippet = f"{m.get('return_type', '')} {m['name']}(...)" if m.get("return_type") != "None" else f"def {m['name']}(...)"
            nodes.append(GraphNode(
                id=key,
                type="method",
                label=key,
                data={
                    "line_start": m.get("line_start"),
                    "line_end": (m.get("span") or {}).get("end", m.get("line_start")),
                    "code_snippet": snippet.strip(),
                    "big_o": bigo.get(key) or bigo.get(m["name"]) or bigo.get(f"{cls['name']}.{m['name']}"),
                },
            ))
    known = {n.id for n in nodes}
    i = 0
    for caller, callees in sorted(calls.items()):
        for callee in sorted(callees):
            if caller in known and callee in known:
                edges.append(GraphEdge(id=f"c{i}", source=caller, target=callee, type="normal", label="calls"))
                i += 1
    return nodes, edges

"""Suggest and build a decomposition of a monolithic class/module into several files.

Supports both Java and Python:
- In Java: static methods are moved into new classes (e.g. MathOps.java, Parser.java).
- In Python: functions are moved into separate modules (e.g. mathops.py, parser.py) and imported in main.py.
"""

from __future__ import annotations

import re

from core.call_graph import resolve_calls
from models.schemas import DecomposedFile, DecomposeResponse

# group name -> method-name prefixes (lower case)
HEURISTICS: list[tuple[str, tuple[str, ...]]] = [
    ("MathOps", ("factorial", "fib", "power", "pow", "gcd", "lcm", "sqrt", "abs", "prime")),
    ("Parser", ("parse", "read", "load", "tokenize", "decode", "extract", "split", "scan")),
    ("Printer", ("print", "format", "show", "display", "render", "report", "dump", "write", "log")),
    ("Analyzer", ("analy", "calc", "compute", "count", "find", "filter", "search", "merge", "sort",
                  "group", "aggregate", "validate", "check", "sum", "avg", "average", "min", "max",
                  "evaluate", "is", "has")),
    ("Storage", ("add", "remove", "delete", "save", "store", "put", "get", "update", "insert", "clear")),
]
FALLBACK = "Helpers"


def _group_of(name: str) -> str | None:
    low = name.lower()
    for group, prefixes in HEURISTICS:
        if low.startswith(prefixes):
            return group
    return None


def _comment_start(lines: list[str], start: int) -> int:
    """Pull in contiguous comment lines directly above a declaration (1-based)."""
    i = start - 1
    while i >= 1 and lines[i - 1].strip().startswith(("//", "/*", "*", "*/", "#")):
        i -= 1
    return i


def _uses(text: str, name: str) -> bool:
    return re.search(rf"(?<![\w.]){re.escape(name)}\b", text) is not None


def _imports_for(ast: dict, body: str) -> str:
    out = []
    for imp in ast.get("imports", []):
        if imp.get("wildcard") or imp.get("static") or _uses(body, imp["path"].split(".")[-1]):
            out.append(f"import {'static ' if imp.get('static') else ''}{imp['path']}{'.*' if imp.get('wildcard') else ''};")
    return "\n".join(out) + ("\n\n" if out else "")


def plan(ast: dict) -> tuple[dict, dict[str, list[dict]], list[dict], list[str]]:
    """Choose the monolith class and group its movable methods."""
    warnings: list[str] = []
    classes = ast.get("classes", [])
    if not classes:
        return {}, {}, [], ["Классы не найдены"]
    # the monolith: top-level (non-nested) class with the most methods
    nested = {i["name"] for c in classes for i in c.get("inner_classes", [])}
    top = [c for c in classes if c["name"] not in nested] or classes
    mono = max(top, key=lambda c: len(c.get("methods", [])))

    is_py = ast.get("language") == "python"
    calls = resolve_calls(ast)
    movable = [
        m for m in mono.get("methods", [])
        if (is_py or "static" in m.get("modifiers", [])) and m["name"] != "main"
    ]
    for m in mono.get("methods", []):
        if m not in movable and m["name"] != "main":
            warnings.append(f"Метод {m['name']} не static — оставлен в {mono['name']}")

    groups: dict[str, list[dict]] = {}
    unknown: list[dict] = []
    for m in movable:
        g = _group_of(m["name"])
        (groups.setdefault(g, []) if g else unknown).append(m)

    # unknown methods follow the group of their neighbours in the call graph
    for m in unknown:
        key = f"{mono['name']}.{m['name']}"
        neighbours = list(calls.get(key, []))
        neighbours += [k for k, v in calls.items() if key in v]
        votes: dict[str, int] = {}
        for n in neighbours:
            nm = n.split(".", 1)[-1]
            for g, ms in groups.items():
                if any(x["name"] == nm for x in ms):
                    votes[g] = votes.get(g, 0) + 1
        target = max(votes, key=votes.get) if votes else FALLBACK
        groups.setdefault(target, []).append(m)

    # a group needs at least 2 methods, otherwise merge into Helpers
    for g in [g for g, ms in groups.items() if len(ms) < 2 and g != FALLBACK]:
        groups.setdefault(FALLBACK, []).extend(groups.pop(g))
    return mono, groups, mono.get("inner_classes", []), warnings


def _decompose_python(code: str, ast: dict, mono: dict, groups: dict, warnings: list[str]) -> DecomposeResponse:
    lines = code.split("\n")
    move_map = {m["name"]: g for g, ms in groups.items() for m in ms}
    files: list[DecomposedFile] = []
    removed_spans: list[tuple[int, int]] = []

    for g, ms in groups.items():
        g_name = g.lower()
        parts = []
        for m in ms:
            s_idx = max(0, m["span"]["start"] - 1)
            e_idx = min(len(lines), m["span"]["end"])
            parts.append("\n".join(lines[s_idx:e_idx]))
            removed_spans.append((m["span"]["start"], m["span"]["end"]))
        content = "\n\n".join(parts) + "\n"
        files.append(DecomposedFile(name=f"{g_name}.py", methods=[m["name"] for m in ms], code=content))

    # Main facade
    main_lines = list(lines)
    for s, e in sorted(removed_spans, reverse=True):
        del main_lines[s - 1: e]

    imports_added = []
    for g, ms in groups.items():
        imports_added.append(f"from {g.lower()} import {', '.join(m['name'] for m in ms)}")
    import_header = "\n".join(imports_added) + "\n\n" if imports_added else ""
    facade_code = import_header + "\n".join(main_lines)
    files.insert(0, DecomposedFile(name="main.py", methods=[m["name"] for m in mono["methods"] if m["name"] not in move_map], code=facade_code))

    return DecomposeResponse(files=files, warnings=warnings)


def decompose(code: str, ast: dict) -> DecomposeResponse:
    mono, groups, inner, warnings = plan(ast)
    if not mono or len(groups) < 1:
        return DecomposeResponse(files=[], warnings=warnings + ["Нечего выделять"])

    if ast.get("language") == "python":
        return _decompose_python(code, ast, mono, groups, warnings)

    lines = code.split("\n")
    facade = mono["name"]
    taken = {facade} | {c["name"] for c in ast.get("classes", [])}
    for g in list(groups):
        if g in taken:
            new = g + "Service"
            while new in taken:
                new += "X"
            groups[new] = groups.pop(g)
    move_map = {m["name"]: g for g, ms in groups.items() for m in ms}
    static_fields = [f for f in mono.get("fields", []) if "static" in f.get("modifiers", [])]
    field_names = {f["name"] for f in static_fields}

    def rewrite(text: str) -> str:
        for name, g in move_map.items():
            text = re.sub(rf"\b{facade}\.{name}\s*\(", f"{g}.{name}(", text)
            text = re.sub(rf"(?<![\w.]){name}\s*\(", f"{g}.{name}(", text)
        return text

    def qualify_facade(text: str, method_names: set[str]) -> str:
        for fn in field_names:
            text = re.sub(rf"(?<![\w.]){fn}\b", f"{facade}.{fn}", text)
        for mn in method_names:
            text = re.sub(rf"(?<![\w.]){mn}\s*\(", f"{facade}.{mn}(", text)
        return text

    def method_text(m: dict) -> tuple[str, str]:
        start = _comment_start(lines, m["span"]["start"])
        chunk = lines[start - 1: m["span"]["end"]]
        bo = m.get("body_open")
        if not bo:
            return "", "\n".join(chunk)
        hdr_len = bo["line"] - start + 1
        header, body = chunk[:hdr_len], chunk[hdr_len:]
        header[-1], tail = header[-1][: bo["col"]], header[-1][bo["col"]:]
        return "\n".join(header), tail + "\n" + "\n".join(body)

    kept_static = {
        m["name"] for m in mono["methods"] if m["name"] not in move_map and "static" in m.get("modifiers", [])
    }
    files: list[DecomposedFile] = []

    # nested classes -> top-level files
    removed_spans: list[tuple[int, int]] = []
    for ic in inner:
        if not ic.get("span"):
            continue
        s, e = _comment_start(lines, ic["span"]["start"]), ic["span"]["end"]
        chunk = lines[s - 1: e]
        text = "\n".join(l[4:] if l.startswith("    ") else l for l in chunk)
        text = re.sub(r"^(\s*)(?:(public|private|protected)\s+)?static\s+", lambda m_: f"{m_.group(1)}", text, count=1, flags=re.M)
        text = re.sub(r"^(\s*)private\s+", r"\1", text, count=1)
        removed_spans.append((s, e))
        files.append(DecomposedFile(name=f"{ic['name']}.java", methods=[m["name"] for m in ic["methods"]],
                                    code=_imports_for(ast, text) + text + "\n"))

    # group files
    for g, ms in groups.items():
        parts = []
        for m in ms:
            hdr, bod = method_text(m)
            parts.append(hdr + qualify_facade(rewrite(bod), kept_static))
        body = "\n\n".join(parts)
        code_g = _imports_for(ast, body) + f"public class {g} {{\n" + body + "\n}\n"
        files.append(DecomposedFile(name=f"{g}.java", methods=[m["name"] for m in ms], code=code_g))
        for m in ms:
            removed_spans.append((_comment_start(lines, m["span"]["start"]), m["span"]["end"]))

    # fields referenced from moved code lose `private`
    facade_lines = list(lines)
    for s, e in sorted(removed_spans, reverse=True):
        del facade_lines[s - 1: e]
    facade_text = "\n".join(facade_lines)
    facade_text = rewrite(facade_text)
    for f in static_fields:
        if any(re.search(rf"(?<![\w.]){f['name']}\b", c.code) for c in files):
            facade_text = re.sub(rf"\bprivate(\s+(?:static|final|\s)*[\w<>\[\], ]+\s+{f['name']}\b)", r"\1", facade_text, count=1)

    files.insert(0, DecomposedFile(name=f"{facade}.java",
                                  methods=[m["name"] for m in mono["methods"] if m["name"] not in move_map],
                                  code=facade_text + "\n"))
    return DecomposeResponse(files=files, warnings=warnings)

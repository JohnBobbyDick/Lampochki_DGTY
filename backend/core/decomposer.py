"""Suggest and build a decomposition of a monolithic class/module into several files.

Supports both Java and Python:
- In Java: static methods are moved into new classes (e.g. MathOps.java, Parser.java).
- In Python: top-level functions (grouped like Java methods) and whole classes are moved into modules
  (e.g. mathops.py, store.py) and imported in main.py.
"""

from __future__ import annotations

import ast as pyast
import builtins
import keyword
import re
import symtable
import sys
from dataclasses import dataclass, field

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

    calls = resolve_calls(ast)
    movable = [
        m for m in mono.get("methods", [])
        if "static" in m.get("modifiers", []) and m["name"] != "main"
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


# ── Python ─────────────────────────────────────────────────────────────────────
# Units are top-level functions and whole classes (methods never leave their class). `main`, the code of the
# module itself and units relying on module globals that stay behind remain in the facade `main.py`. A module
# constant moves together with its users only when every user lands in the same module. Moved code is sliced
# from the source line by line, so it stays byte-identical.

_PY_DYNAMIC = ("__name__", "__file__", "__spec__", "__loader__", "__package__", "__doc__", "globals", "eval", "exec")
_PY_IMPURE = {"print", "input", "open", "exec", "eval", "breakpoint", "exit", "quit", "__import__"}
_PY_BUILTINS = set(dir(builtins))
_PY_DEFS = (pyast.FunctionDef, pyast.AsyncFunctionDef, pyast.ClassDef)
_PY_SCOPES = (pyast.Lambda, pyast.ListComp, pyast.SetComp, pyast.DictComp, pyast.GeneratorExp)


@dataclass(eq=False)
class _PyUnit:
    name: str
    kind: str                       # "func" | "class" | "const"
    index: int                      # position in the module body
    start: int                      # first line, 1-based (comments above and decorators included)
    end: int
    uses: set[str] = field(default_factory=set)     # module-level names it references
    fixed: bool = False             # never moves (main, redefined names…)
    target: str | None = None       # module name; None = stays in main.py

    @property
    def who(self) -> tuple[str, str]:
        return ("Класс", "оставлен") if self.kind == "class" else ("Функция", "оставлена")


def _snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def _py_names(nodes) -> set[str]:
    return {x.id for n in nodes if n is not None for x in pyast.walk(n) if isinstance(x, pyast.Name)}


def _py_header(node) -> list:
    """Parts of a def/class evaluated in the module scope (symtable files them under the module)."""
    if isinstance(node, pyast.ClassDef):
        return [*node.decorator_list, *node.bases, *(k.value for k in node.keywords)]
    a = node.args
    params = [x for x in (*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg) if x is not None]
    return [*node.decorator_list, *a.defaults, *a.kw_defaults, *(p.annotation for p in params), node.returns]


def _scope_globals(table) -> set[str]:
    out = {s.get_name() for s in table.get_symbols() if s.is_global()}
    for child in table.get_children():
        out |= _scope_globals(child)
    return out


def _declared_globals(table) -> set[str]:
    out = {s.get_name() for s in table.get_symbols() if s.is_declared_global()}
    for child in table.get_children():
        out |= _declared_globals(child)
    return out


def _import_names(stmt) -> set[str]:
    return {a.asname or a.name.split(".")[0] for a in stmt.names if a.name != "*"}


def _bound(stmt) -> set[str]:
    """Module-level names bound by a top-level statement."""
    if isinstance(stmt, _PY_DEFS):
        return {stmt.name}
    out: set[str] = set()

    def visit(n) -> None:
        if isinstance(n, _PY_DEFS):
            out.add(n.name)
            return
        if isinstance(n, _PY_SCOPES):
            return
        if isinstance(n, (pyast.Import, pyast.ImportFrom)):
            out.update(_import_names(n))
        elif isinstance(n, pyast.Name) and not isinstance(n.ctx, pyast.Load):
            out.add(n.id)
        elif isinstance(n, (pyast.ExceptHandler, pyast.MatchAs, pyast.MatchStar)) and n.name:
            out.add(n.name)
        elif isinstance(n, pyast.MatchMapping) and n.rest:
            out.add(n.rest)
        for c in pyast.iter_child_nodes(n):
            visit(c)

    visit(stmt)
    return out


def _render_import(stmt, keep: set[str]) -> str | None:
    """`import …` / `from … import …` with only the aliases in *keep* (star imports are always kept)."""
    names = [a for a in stmt.names if a.name == "*" or (a.asname or a.name.split(".")[0]) in keep]
    if not names:
        return None
    alias = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in names)
    if isinstance(stmt, pyast.Import):
        return f"import {alias}"
    return f"from {'.' * stmt.level}{stmt.module or ''} import {alias}"


def _reaches(edges: dict[str, set[str]], src: str, dst: str) -> bool:
    seen, todo = set(), [src]
    while todo:
        m = todo.pop()
        if m == dst:
            return True
        if m not in seen:
            seen.add(m)
            todo.extend(edges.get(m, ()))
    return False


def _decompose_python(code: str) -> DecomposeResponse:
    try:
        tree = pyast.parse(code)
        top = symtable.symtable(code, "main.py", "exec")
    except (SyntaxError, ValueError):
        return DecomposeResponse(files=[], warnings=["Нечего выделять"])
    lines = code.split("\n")
    body = tree.body
    tables = {(t.get_name(), t.get_lineno()): t for t in reversed(top.get_children())}
    counts: dict[str, int] = {}
    for s in body:
        for n in _bound(s):
            counts[n] = counts.get(n, 0) + 1
    module_bound = set(counts) | _declared_globals(top)

    future = [s for s in body if isinstance(s, pyast.ImportFrom) and s.module == "__future__"]
    imports = [s for s in body if isinstance(s, (pyast.Import, pyast.ImportFrom)) and s not in future]
    clean_imports = {n for s in imports for n in _import_names(s)}
    clean_imports = {n for n in clean_imports if counts[n] == sum(n in _import_names(s) for s in imports)}

    def first_line(i: int) -> int:
        s = body[i]
        return min([s.lineno] + [d.lineno for d in getattr(s, "decorator_list", [])])

    def alone(i: int) -> bool:
        prev_end = body[i - 1].end_lineno if i else 0
        next_start = first_line(i + 1) if i + 1 < len(body) else len(lines) + 1
        return prev_end < first_line(i) and body[i].end_lineno < next_start

    def start_with_comments(i: int) -> int:
        j, lo = first_line(i), (body[i - 1].end_lineno if i else 0)
        while j - 1 > lo and lines[j - 2].lstrip().startswith("#") and not lines[j - 2].startswith("#!") \
                and not re.match(r"#.*coding[:=]", lines[j - 2]):
            j -= 1
        return j

    units: list[_PyUnit] = []
    warnings: list[str] = []
    for i, s in enumerate(body):
        if isinstance(s, _PY_DEFS):
            table = tables.get((s.name, s.lineno))
            uses = _py_names(_py_header(s)) | (_scope_globals(table) if table else _py_names(s.body))
            u = _PyUnit(s.name, "class" if isinstance(s, pyast.ClassDef) else "func", i,
                        start_with_comments(i), s.end_lineno, uses)
            if s.name == "main":
                u.fixed = True
            elif counts[s.name] > 1 or not alone(i):
                u.fixed = True
                warnings.append(f"{u.who[0]} {s.name} определяется несколько раз — {u.who[1]} в main.py")
            else:
                dyn = sorted(n for n in uses & set(_PY_DYNAMIC) if n not in module_bound)
                if dyn:
                    u.fixed = True
                    warnings.append(f"{u.who[0]} {s.name} использует {dyn[0]} — {u.who[1]} в main.py")
            units.append(u)
            continue
        if isinstance(s, pyast.Assign) and len(s.targets) == 1:
            target = s.targets[0]
        elif isinstance(s, pyast.AnnAssign) and s.value is not None and s.simple:
            target = s.target
        else:
            continue
        if not isinstance(target, pyast.Name) or target.id.startswith("__") or counts[target.id] > 1 or not alone(i):
            continue
        parts = [s.value] + ([s.annotation] if isinstance(s, pyast.AnnAssign) else [])
        refs = _py_names(parts)
        if refs & _PY_IMPURE or not refs <= (_PY_BUILTINS | clean_imports) \
                or any(isinstance(x, (pyast.Await, pyast.Yield, pyast.YieldFrom, pyast.NamedExpr))
                       for p in parts for x in pyast.walk(p)):
            continue
        units.append(_PyUnit(target.id, "const", i, start_with_comments(i), s.end_lineno, refs))

    code_units = [u for u in units if u.kind != "const"]
    consts = [u for u in units if u.kind == "const"]
    funcs = [u for u in code_units if u.kind == "func" and not u.fixed]
    classes = [u for u in code_units if u.kind == "class" and not u.fixed]
    if not funcs and not classes:
        return DecomposeResponse(files=[], warnings=warnings + ["Нечего выделять"])

    # grouping: functions by name heuristics (+ call-graph neighbours), every class into its own module
    groups: dict[str, list[_PyUnit]] = {}
    unknown: list[_PyUnit] = []
    for u in funcs:
        g = _group_of(u.name)
        (groups.setdefault(g, []) if g else unknown).append(u)
    for u in unknown:
        votes: dict[str, int] = {}
        for v in funcs:
            if v is not u and (v.name in u.uses or u.name in v.uses):
                for g, ms in groups.items():
                    if v in ms:
                        votes[g] = votes.get(g, 0) + 1
        groups.setdefault(max(votes, key=votes.get) if votes else FALLBACK, []).append(u)
    for g in [g for g, ms in groups.items() if len(ms) < 2 and g != FALLBACK]:
        groups.setdefault(FALLBACK, []).extend(groups.pop(g))

    taken = set(sys.stdlib_module_names) | {"main", "__main__"}
    for s in imports:
        if isinstance(s, pyast.Import):
            taken |= {a.name.split(".")[0] for a in s.names}
        else:
            taken.add((s.module or "").split(".")[0])

    def module_name(base: str) -> str:
        name, k = base, 1
        while name in taken or keyword.iskeyword(name) or not name.isidentifier():
            name, k = f"{base}_mod{'' if k == 1 else k}", k + 1
        taken.add(name)
        return name

    for u in classes:
        u.target = module_name(_snake(u.name))
    for g, ms in groups.items():
        mod = module_name(g.lower())
        for u in ms:
            u.target = mod

    by_name = {u.name: u for u in units if counts.get(u.name) == 1}
    unit_index = {u.index for u in units}
    facade_refs = _py_names([s for i, s in enumerate(body) if i not in unit_index])
    kept_reason: dict[str, str] = {}

    def facade_uses() -> set[str]:
        return facade_refs | {n for u in code_units if u.target is None for n in u.uses}

    def demote(u: _PyUnit, why: str) -> None:
        u.target = None
        kept_reason[u.name] = why

    while True:
        refs = facade_uses()
        for c in consts:
            users = {u.target for u in code_units if c.name in u.uses}
            c.target = next(iter(users)) if c.name not in refs and len(users) == 1 else None
        changed = False
        for u in code_units:
            if u.target is None:
                continue
            for n in sorted(u.uses):
                v = by_name.get(n)
                if n == u.name or (v is None and n in clean_imports) or (v is not None and v.target == u.target)                         or (v is not None and v.kind != "const" and v.target is not None):
                    continue
                if v is not None and v.kind != "const" and v.target is None:
                    demote(u, f"{u.who[0]} {u.name} зависит от {n} из main.py — {u.who[1]} в main.py")
                elif (v is not None and v.kind == "const") or n in module_bound:
                    demote(u, f"{u.who[0]} {u.name} использует глобальное имя {n} — {u.who[1]} в main.py")
                else:
                    continue
                changed = True
                break
        if changed:
            continue
        # cyclic module dependencies: break one cycle per round (both directions of the chosen module pair)
        edges: dict[str, set[str]] = {}
        cross: list[tuple[_PyUnit, str]] = []
        for u in code_units:
            for n in sorted(u.uses):
                v = by_name.get(n)
                if u.target and v is not None and v.kind != "const" and v.target and v.target != u.target:
                    edges.setdefault(u.target, set()).add(v.target)
                    cross.append((u, v.target))
        cyclic = [(u, t) for u, t in cross if _reaches(edges, t, u.target)]
        if not cyclic:
            break
        u0, t0 = max(cyclic, key=lambda e: (e[0].kind == "func", e[0].index))
        m0 = u0.target
        for u, t in cyclic:
            if (u.target, t) in ((m0, t0), (t0, m0)):
                demote(u, f"{u.who[0]} {u.name} {u.who[1]} в main.py: циклическая зависимость модулей "
                          f"{m0}.py ↔ {t0}.py")

    moved = [u for u in units if u.target is not None]
    warnings += [kept_reason[u.name] for u in code_units if u.name in kept_reason]
    if not any(u.kind != "const" for u in moved):
        return DecomposeResponse(files=[], warnings=warnings + ["Нечего выделять"])

    modules: dict[str, list[_PyUnit]] = {}
    for u in sorted(moved, key=lambda x: x.index):
        modules.setdefault(u.target, []).append(u)
    future_line = (
        "from __future__ import " + ", ".join(dict.fromkeys(a.name for s in future for a in s.names))
        if future else None
    )

    def chunk(u: _PyUnit) -> str:
        return "\n".join(lines[u.start - 1: u.end]).rstrip()

    files: list[DecomposedFile] = []
    for mod, ms in modules.items():
        needed = {n for u in ms for n in u.uses}
        head = [r for s in imports if (r := _render_import(s, needed)) is not None]
        for other, others in modules.items():
            names = [v.name for v in others if other != mod and v.kind != "const" and v.name in needed]
            if names:
                head.append(f"from {other} import {', '.join(names)}")
        blocks = [b for b in (future_line, "\n".join(head)) if b]
        text = "\n\n\n".join(chunk(u) for u in ms) + "\n"
        if blocks:
            text = "\n\n".join(blocks) + "\n\n\n" + text
        files.append(DecomposedFile(name=f"{mod}.py", methods=[u.name for u in ms if u.kind != "const"], code=text))

    # facade: the source without moved units + imports of the moved units it still needs
    refs = facade_uses()
    facade_imports = []
    for mod, ms in modules.items():
        names = [u.name for u in ms if u.kind != "const" and u.name in refs]
        if names:
            facade_imports.append(f"from {mod} import {', '.join(names)}")
    removed: set[int] = set()
    for u in moved:
        removed.update(range(u.start, u.end + 1))
        j = u.end + 1
        while j <= len(lines) and not lines[j - 1].strip():
            removed.add(j)
            j += 1
    lead = 0
    while lead < len(body) and (isinstance(body[lead], (pyast.Import, pyast.ImportFrom)) or (
            lead == 0 and isinstance(body[0], pyast.Expr) and isinstance(body[0].value, pyast.Constant)
            and isinstance(body[0].value.value, str))):
        lead += 1
    after = body[lead - 1].end_lineno if lead else None
    before = start_with_comments(0) if not lead else None
    out: list[str] = []
    glue = None                     # index right after the inserted imports
    for ln, text in enumerate(lines, 1):
        if ln == before and facade_imports:
            out += facade_imports + ["", ""]
        if ln not in removed:
            out.append(text)
        if ln == after and facade_imports:
            out += facade_imports
            glue = len(out)
    if glue is not None:            # keep PEP 8 spacing between the imports and a following def/class
        k = glue
        while k < len(out) and not out[k].strip():
            k += 1
        if k < len(out) and out[k].startswith(("def ", "async def ", "class ", "@")) and k - glue < 2:
            out[glue:glue] = [""] * (2 - (k - glue))
    files.insert(0, DecomposedFile(name="main.py", code="\n".join(out).rstrip() + "\n",
                                   methods=[u.name for u in code_units if u.target is None]))
    return DecomposeResponse(files=files, warnings=warnings)


def decompose(code: str, ast: dict) -> DecomposeResponse:
    if ast.get("language") == "python":
        return _decompose_python(code)
    mono, groups, inner, warnings = plan(ast)
    if not mono or len(groups) < 1:
        return DecomposeResponse(files=[], warnings=warnings + ["Нечего выделять"])

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

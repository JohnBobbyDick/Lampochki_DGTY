"""Generate source code from AST or an edited CFG.

For Java: CFG edits update method statements; class diagrams yield skeletons.
For Python: CFG edits update indented Python functions and methods.
"""

from __future__ import annotations

import copy
import re

from core.cfg_builder import build_cfg_with_map

INDENT = "    "


class UnsupportedConstruct(Exception):
    """Raised when a graph structure cannot be turned back into valid code."""


# ---------------------------------------------------------------------------
# Java Statement rendering
# ---------------------------------------------------------------------------

def _end(text: str) -> str:
    text = text.rstrip()
    return text if text.endswith(";") else text + ";"


def render_stmts(stmts: list[dict], level: int) -> list[str]:
    lines: list[str] = []
    for s in stmts:
        lines.extend(render_stmt(s, level))
    return lines


def _block(stmts: list[dict], level: int) -> list[str]:
    return render_stmts(_flatten(stmts), level + 1)


def _flatten(stmts: list[dict]) -> list[dict]:
    res: list[dict] = []
    for s in stmts:
        if s.get("type") == "BlockStatement":
            res.extend(_flatten(s.get("body", [])))
        else:
            res.append(s)
    return res


def render_stmt(s: dict, level: int) -> list[str]:
    ind = INDENT * level
    t = s.get("type", "")

    if "_text" in s:
        return [ind + line for line in _end(s["_text"]).splitlines()]

    if t == "LocalVariableDeclaration":
        parts = []
        for d in s.get("declarators", []):
            parts.append(f"{d['name']} = {d['initializer']}" if d.get("initializer") else d["name"])
        mods = " ".join(s.get("modifiers", []))
        return [f"{ind}{mods + ' ' if mods else ''}{s['var_type']} {', '.join(parts)};"]
    if t == "StatementExpression":
        return [f"{ind}{s.get('expression', s.get('raw', ''))};"]
    if t == "ReturnStatement":
        return [f"{ind}return {s['expression']};" if s.get("expression") else f"{ind}return;"]
    if t == "ThrowStatement":
        return [f"{ind}throw {s['expression']};"]
    if t == "BreakStatement":
        return [f"{ind}break{' ' + s['label'] if s.get('label') else ''};"]
    if t == "ContinueStatement":
        return [f"{ind}continue{' ' + s['label'] if s.get('label') else ''};"]
    if t == "BlockStatement":
        return [ind + "{", *_block(s.get("body", []), level), ind + "}"]

    if t == "IfStatement":
        return _render_if(s, level, f"{ind}if")

    if t == "ForStatement":
        return [f"{ind}for ({s['control']}) {{", *_block(s.get("body", []), level), ind + "}"]
    if t == "WhileStatement":
        return [f"{ind}while ({s['condition']}) {{", *_block(s.get("body", []), level), ind + "}"]
    if t == "DoStatement":
        return [ind + "do {", *_block(s.get("body", []), level), f"{ind}}} while ({s['condition']});"]

    if t == "SwitchStatement":
        lines = [f"{ind}switch ({s['expression']}) {{"]
        for case in s.get("cases", []):
            for lbl in case.get("labels", []):
                lines.append(f"{ind}{INDENT}default:" if lbl == "default" else f"{ind}{INDENT}case {lbl}:")
            lines.extend(render_stmts(_flatten(case.get("body", [])), level + 2))
        lines.append(ind + "}")
        return lines

    if t == "TryStatement":
        res = s.get("resources")
        head = f"{ind}try ({'; '.join(res)}) {{" if res else f"{ind}try {{"
        lines = [head, *_block(s.get("body", []), level)]
        for c in s.get("catches", []):
            types = " | ".join(c.get("types", ["Exception"]))
            lines.append(f"{ind}}} catch ({types} {c.get('name', 'e')}) {{")
            lines.extend(_block(c.get("body", []), level))
        if s.get("finally"):
            lines.append(f"{ind}}} finally {{")
            lines.extend(_block(s["finally"], level))
        lines.append(ind + "}")
        return lines

    raise UnsupportedConstruct(f"Unsupported statement: {t}")


def _render_if(s: dict, level: int, prefix: str) -> list[str]:
    ind = INDENT * level
    lines = [f"{prefix} ({s['condition']}) {{", *_block(s.get("then", []), level)]
    els = _flatten(s.get("else", []))
    if len(els) == 1 and els[0].get("type") == "IfStatement" and "_text" not in els[0]:
        lines.extend(_render_if(els[0], level, f"{ind}}} else if"))
        return lines
    if els:
        lines.append(f"{ind}}} else {{")
        lines.extend(render_stmts(els, level + 1))
    lines.append(ind + "}")
    return lines


# ---------------------------------------------------------------------------
# Python Statement rendering
# ---------------------------------------------------------------------------

def render_python_stmts(stmts: list[dict], level: int) -> list[str]:
    lines: list[str] = []
    for s in stmts:
        lines.extend(render_python_stmt(s, level))
    return lines


def render_python_stmt(s: dict, level: int) -> list[str]:
    ind = INDENT * level
    t = s.get("type", "")

    if "_text" in s:
        return [ind + line for line in s["_text"].splitlines()]

    if t in ("StatementExpression", "LocalVariableDeclaration"):
        return [f"{ind}{s.get('expression', s.get('raw', 'pass'))}"]
    if t == "ReturnStatement":
        return [f"{ind}return {s['expression']}" if s.get("expression") else f"{ind}return"]
    if t == "ThrowStatement":
        return [f"{ind}raise {s['expression']}" if s.get("expression") else f"{ind}raise"]
    if t == "BreakStatement":
        return [f"{ind}break"]
    if t == "ContinueStatement":
        return [f"{ind}continue"]

    if t == "IfStatement":
        cond = s.get("condition", "True").rstrip(":")
        if cond.startswith("(") and cond.endswith(")"):
            cond = cond[1:-1]
        lines = [f"{ind}if {cond}:"]
        then_stmts = s.get("then", [])
        lines.extend(render_python_stmts(then_stmts, level + 1) if then_stmts else [f"{ind}{INDENT}pass"])
        if s.get("else"):
            lines.append(f"{ind}else:")
            lines.extend(render_python_stmts(s.get("else", []), level + 1))
        return lines

    if t == "ForStatement":
        ctrl = s.get("control", "item in items").rstrip(":")
        lines = [f"{ind}for {ctrl}:"]
        body = s.get("body", [])
        lines.extend(render_python_stmts(body, level + 1) if body else [f"{ind}{INDENT}pass"])
        return lines

    if t == "WhileStatement":
        cond = s.get("condition", "True").rstrip(":")
        if cond.startswith("(") and cond.endswith(")"):
            cond = cond[1:-1]
        lines = [f"{ind}while {cond}:"]
        body = s.get("body", [])
        lines.extend(render_python_stmts(body, level + 1) if body else [f"{ind}{INDENT}pass"])
        return lines

    if t == "TryStatement":
        lines = [f"{ind}try:"]
        body = s.get("body", [])
        lines.extend(render_python_stmts(body, level + 1) if body else [f"{ind}{INDENT}pass"])
        for c in s.get("catches", []):
            types = ", ".join(c.get("types", [])) or "Exception"
            name = f" as {c['name']}" if c.get("name") else ""
            lines.append(f"{ind}except {types}{name}:")
            cbody = c.get("body", [])
            lines.extend(render_python_stmts(cbody, level + 1) if cbody else [f"{ind}{INDENT}pass"])
        if s.get("finally"):
            lines.append(f"{ind}finally:")
            lines.extend(render_python_stmts(s.get("finally", []), level + 1))
        return lines

    return [f"{ind}pass"]


# ---------------------------------------------------------------------------
# Applying graph edits to a method
# ---------------------------------------------------------------------------

_PATTERNS = {
    "IfStatement": re.compile(r"^\s*if\s*(?:\((.*)\)|(.*))\s*$", re.S),
    "ForStatement": re.compile(r"^\s*for\s*(?:\((.*)\)|(.*))\s*$", re.S),
    "WhileStatement": re.compile(r"^\s*while\s*(?:\((.*)\)|(.*))\s*$", re.S),
    "SwitchStatement": re.compile(r"^\s*switch\s*(?:\((.*)\)|(.*))\s*$", re.S),
}
_FIELD_OF = {
    "IfStatement": "condition", "WhileStatement": "condition", "ForStatement": "control",
    "SwitchStatement": "expression",
}


def apply_edit(stmt: dict, text: str) -> None:
    """Mutate *stmt* so that it renders from the user-edited node *text*."""
    t = stmt.get("type", "")
    text = text.strip()
    if t in _PATTERNS:
        m = _PATTERNS[t].match(text)
        val = m.group(1) or m.group(2) if m else text
        stmt[_FIELD_OF[t]] = (val or text).rstrip(":").strip()
    elif t in ("ReturnStatement", "ThrowStatement"):
        kw = "return" if t == "ReturnStatement" else "throw|raise"
        stmt["expression"] = re.sub(rf"^({kw})\b\s*", "", text).rstrip(";").strip()
    elif "catches" not in stmt and "types" in stmt:  # a catch clause dict
        m = re.match(r"^(?:catch\s*\((.+?)\s+(\w+)\)|except\s+(.+?)(?:\s+as\s+(\w+))?:?)$", text)
        if m:
            types_str = m.group(1) or m.group(3) or "Exception"
            stmt["types"] = [x.strip() for x in types_str.replace("|", ",").split(",")]
            stmt["name"] = m.group(2) or m.group(4) or ""
    elif t in ("TryStatement", "DoStatement"):
        pass  # structural markers – not editable as text
    else:
        stmt["_text"] = text


def regenerate_method(method: dict, edits: dict[str, str], language: str = "java") -> tuple[list[str], list[str]]:
    """Return (body lines at level 0, ids of nodes actually changed)."""
    m = copy.deepcopy(method)
    _, _, stmt_of = build_cfg_with_map(m)
    changed: list[str] = []
    for nid, text in edits.items():
        stmt = stmt_of.get(nid)
        if stmt is None:
            continue
        apply_edit(stmt, text)
        changed.append(nid)

    if language == "python":
        return render_python_stmts(m.get("body", []), 0), changed
    return render_stmts(m.get("body", []), 0), changed


def splice_method(code: str, method: dict, body_lines: list[str], language: str = "java") -> str:
    """Replace the body of *method* in *code* with *body_lines* (level 0 lines)."""
    span = method.get("span")
    if not span:
        raise UnsupportedConstruct("Method span unknown")

    if language == "python":
        return _splice_python(code, span, body_lines)

    bo = method.get("body_open")
    if not bo:
        raise UnsupportedConstruct("Method body opening brace unknown")
    src = code.split("\n")
    first = src[span["start"] - 1]
    base_indent = first[: len(first) - len(first.lstrip())]
    header = src[span["start"] - 1: bo["line"]]
    header[-1] = header[-1][: bo["col"]]  # keep up to and including '{'
    inner = [(base_indent + INDENT + l) if l else "" for l in body_lines]
    new = [*header, *inner, base_indent + "}"]
    return "\n".join(src[: span["start"] - 1] + new + src[span["end"]:])


def _splice_python(code: str, span: dict, body_lines: list[str]) -> str:
    src = code.split("\n")
    start_idx = max(0, span["start"] - 1)
    end_idx = min(len(src), span["end"])

    # locate def ...: header line
    colon_idx = start_idx
    while colon_idx < len(src) and ":" not in src[colon_idx]:
        colon_idx += 1
    if colon_idx >= len(src):
        colon_idx = start_idx

    first = src[start_idx]
    base_indent = first[: len(first) - len(first.lstrip())]
    body_indent = base_indent + INDENT
    inner = [(body_indent + l) if l else "" for l in body_lines]
    if not inner:
        inner = [body_indent + "pass"]

    header_lines = src[start_idx : colon_idx + 1]
    return "\n".join(src[:start_idx] + header_lines + inner + src[end_idx:])


def find_method(ast: dict, name: str, class_name: str | None = None) -> tuple[dict, dict] | None:
    for cls in ast.get("classes", []):
        if class_name and cls["name"] != class_name and cls["name"] not in ("Module", ""):
            continue
        for m in cls.get("methods", []) + cls.get("constructors", []):
            if m["name"] == name:
                return cls, m
    return None


# ---------------------------------------------------------------------------
# Class skeletons
# ---------------------------------------------------------------------------

def generate_skeleton(ast: dict) -> str:
    out: list[str] = []
    for imp in ast.get("imports", []):
        out.append(f"import {'static ' if imp.get('static') else ''}{imp['path']}{'.*' if imp.get('wildcard') else ''};")
    if out:
        out.append("")
    for cls in ast.get("classes", []):
        head = " ".join([*cls["modifiers"], "class", cls["name"]])
        if cls.get("extends"):
            head += f" extends {cls['extends']}"
        if cls.get("implements"):
            head += " implements " + ", ".join(cls["implements"])
        out.append(head + " {")
        for f in cls["fields"]:
            out.append(f"{INDENT}{' '.join(f['modifiers'] + [f['type'], f['name']])};")
        if cls["fields"]:
            out.append("")
        for m in cls["methods"]:
            params = ", ".join(f"{p['type']} {p['name']}" for p in m["parameters"])
            sig = " ".join([*m["modifiers"], m["return_type"], f"{m['name']}({params})"])
            stub = "" if m["return_type"] == "void" else f"{INDENT*2}return {_default(m['return_type'])};"
            out += [f"{INDENT}{sig} {{", f"{INDENT*2}// TODO" if not stub else stub, f"{INDENT}}}", ""]
        out.append("}")
        out.append("")
    return "\n".join(out)


def _default(t: str) -> str:
    if t in ("int", "long", "short", "byte", "double", "float", "char"):
        return "0"
    if t == "boolean":
        return "false"
    return "null"

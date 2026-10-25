"""Generate source code from AST or an edited CFG.

For Java: CFG edits update method statements; class diagrams yield skeletons.
Python graph edits are span replacements in ``core.py_codegen``.
"""

from __future__ import annotations

import copy
import re

from core.cfg_builder import build_cfg_with_map
from core.streams import compose

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


def _dirty(s) -> bool:
    """Whether a statement dict (or anything inside it) was changed by ``apply_edit``."""
    if isinstance(s, dict):
        return any(k in s for k in ("_edited", "_text", "_deleted", "_orig_text")) or any(
            _dirty(v) for v in s.values() if isinstance(v, (dict, list)))
    if isinstance(s, list):
        return any(_dirty(v) for v in s)
    return False


def _verbatim(s: dict, ind: str) -> list[str]:
    """The statement's own source, re-indented to *ind* (continuation lines keep their offsets)."""
    lines = s["src"].split("\n")
    old = max(0, (s.get("col") or 1) - 1)
    rest = []
    for line in lines[1:]:
        cut = min(old, len(line) - len(line.lstrip(" ")))
        rest.append(ind + line[cut:] if line.strip() else "")
    return [ind + lines[0], *rest]


def render_stmt(s: dict, level: int) -> list[str]:
    ind = INDENT * level
    t = s.get("type", "")

    if s.get("src") and not _dirty(s):
        return _verbatim(s, ind)

    if "_text" in s:
        return [ind + line for line in _end(s["_text"]).splitlines()]

    if s.get("stream"):
        return [ind + line for line in _end(_compose_edited(s["stream"])).splitlines()]

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
    if t == "YieldStatement":
        return [f"{ind}yield {s['expression']};"]
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

    if t == "SwitchStatement" and s.get("arrow"):
        lines = [f"{ind}switch ({s['expression']}) {{"]
        for case in s.get("cases", []):
            labels = [lbl for lbl in case.get("labels", []) if lbl != "default"]
            head = f"case {', '.join(labels)}" if labels else "default"
            lines.append(f"{ind}{INDENT}{head} -> {{")
            lines.extend(render_stmts(_flatten(case.get("body", [])), level + 2))
            lines.append(f"{ind}{INDENT}}}")
        lines.append(ind + "}")
        return lines

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

    if s.get("src"):
        return _verbatim(s, ind)
    raise UnsupportedConstruct(f"Unsupported statement: {t}")


def _prefix_re(prefix: str) -> re.Pattern[str]:
    """Matches *prefix* at the start of a label, tolerant to whitespace differences."""
    chunks = prefix.split()
    pat = ""
    for i, chunk in enumerate(chunks):
        if i:
            word_gap = chunks[i - 1][-1:].isalnum() or chunks[i - 1][-1:] == "_"
            word_gap = word_gap and (chunk[:1].isalnum() or chunk[:1] == "_")
            pat += r"\s+" if word_gap else r"\s*"
        pat += re.escape(chunk)
    if chunks and (chunks[-1][-1].isalnum() or chunks[-1][-1] == "_"):
        pat += r"(?![\w$])"
    return re.compile(r"^\s*" + pat + r"\s*")


def _strip_suffix(text: str, suffix: str) -> str | None:
    """*text* without a trailing *suffix* (compared ignoring whitespace), or ``None``."""
    sq_text, sq_suffix = re.sub(r"\s+", "", text), re.sub(r"\s+", "", suffix)
    if not sq_suffix or not sq_text.endswith(sq_suffix):
        return None
    keep, pos = len(sq_text) - len(sq_suffix), 0
    while keep:
        if not text[pos].isspace():
            keep -= 1
        pos += 1
    return text[:pos].rstrip()


def _steps_suffix(ops: list[dict], terminal: dict | None, key: str) -> str:
    text = "".join("." + op.get(key, op["text"]) for op in ops)
    return text + ("." + terminal.get(key, terminal["text"]) if terminal else "")


_RETURN_HEAD = re.compile(r"^\s*return(?![\w$])")


def _has_head(text: str) -> bool:
    """Whether a source label starts with its own statement head: a leading `return` or a top-level
    assignment / declaration `=` (also `+=` etc.; not `==`, `!=`, `<=`, `>=`, not inside (), [], {}
    or string / char literals)."""
    if _RETURN_HEAD.match(text):
        return True
    depth, i, n = 0, 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "=" and depth == 0:
            nxt, prev = text[i + 1:i + 2], text[i - 1:i]
            if nxt != "=" and prev not in ("=", "!") and (prev not in ("<", ">") or text[i - 2:i] in ("<<", ">>")):
                return True
            i += 1 if nxt != "=" else 2
            continue
        i += 1
    return False


def _compose_edited(stream: dict) -> str:
    """`compose` of a possibly edited chain.

    Drops a prefix the user left in the source label, a whole chain pasted into the source label
    (its ops + terminal, as they are now or were before the edit) and deleted (emptied) ops. A source
    label with a different head of its own (`_has_head`) replaces the old prefix.
    """
    src, prefix = stream["source"]["text"], stream["prefix"]
    if prefix.strip():
        m = _prefix_re(prefix).match(src)
        if m:
            src = src[m.end():]
        elif _has_head(src):
            prefix = ""  # the user rewrote the head (`T q = `, `q = `, `return `): it replaces the old one
    ops, terminal = stream["ops"], stream.get("terminal")
    for key in ("text", "_orig_text"):
        cut = _strip_suffix(src, _steps_suffix(ops, terminal, key))
        if cut:
            src = cut
            break
    kept = [op for op in ops if not op.get("_deleted")]
    return compose({**stream, "prefix": prefix, "source": {**stream["source"], "text": src}, "ops": kept})


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
    stmt["_edited"] = True
    if t in ("StreamSource", "StreamOp", "StreamTerminal"):
        text = text.rstrip(";").strip()
        if t != "StreamSource":
            text = text.lstrip(".").strip()
        stmt.setdefault("_orig_text", stmt["text"])
        if not text:
            if t == "StreamOp":
                stmt["_deleted"] = True  # an emptied step is removed from the chain
            return  # an emptied source / terminal keeps its text
        stmt["text"] = text  # prefix / pasted chain in a source label are dropped by render_stmt
        return
    if t in _PATTERNS:
        m = _PATTERNS[t].match(text)
        val = m.group(1) or m.group(2) if m else text
        stmt[_FIELD_OF[t]] = (val or text).rstrip(":").strip()
    elif t in ("ReturnStatement", "ThrowStatement"):
        kw = "return" if t == "ReturnStatement" else "throw"
        stmt["expression"] = re.sub(rf"^({kw})\b\s*", "", text).rstrip(";").strip()
    elif "catches" not in stmt and "types" in stmt:  # a catch clause dict
        m = re.match(r"^catch\s*\((.+?)\s+(\w+)\)$", text)
        if m:
            stmt["types"] = [x.strip() for x in m.group(1).split("|")]
            stmt["name"] = m.group(2)
    elif t in ("TryStatement", "DoStatement"):
        pass  # structural markers – not editable as text
    else:
        stmt["_text"] = text


def _stream_owners(stmts: list, owners: dict[int, dict]) -> dict[int, dict]:
    """id(stream step dict) -> the statement holding that stream."""
    for s in stmts:
        if not isinstance(s, dict):
            continue
        st = s.get("stream")
        if st:
            for step in [st["source"], *st["ops"], st.get("terminal")]:
                if step:
                    owners[id(step)] = s
        for key in ("then", "else", "body", "finally"):
            if isinstance(s.get(key), list):
                _stream_owners(s[key], owners)
        for part in (s.get("cases") or []) + (s.get("catches") or []):
            _stream_owners(part.get("body", []), owners)
    return owners


def _replacement(stmt: dict) -> tuple[list[int], str] | None:
    """(source range, new text) for one edited statement / catch clause, or None if unknown."""
    t = stmt.get("type", "")
    if stmt.get("stream") and _dirty(stmt["stream"]):
        return (stmt["range"], _end(_compose_edited(stmt["stream"]))) if "range" in stmt else None
    if "_text" in stmt:
        return (stmt["range"], _end(stmt["_text"])) if "range" in stmt else None
    if t in _FIELD_OF:
        return (stmt["head_range"], stmt[_FIELD_OF[t]]) if "head_range" in stmt else None
    if t in ("ReturnStatement", "ThrowStatement"):
        return (stmt["range"], render_stmt(stmt, 0)[0]) if "range" in stmt else None
    if "catches" not in stmt and "types" in stmt:  # a catch clause
        if "head_range" not in stmt:
            return None
        return stmt["head_range"], f"{' | '.join(stmt['types'])} {stmt['name']}"
    return None


def splice_edits(code: str, method: dict, edits: dict[str, str]) -> tuple[str, list[str]] | None:
    """Apply node edits as text replacements of just the edited nodes' source ranges.

    Everything else in the file stays byte-identical. Returns None when some edited node has no
    known range (then the caller re-renders the method body)."""
    m = copy.deepcopy(method)
    _, _, stmt_of = build_cfg_with_map(m)
    owners = _stream_owners(m.get("body", []), {})
    targets: dict[int, dict] = {}
    changed: list[str] = []
    for nid, text in edits.items():
        stmt = stmt_of.get(nid)
        if stmt is None:
            continue
        apply_edit(stmt, text)
        changed.append(nid)
        target = owners.get(id(stmt), stmt)
        targets[id(target)] = target
    if not targets:
        return code, changed

    repl: list[tuple[int, int, str]] = []
    for target in targets.values():
        r = _replacement(target)
        if r is None:
            return None
        (a, b), text = r
        line_start = code.rfind("\n", 0, a) + 1
        indent = code[line_start:a] if not code[line_start:a].strip() else ""
        repl.append((a, b, text.replace("\n", "\n" + indent)))
    repl.sort(reverse=True)
    for (a, b, _), (a2, b2, _) in zip(repl[1:], repl):
        if b > a2:  # overlapping edits: let the full re-render sort them out
            return None
    for a, b, text in repl:
        code = code[:a] + text + code[b:]
    return code, changed


def regenerate_method(method: dict, edits: dict[str, str]) -> tuple[list[str], list[str]]:
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

    return render_stmts(m.get("body", []), 0), changed


def splice_method(code: str, method: dict, body_lines: list[str]) -> str:
    """Replace the body of *method* in *code* with *body_lines* (level 0 lines)."""
    span = method.get("span")
    if not span:
        raise UnsupportedConstruct("Method span unknown")

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

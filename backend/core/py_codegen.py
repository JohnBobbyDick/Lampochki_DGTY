"""Python graph edits as in-place replacement of source spans.

Each edited CFG node replaces only its own fragment of the source: a simple statement its ``span``,
a compound statement / ``except`` / ``case`` its ``header`` (the original keyword is kept, so the label
``if y`` on an ``elif`` node gives ``elif y``). Everything else — comments, blank lines, quotes,
docstrings — stays byte for byte. Columns are character offsets within a line.
"""

from __future__ import annotations

import re

from core.cfg_builder import build_cfg_with_map
from core.code_generator import UnsupportedConstruct

# header keywords whose text is editable; the alternatives a label may start with
_HEADER_KW = {
    "if": ("if", "elif"), "elif": ("elif", "if"), "for": ("for",), "while": ("while",),
    "with": ("with",), "match": ("match",), "case": ("case",), "except": ("except",),
}
_KW_RE = re.compile(r"(?:async\s+)?([A-Za-z_]\w*)")
_STMT_KW = {"ReturnStatement": "return", "ThrowStatement": "raise"}
_EOL_RE = re.compile(r"(\r\n|\r|\n)")


def _lines(code: str) -> tuple[list[str], list[str]]:
    """Split *code* into line contents and their line endings (kept for a byte-exact join)."""
    parts = _EOL_RE.split(code)  # only the line breaks Python itself counts (not str.splitlines)
    return parts[0::2], [*parts[1::2], ""]


def _slice(lines: list[str], rng: tuple[int, int, int, int]) -> str:
    line, col, end_line, end_col = rng
    if line == end_line:
        return lines[line - 1][col:end_col]
    parts = [lines[line - 1][col:], *lines[line:end_line - 1], lines[end_line - 1][:end_col]]
    return "\n".join(parts)


def _rng(d: dict) -> tuple[int, int, int, int]:
    return d["line"], d["col"], d["end_line"], d["end_col"]


def _header_text(original: str, label: str) -> str | None:
    """New header from *label*: the original keyword prefix + the label without its keyword."""
    m = _KW_RE.match(original)
    if not m or m.group(1) not in _HEADER_KW:
        return None  # try / finally / else — structural, not editable
    text = label.strip()
    if text.endswith(":"):
        text = text[:-1].rstrip()
    if not text:
        return None
    lm = _KW_RE.match(text)
    if lm and lm.group(1) in _HEADER_KW[m.group(1)]:
        text = text[lm.end():].lstrip()
    prefix = m.group(0)
    if text and _wrapped(original[m.end():].strip()) and not _wrapped(text):
        text = f"({text})"  # keep the original parentheses (needed by a multi-line condition)
    return f"{prefix} {text}" if text else prefix


def _wrapped(text: str) -> bool:
    """True when *text* is entirely enclosed in one matching pair of parentheses."""
    if not (text.startswith("(") and text.endswith(")")):
        return False
    depth = 0
    for i, ch in enumerate(text):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0:
            return i == len(text) - 1
    return False


def _indent_continuation(text: str, indent: str) -> str:
    first, *rest = text.split("\n")
    return "\n".join([first, *[(indent + l) if l.strip() else l for l in rest]])


def _replacement(lines: list[str], stmt: dict, label: str) -> tuple[tuple[int, int, int, int], str] | None:
    """(range, new text) for an edit of *stmt*, or None when the edit is ignored."""
    header, span = stmt.get("header"), stmt.get("span")
    if header:
        rng = _rng(header)
        new = _header_text(_slice(lines, rng), label)
    elif span:
        rng = _rng(span)
        if stmt.get("nested_def") or stmt.get("expression", "").startswith("class "):
            # def / class inside a body: only the header text is editable
            head = stmt.get("expression") or ""
            if not head or not _slice(lines, rng).startswith(head):
                raise UnsupportedConstruct("Заголовок вложенной функции или класса нельзя изменить через граф")
            *before, last = head.split("\n")
            end_line = rng[0] + len(before)
            end_col = (rng[1] if not before else 0) + len(last)
            rng = (rng[0], rng[1], end_line, end_col)
            new = label.strip().removesuffix(":").rstrip() or None
        else:
            new = label.strip() or "pass"
            kw = _STMT_KW.get(stmt.get("type", ""))
            if kw and new != "pass" and not re.match(rf"{kw}\b", new):
                new = f"{kw} {new}"  # as in Java: the label may omit the keyword
    else:
        return None
    if new is None:
        return None
    first = lines[rng[0] - 1]
    new = _indent_continuation(new, first[: len(first) - len(first.lstrip())])
    return rng, new


def apply_edits(code: str, method: dict, edits: dict[str, str]) -> tuple[str, list[str]]:
    """Apply node label *edits* of *method* to *code*; return (new code, ids of nodes actually changed)."""
    nodes, _, stmt_of = build_cfg_with_map(method)
    labels = {n.id: n.label for n in nodes}
    lines, ends = _lines(code)
    planned: list[tuple[tuple[int, int, int, int], str, str]] = []
    for nid, label in edits.items():
        stmt = stmt_of.get(nid)
        if label is not None:
            label = _EOL_RE.sub("\n", str(label))
        if stmt is None or label is None or label == labels.get(nid):
            continue
        rep = _replacement(lines, stmt, str(label))
        if rep is None or rep[1] == _slice(lines, rep[0]):
            continue
        planned.append((rep[0], rep[1], nid))

    planned.sort(key=lambda p: p[0][:2], reverse=True)  # bottom-up: earlier ranges keep their offsets
    changed: list[str] = []
    bound: tuple[int, int] | None = None  # start of the last applied range
    for (line, col, end_line, end_col), new, nid in planned:
        if bound is not None and (end_line, end_col) > bound:
            continue  # overlaps an edit below it
        bound = (line, col)
        head, tail = lines[line - 1][:col], lines[end_line - 1][end_col:]
        new_lines = (head + new + tail).split("\n")
        lines[line - 1:end_line] = new_lines
        ends[line - 1:end_line] = [ends[line - 1]] * (len(new_lines) - 1) + [ends[end_line - 1]]
        changed.append(nid)
    changed.reverse()
    return "".join(l + e for l, e in zip(lines, ends)), changed

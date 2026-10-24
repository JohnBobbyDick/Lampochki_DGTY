"""Token-level parsing of boolean conditions (no javac).

All indices are positions in the javalang token list; ranges are half-open [a, b).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

_OPEN = {"(", "[", "{"}
_CLOSE = {")", "]", "}"}
_REL = {"<", "<=", ">", ">=", "==", "!="}
_ASSIGN = {"=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=", ">>>="}
_FORBIDDEN = _ASSIGN | {"?", ":", "instanceof", "&", "|", "^", "->", "new"}
# binary operators that make an expression non-primary (for `!` handling)
_BINARY = _REL | _FORBIDDEN | {
    "+", "-", "*", "/", "%", "<<", ">>", ">>>", "&&", "||",
}
_TERNARY_STOP = {",", ";", "=", ":", "?", "->", "return", "throw"} | _ASSIGN


@dataclass
class Cond:
    kind: Literal["or", "and", "not", "paren", "leaf"]
    a: int
    b: int
    children: list["Cond"] = field(default_factory=list)


def _v(tokens: list, i: int) -> str:
    return tokens[i].value


def _top_level(tokens: list, a: int, b: int):
    """Yield (index, value) of tokens at nesting depth 0 within [a, b)."""
    depth = 0
    for i in range(a, b):
        v = _v(tokens, i)
        if v in _CLOSE:
            depth -= 1
        if depth == 0:
            yield i, v
        if v in _OPEN:
            depth += 1


def _split(tokens: list, a: int, b: int, op: str) -> list[tuple[int, int]]:
    parts, start = [], a
    for i, v in _top_level(tokens, a, b):
        if v == op:
            parts.append((start, i))
            start = i + 1
    if not parts:
        return []
    parts.append((start, b))
    return parts


def _closing_paren(tokens: list, i: int, b: int) -> int | None:
    depth = 0
    for j in range(i, b):
        v = _v(tokens, j)
        if v in _OPEN:
            depth += 1
        elif v in _CLOSE:
            depth -= 1
            if depth == 0:
                return j
    return None


def _is_group(tokens: list, a: int, b: int) -> bool:
    """[a, b) is one parenthesised group not preceded by an identifier/call."""
    if b - a < 2 or _v(tokens, a) != "(" or _closing_paren(tokens, a, b) != b - 1:
        return False
    if a > 0:
        prev = tokens[a - 1]
        pv = prev.value
        if pv in (")", "]", ">") or type(prev).__name__ == "Identifier":
            return False
    return True


def parse_condition(tokens: list, a: int, b: int) -> Cond:
    for op, kind in (("||", "or"), ("&&", "and")):
        parts = _split(tokens, a, b, op)
        if parts:
            return Cond(kind, a, b, [parse_condition(tokens, x, y) for x, y in parts])
    if b - a >= 2 and _v(tokens, a) == "!":
        ra = a + 1
        if _is_group(tokens, ra, b):
            return Cond("not", a, b, [parse_condition(tokens, ra, b)])
        if not any(v in _BINARY for _, v in _top_level(tokens, ra, b)):
            return Cond("not", a, b, [parse_condition(tokens, ra, b)])
        return Cond("leaf", a, b)
    if _is_group(tokens, a, b):
        inner = [v for _, v in _top_level(tokens, a + 1, b - 1)]
        if "?" in inner or b - a == 2:
            return Cond("leaf", a, b)
        return Cond("paren", a, b, [parse_condition(tokens, a + 1, b - 1)])
    return Cond("leaf", a, b)


def has_logic(c: Cond) -> bool:
    if c.kind in ("or", "and", "not"):
        return True
    return any(has_logic(ch) for ch in c.children)


def leaves(c: Cond) -> list[Cond]:
    if c.kind == "leaf":
        return [c]
    out: list[Cond] = []
    for ch in c.children:
        out.extend(leaves(ch))
    return out


def split_relation(tokens: list, a: int, b: int) -> tuple[int, str, int] | None:
    rels = []
    for i, v in _top_level(tokens, a, b):
        if v in _FORBIDDEN:
            return None
        if v in _REL:
            rels.append(i)
    if len(rels) != 1:
        return None
    i = rels[0]
    if i == a or i == b - 1:
        return None
    return i, _v(tokens, i), b


def ternary_conditions(tokens: list, a: int, b: int) -> list[tuple[int, int]]:
    out = []
    for i in range(a, b):
        if _v(tokens, i) != "?":
            continue
        if i + 1 < b and _v(tokens, i + 1) in ("extends", "super", ">", ","):
            continue
        depth, start = 0, a
        for j in range(i - 1, a - 1, -1):
            v = _v(tokens, j)
            if v in _CLOSE:
                depth += 1
            elif v in _OPEN:
                if depth == 0:
                    start = j + 1
                    break
                depth -= 1
            elif depth == 0 and v in _TERNARY_STOP:
                start = j + 1
                break
        if start < i:
            out.append((start, i))
    return out

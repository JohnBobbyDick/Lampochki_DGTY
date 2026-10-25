"""Token-based source spans for declarations (methods, constructors, classes).

javalang only gives the position of the first non-modifier token of a
declaration, so spans (including annotations/modifiers and the closing brace)
are recovered from the token stream.
"""

from __future__ import annotations

import javalang


def tokenize(code: str) -> list:
    try:
        return list(javalang.tokenizer.tokenize(code))
    except Exception:  # noqa: BLE001
        return []


def declaration_span(tokens: list, line: int, col: int) -> dict | None:
    """Return {start, end, start_tok, end_tok, body_start_tok} for a declaration
    whose first non-modifier token sits at (line, col)."""
    idx = None
    for i, t in enumerate(tokens):
        if t.position and t.position.line == line and t.position.column == col:
            idx = i
            break
    if idx is None:
        return None

    # walk back over modifiers / annotations
    start = idx
    while start > 0:
        prev = tokens[start - 1]
        if prev.value in (";", "{", "}"):
            break
        start -= 1

    # find the opening brace of the body (or ';' for abstract/interface methods)
    depth_paren = 0
    j = idx
    body_start = None
    while j < len(tokens):
        v = tokens[j].value
        if v == "(":
            depth_paren += 1
        elif v == ")":
            depth_paren -= 1
        elif depth_paren == 0 and v == "{":
            body_start = j
            break
        elif depth_paren == 0 and v == ";":
            return _result(tokens, start, j, None)
        j += 1
    if body_start is None:
        return None

    depth = 0
    k = body_start
    while k < len(tokens):
        v = tokens[k].value
        if v == "{":
            depth += 1
        elif v == "}":
            depth -= 1
            if depth == 0:
                return _result(tokens, start, k, body_start)
        k += 1
    return None


def _result(tokens: list, s: int, e: int, body_start: int | None) -> dict:
    return {
        "start": tokens[s].position.line,
        "end": tokens[e].position.line,
        "start_tok": s,
        "end_tok": e,
        "body_start_tok": body_start,
    }


# ---------------------------------------------------------------------------
# Statement ranges (token indexes / char offsets) for span-based code edits
# ---------------------------------------------------------------------------

_OPEN, _CLOSE = "([{", ")]}"
_DECL_HEADS = ("class", "interface", "enum")


def match_close(tokens: list, i: int) -> int:
    """Index of the bracket closing the one at *i* (any of ``([{``), or the last token."""
    depth = 0
    for j in range(i, len(tokens)):
        v = tokens[j].value
        if v in _OPEN:
            depth += 1
        elif v in _CLOSE:
            depth -= 1
            if depth == 0:
                return j
    return len(tokens) - 1


def paren_after(tokens: list, i: int) -> tuple[int, int] | None:
    """(open, close) token indexes of the first ``(`` … ``)`` at or after *i*."""
    for j in range(i, min(i + 8, len(tokens))):
        if tokens[j].value == "(":
            return j, match_close(tokens, j)
    return None


def _to_semicolon(tokens: list, i: int) -> int:
    depth = 0
    for j in range(i, len(tokens)):
        v = tokens[j].value
        if v in _OPEN:
            depth += 1
        elif v in _CLOSE:
            depth -= 1
        elif v == ";" and depth == 0:
            return j
    return len(tokens) - 1


def statement_end(tokens: list, i: int) -> int:
    """Index of the last token of the Java statement that starts at token *i*."""
    n = len(tokens)
    v = tokens[i].value
    nxt = tokens[i + 1].value if i + 1 < n else ""
    if nxt == ":" and v not in ("default", "case") and tokens[i].__class__.__name__ == "Identifier":
        return statement_end(tokens, i + 2)                      # labeled statement
    if v == "{":
        return match_close(tokens, i)
    if v == "if":
        _, close = paren_after(tokens, i) or (i, i)
        j = statement_end(tokens, close + 1)
        if j + 1 < n and tokens[j + 1].value == "else":
            return statement_end(tokens, j + 2)
        return j
    if v in ("for", "while", "synchronized"):
        _, close = paren_after(tokens, i) or (i, i)
        return statement_end(tokens, close + 1)
    if v == "switch" and nxt == "(":
        close = match_close(tokens, i + 1)
        if close + 1 < n and tokens[close + 1].value == "{":
            end = match_close(tokens, close + 1)
            # `switch (x) { … }.foo();` would be an expression statement; a statement ends at its brace
            return end
        return _to_semicolon(tokens, i)
    if v == "do":
        j = statement_end(tokens, i + 1)
        return _to_semicolon(tokens, j + 1)
    if v == "try":
        j = i + 1
        if j < n and tokens[j].value == "(":
            j = match_close(tokens, j) + 1
        j = match_close(tokens, j)                               # the try block
        while j + 1 < n and tokens[j + 1].value == "catch":
            _, close = paren_after(tokens, j + 1) or (j + 1, j + 1)
            j = match_close(tokens, close + 1)
        if j + 1 < n and tokens[j + 1].value == "finally":
            j = match_close(tokens, j + 2)
        return j
    # local class / interface / enum / record (possibly after modifiers and annotations)
    k = i
    while k < n and (tokens[k].__class__.__name__ in ("Modifier", "Annotation")
                     or tokens[k].value in ("sealed", "non", "-")):
        k += 2 if tokens[k].value == "@" else 1
    if k < n and (tokens[k].value in _DECL_HEADS
                  or (tokens[k].value == "record" and k + 2 < n and tokens[k + 2].value in ("(", "<"))):
        for j in range(k, n):
            if tokens[j].value == "{":
                return match_close(tokens, j)
    return _to_semicolon(tokens, i)


class Offsets:
    """Maps javalang tokens to char offsets in the original code.

    javalang positions refer to the text after ``\\uXXXX`` escapes are decoded; with such escapes
    the mapping is not attempted (``ok`` is False) and callers fall back to non-span behaviour."""

    def __init__(self, code: str, tokens: list):
        self.tokens = tokens
        self.ok = "\\u" not in code and bool(tokens)
        self.line_starts = [0]
        for i, ch in enumerate(code):
            if ch == "\n":
                self.line_starts.append(i + 1)
        self.at = {(t.position.line, t.position.column): i for i, t in enumerate(tokens) if t.position}

    def index(self, line: int | None, col: int | None) -> int | None:
        return self.at.get((line, col)) if line and col else None

    def start(self, i: int) -> int:
        p = self.tokens[i].position
        return self.line_starts[p.line - 1] + p.column - 1

    def end(self, i: int) -> int:
        return self.start(i) + len(self.tokens[i].value)

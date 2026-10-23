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

"""Stream API chains: recognising `src.stream().op(…)….terminal(…)` in a statement.

`stream_of` turns a javalang expression into the `stream` field of a statement dict (or ``None``);
`compose` renders that field back. Invariant: ``compose(stream) == prefix + text of the expression``,
i.e. the usual statement text without ``;`` — otherwise the chain is not decomposed.
"""

from __future__ import annotations

from typing import Any

from javalang.tree import MemberReference, MethodInvocation, This

# Calls that start a stream: `.stream()` / `.parallelStream()` on anything, or static factories.
SOURCE_CALLS = frozenset({"stream", "parallelStream"})
STATIC_SOURCES: dict[str, frozenset[str]] = {
    "Arrays": frozenset({"stream"}),
    "Stream": frozenset({"of", "iterate", "generate"}),
    "IntStream": frozenset({"range", "rangeClosed", "of"}),
    "LongStream": frozenset({"range", "rangeClosed", "of"}),
    "DoubleStream": frozenset({"range", "rangeClosed", "of"}),
}
STREAM_OPS = frozenset({
    "filter", "map", "mapToInt", "mapToLong", "mapToDouble", "mapToObj", "flatMap",
    "sorted", "distinct", "limit", "skip", "peek", "boxed",
})
TERMINALS = frozenset({
    "collect", "forEach", "forEachOrdered", "reduce", "count", "sum", "min", "max", "average",
    "anyMatch", "allMatch", "noneMatch", "findFirst", "findAny", "toArray",
})


def compose(stream: dict) -> str:
    text = stream["prefix"] + stream["source"]["text"]
    text += "".join("." + op["text"] for op in stream["ops"])
    if stream.get("terminal"):
        text += "." + stream["terminal"]["text"]
    return text


def _line(node: Any, fallback: int | None) -> int | None:
    pos = getattr(node, "position", None)
    return pos.line if pos else fallback


def _is_source_call(call: MethodInvocation) -> bool:
    if not call.qualifier:
        return False
    if call.member in SOURCE_CALLS:
        return True  # `x.stream()`, `Arrays.stream(a)`, `a.b.parallelStream()`
    owner = call.qualifier.rsplit(".", 1)[-1]
    return call.member in STATIC_SOURCES.get(owner, frozenset())


def stream_of(expr: Any, prefix: str, stmt_line: int | None) -> dict | None:
    """The `stream` field for statement ``prefix + expr`` or ``None`` if `expr` is not a chain."""
    from core.parser import _args_text, _expr_to_str, _selector_text

    if not isinstance(expr, (MethodInvocation, MemberReference, This)):
        return None
    if getattr(expr, "postfix_operators", None):
        return None
    selectors = list(getattr(expr, "selectors", None) or [])
    pre = "".join(getattr(expr, "prefix_operators", None) or [])
    full = _expr_to_str(expr)
    sel_texts = [_selector_text(s) for s in selectors]
    core_len = len(full) - len(pre) - sum(len(t) for t in sel_texts)
    if not full.startswith(pre) or core_len <= 0:
        return None
    core = full[len(pre):len(pre) + core_len]

    # Where the source ends: the expression's own call, or the first `.stream()` selector.
    if isinstance(expr, MethodInvocation) and _is_source_call(expr):
        start, src_node = 0, expr
    else:
        idx = next((i for i, s in enumerate(selectors)
                    if isinstance(s, MethodInvocation) and s.member in SOURCE_CALLS), None)
        if idx is None:
            return None
        start, src_node = idx + 1, selectors[idx]
    source = {"type": "StreamSource", "text": core + "".join(sel_texts[:start]),
              "line": _line(src_node, stmt_line)}

    ops: list[dict] = []
    terminal: dict | None = None
    i = start
    while i < len(selectors):
        s = selectors[i]
        if not isinstance(s, MethodInvocation):
            return None
        args = _args_text(s)
        if s.member in STREAM_OPS:
            ops.append({"type": "StreamOp", "name": s.member, "args": args,
                        "text": f"{s.member}({args})", "line": _line(s, stmt_line)})
            i += 1
            continue
        if s.member in TERMINALS:
            tail = "".join(sel_texts[i + 1:])
            terminal = {"type": "StreamTerminal", "name": s.member, "args": args, "tail": tail,
                        "text": f"{s.member}({args}){tail}", "line": _line(s, stmt_line)}
            break
        return None  # unknown method between source and terminal
    if not ops and terminal is None:
        return None

    stream = {"prefix": prefix + pre, "source": source, "ops": ops, "terminal": terminal}
    if compose(stream) != prefix + full:
        return None
    return stream

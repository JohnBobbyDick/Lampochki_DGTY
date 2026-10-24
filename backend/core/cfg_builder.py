"""Control Flow Graph (CFG) builder for Java methods.

Converts the parsed method body (list[dict]) produced by ``core.parser``
into a list of ``GraphNode`` / ``GraphEdge`` pairs that the front-end can
render.  Node ids are deterministic (``n0``, ``n1`` …) so that the same source
always yields the same ids; ``build_cfg_with_map`` additionally returns the
node-id → statement-dict mapping used by the code generator.
"""

from __future__ import annotations

from typing import Any

from core.streams import compose
from models.schemas import GraphEdge, GraphNode

# A dangling exit of a processed fragment: (source node id, edge type, edge label)
Tail = tuple[str, str, str]


def _plain(src: str) -> Tail:
    return (src, "normal", "")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_cfg(method_ast: dict) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Build a control-flow graph for a single method."""
    nodes, edges, _ = build_cfg_with_map(method_ast)
    return nodes, edges


def build_cfg_with_map(
    method_ast: dict,
) -> tuple[list[GraphNode], list[GraphEdge], dict[str, dict]]:
    """Like :func:`build_cfg` but also returns ``node id -> statement dict``."""
    builder = _CFGBuilder(method_ast)
    builder.build()
    return builder.nodes, builder.edges, builder.stmt_of


def max_line(stmt: Any, default: int | None = None) -> int | None:
    """Largest source line mentioned anywhere inside a statement dict."""
    best = default
    if isinstance(stmt, dict):
        for k, v in stmt.items():
            if k == "line" and isinstance(v, int):
                best = v if best is None else max(best, v)
            elif isinstance(v, (dict, list)):
                best = max_line(v, best)
    elif isinstance(stmt, list):
        for v in stmt:
            best = max_line(v, best)
    return best


# ---------------------------------------------------------------------------
# Internal builder
# ---------------------------------------------------------------------------

class _CFGBuilder:
    """Stateful builder that walks statement dicts and emits graph elements."""

    def __init__(self, method_ast: dict) -> None:
        self.method = method_ast
        self.nodes: list[GraphNode] = []
        self.edges: list[GraphEdge] = []
        self.stmt_of: dict[str, dict] = {}
        self._end_id = ""
        # stack of enclosing breakable/continuable constructs
        self._ctx: list[dict[str, Any]] = []

    # -- helpers -----------------------------------------------------------

    def _add_node(
        self,
        ntype: str,
        label: str,
        *,
        stmt: dict | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        code_snippet: str | None = None,
    ) -> GraphNode:
        nid = f"n{len(self.nodes)}"
        if stmt is not None:
            line_start = line_start if line_start is not None else stmt.get("line")
            line_end = line_end if line_end is not None else line_start
        node = GraphNode(
            id=nid,
            type=ntype,
            label=label,
            data={
                "line_start": line_start,
                "line_end": line_end if line_end is not None else line_start,
                "code_snippet": code_snippet if code_snippet is not None else label,
            },
        )
        self.nodes.append(node)
        if stmt is not None:
            self.stmt_of[nid] = stmt
        return node

    def _add_edge(self, source: str, target: str, etype: str = "normal", label: str = "") -> GraphEdge:
        edge = GraphEdge(id=f"e{len(self.edges)}", source=source, target=target, type=etype, label=label)
        self.edges.append(edge)
        return edge

    def _connect(self, tails: list[Tail], target: str) -> None:
        for src, etype, label in tails:
            self._add_edge(src, target, etype, label)

    # -- main build --------------------------------------------------------

    def build(self) -> None:
        start = self._add_node("start", "START", line_start=self.method.get("line_start"))
        end = self._add_node("end", "END")
        self._end_id = end.id

        body: list[dict] = self.method.get("body", [])
        tails = self._process_block(body, [_plain(start.id)])
        self._connect(tails, end.id)

    # -- block processing --------------------------------------------------

    def _process_block(self, stmts: list[dict], tails: list[Tail]) -> list[Tail]:
        for stmt in stmts:
            if not tails:  # unreachable code after return/throw/break
                break
            tails = self._process_stmt(stmt, tails)
        return tails

    def _process_stmt(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        stype = stmt.get("type", "")
        handlers = {
            "IfStatement": self._process_if,
            "ForStatement": self._process_loop,
            "WhileStatement": self._process_loop,
            "DoStatement": self._process_do,
            "SwitchStatement": self._process_switch,
            "TryStatement": self._process_try,
            "ReturnStatement": self._process_return,
            "ThrowStatement": self._process_throw,
            "BreakStatement": self._process_break,
            "ContinueStatement": self._process_continue,
        }
        if stype == "BlockStatement":
            return self._process_block(stmt.get("body", []), tails)
        handler = handlers.get(stype)
        if handler:
            return handler(stmt, tails)
        return self._process_generic(stmt, tails)

    # -- generic -----------------------------------------------------------

    def _process_generic(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        if stmt.get("stream"):
            return self._process_stream(stmt, tails)
        snippet = _stmt_snippet(stmt)
        node = self._add_node(
            "statement", snippet[:60], stmt=stmt, line_end=max_line(stmt), code_snippet=snippet,
        )
        self._connect(tails, node.id)
        return [_plain(node.id)]

    # -- stream pipelines ---------------------------------------------------

    def _process_stream(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        """One node per pipeline part: source -> ops -> terminal (labels are not truncated)."""
        st = stmt["stream"]
        src = st["source"]
        node = self._add_node(
            "stream-source", st["prefix"] + src["text"], stmt=src,
            line_start=src.get("line") or stmt.get("line"), code_snippet=compose(st),
        )
        self._connect(tails, node.id)
        parts = [("stream-op", op) for op in st["ops"]]
        if st.get("terminal"):
            parts.append(("stream-terminal", st["terminal"]))
        for ntype, part in parts:
            nxt = self._add_node(ntype, part["text"], stmt=part, line_start=part.get("line") or stmt.get("line"))
            self._add_edge(node.id, nxt.id)
            node = nxt
        return [_plain(node.id)]

    # -- if / else ---------------------------------------------------------

    def _process_if(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        cond_text = stmt.get("condition", "?")
        cond = self._add_node(
            "condition", f"if ({cond_text})", stmt=stmt, code_snippet=f"if ({cond_text})",
        )
        self._connect(tails, cond.id)

        out: list[Tail] = []
        then_body = stmt.get("then", [])
        else_body = stmt.get("else", [])

        out.extend(self._process_block(then_body, [(cond.id, "true", "true")]))
        out.extend(self._process_block(else_body, [(cond.id, "false", "false")]))
        return out

    # -- loops -------------------------------------------------------------

    def _process_loop(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        if stmt.get("type") == "ForStatement":
            header = f"for ({stmt.get('control', '')})"
        else:
            header = f"while ({stmt.get('condition', '?')})"

        loop = self._add_node("loop", header, stmt=stmt, code_snippet=header)
        self._connect(tails, loop.id)

        ctx = {"kind": "loop", "header": loop.id, "breaks": []}
        self._ctx.append(ctx)
        body_tails = self._process_block(stmt.get("body", []), [(loop.id, "true", "true")])
        self._ctx.pop()

        # normal fall-through and `continue` both return to the header
        for src, _etype, _label in body_tails:
            self._add_edge(src, loop.id, "back", "back")

        # exit: the false path plus any `break`
        return [(loop.id, "false", "false")] + ctx["breaks"]

    def _process_do(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        entry = self._add_node("statement", "do {", stmt=stmt, code_snippet="do")
        self._connect(tails, entry.id)

        ctx = {"kind": "loop", "header": entry.id, "breaks": [], "do": True}
        self._ctx.append(ctx)
        body_tails = self._process_block(stmt.get("body", []), [_plain(entry.id)])
        self._ctx.pop()

        cond_text = stmt.get("condition", "?")
        cond = self._add_node(
            "condition", f"while ({cond_text})", line_start=max_line(stmt),
            code_snippet=f"while ({cond_text})",
        )
        self._connect(body_tails, cond.id)
        self._add_edge(cond.id, entry.id, "back", "true")
        return [(cond.id, "false", "false")] + ctx["breaks"]

    # -- switch ------------------------------------------------------------

    def _process_switch(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        expr = stmt.get("expression", "?")
        sw = self._add_node("switch", f"switch ({expr})", stmt=stmt, code_snippet=f"switch ({expr})")
        self._connect(tails, sw.id)

        ctx = {"kind": "switch", "breaks": []}
        self._ctx.append(ctx)

        out: list[Tail] = []
        fallthrough: list[Tail] = []
        has_default = False
        for case in stmt.get("cases", []):
            labels = case.get("labels", ["default"])
            if "default" in labels:
                has_default = True
            label_text = ", ".join(str(lbl) for lbl in labels)
            case_node = self._add_node(
                "case", f"case {label_text}", line_start=stmt.get("line"),
                code_snippet=f"case {label_text}:",
            )
            self._add_edge(sw.id, case_node.id, "normal", label_text)
            # fall-through from the previous case without break
            self._connect(fallthrough, case_node.id)
            fallthrough = self._process_block(case.get("body", []), [_plain(case_node.id)])

        out.extend(fallthrough)
        self._ctx.pop()
        out.extend(ctx["breaks"])
        if not has_default:
            out.append((sw.id, "normal", "no match"))
        return out

    # -- try / catch / finally ---------------------------------------------

    def _process_try(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        label = "try"
        if stmt.get("resources"):
            label = "try (" + "; ".join(stmt["resources"]) + ")"
        try_node = self._add_node("try", label[:60], stmt=stmt, code_snippet=label)
        self._connect(tails, try_node.id)

        out = self._process_block(stmt.get("body", []), [_plain(try_node.id)])

        for catch in stmt.get("catches", []):
            catch_types = " | ".join(catch.get("types", ["Exception"]))
            catch_name = catch.get("name", "e")
            text = f"catch ({catch_types} {catch_name})"
            catch_node = self._add_node("catch", text, line_start=stmt.get("line"), code_snippet=text)
            self.stmt_of[catch_node.id] = catch
            self._add_edge(try_node.id, catch_node.id, "exception", "exception")
            out.extend(self._process_block(catch.get("body", []), [_plain(catch_node.id)]))

        finally_body = stmt.get("finally", [])
        if finally_body:
            fin = self._add_node("finally", "finally", line_start=stmt.get("line"), code_snippet="finally")
            self._connect(out, fin.id)
            return self._process_block(finally_body, [_plain(fin.id)])
        return out

    # -- jumps -------------------------------------------------------------

    def _process_return(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        if stmt.get("stream"):
            for src, _etype, _label in self._process_stream(stmt, tails):
                self._add_edge(src, self._end_id)
            return []
        expr = stmt.get("expression", "")
        label = f"return {expr}" if expr else "return"
        node = self._add_node("return", label[:60], stmt=stmt, code_snippet=label)
        self._connect(tails, node.id)
        self._add_edge(node.id, self._end_id)
        return []

    def _process_throw(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        label = f"throw {stmt.get('expression', '')}"
        node = self._add_node("throw", label[:60], stmt=stmt, code_snippet=label)
        self._connect(tails, node.id)
        self._add_edge(node.id, self._end_id, "exception", "throws")
        return []

    def _process_break(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        node = self._add_node("statement", "break", stmt=stmt, code_snippet="break")
        self._connect(tails, node.id)
        for ctx in reversed(self._ctx):
            ctx["breaks"].append(_plain(node.id))
            return []
        self._add_edge(node.id, self._end_id)
        return []

    def _process_continue(self, stmt: dict, tails: list[Tail]) -> list[Tail]:
        node = self._add_node("statement", "continue", stmt=stmt, code_snippet="continue")
        self._connect(tails, node.id)
        for ctx in reversed(self._ctx):
            if ctx["kind"] == "loop":
                self._add_edge(node.id, ctx["header"], "back", "continue")
                return []
        return [_plain(node.id)]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _stmt_snippet(stmt: dict) -> str:
    """Produce a short code snippet from a statement dict."""
    stype = stmt.get("type", "")
    if stype == "LocalVariableDeclaration":
        parts = []
        for d in stmt.get("declarators", []):
            init = d.get("initializer")
            parts.append(f"{d.get('name', '?')} = {init}" if init else d.get("name", "?"))
        mods = " ".join(stmt.get("modifiers", []))
        prefix = f"{mods} " if mods else ""
        return f"{prefix}{stmt.get('var_type', '?')} {', '.join(parts)}"
    if stype == "StatementExpression":
        return stmt.get("expression", stype)
    if "raw" in stmt:
        return str(stmt["raw"])[:80]
    return stype

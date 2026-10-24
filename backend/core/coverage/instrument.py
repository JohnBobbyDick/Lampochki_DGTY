"""Java source instrumentation for coverage.

One pass over the javalang AST collects text edits at token offsets; probes get their ``id``/``slot``
afterwards in source order (by edit offset), so numbering is deterministic.  Edits never contain a
newline, so line numbers of the instrumented code match the original (javac errors and stack traces
point at the user's lines).

Probes (see the stage 4 plan, "Формат данных"):
  * ``line``   — ``__Cov.h(s);`` before every statement of a method / constructor / initializer body and
    everything nested in it (block lambdas, anonymous and local classes). Field initializers are untouched.
  * ``method`` — ``__Cov.h(s);`` right after the ``{`` of a named class' method/constructor body
    (after ``this(…);`` / ``super(…);`` when the body starts with one).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import javalang
import javalang.tree as T

from core.source_map import declaration_span, tokenize

COV_CLASS = "__Cov"
_TEMPLATE = Path(__file__).with_name("Cov.java")
_DONE = ["выполнено"]
_DECISION_KINDS = ("branch", "cond", "rel")   # removed by strip level 1
_TYPE_DECLS = (T.ClassDeclaration, T.InterfaceDeclaration, T.EnumDeclaration, T.AnnotationDeclaration)
_CTOR_CALLS = (T.ExplicitConstructorInvocation, T.SuperConstructorInvocation)
_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {")", "]", "}"}


class CoverageUnavailable(Exception):
    """The code cannot be instrumented (the message is shown to the user, in Russian)."""


@dataclass
class Probe:
    id: int
    kind: str
    line: int
    method: str
    label: str
    outcomes: list[str]
    slot: int

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class Instrumented:
    code: str
    probes: list[Probe]
    slots: int
    cov_source: str


def cov_java(slots: int, package: str | None = None) -> str:
    """Source of the ``__Cov`` counter class for *slots* counters (in the user's package, if any)."""
    src = _TEMPLATE.read_text(encoding="utf-8").replace("/*SLOTS*/0", str(int(slots)))
    return f"package {package};\n{src}" if package else src


def instrument_java(code: str, *, strip: dict[int, int] | None = None) -> Instrumented:
    """Insert coverage probes into *code*.

    ``strip[line] = 1`` drops decision probes (branch/cond/rel) on that line, ``2`` drops every probe
    on it (used to retry after javac rejects the instrumented code).
    """
    try:
        cu = javalang.parse.parse(code)
    except Exception as exc:  # noqa: BLE001 — javalang raises several unrelated exception types
        raise CoverageUnavailable(f"Не удалось разобрать код для покрытия: {_describe(exc)}") from exc
    tokens = tokenize(code)
    if not tokens:
        raise CoverageUnavailable("Не удалось разобрать код для покрытия: ошибка разбора токенов")
    ins = _Instrumenter(code, tokens, strip or {})
    for decl in cu.types:
        ins.type_decl(decl, None)
    text, probes, slots = ins.render()
    return Instrumented(text, probes, slots, cov_java(slots, cu.package.name if cu.package else None))


def _unescape_map(code: str) -> tuple[str, list[int] | None]:
    """Decode ``\\uXXXX`` escapes the way javalang's ``pre_tokenize`` does.

    Returns the decoded text and ``omap`` with ``omap[k]`` = offset in *code* of decoded char ``k``
    (``omap[len(decoded)] == len(code)``), or ``None`` when there is no escape (identity).
    """
    if "\\u" not in code:
        return code, None
    out: list[str] = []
    omap: list[int] = []
    j, n = 0, len(code)
    while j < n:
        if code[j] == "\\" and j + 1 < n:
            if code[j + 1] != "u":            # "\\\\", "\\n"…: the next char is never an escape start
                out += code[j:j + 2]
                omap += [j, j + 1]
                j += 2
                continue
            k = j + 1
            while k < n and code[k] == "u":
                k += 1
            try:
                ch = chr(int(code[k:k + 4], 16))
            except ValueError as exc:
                raise CoverageUnavailable("Не удалось разобрать код для покрытия: неверная \\u-последовательность") from exc
            out.append(ch)
            omap.append(j)
            j = k + 4
            continue
        out.append(code[j])
        omap.append(j)
        j += 1
    omap.append(n)
    decoded = "".join(out)
    try:
        tk = javalang.tokenizer.JavaTokenizer(code)
        tk.pre_tokenize()
        same = tk.data == decoded
    except Exception:  # noqa: BLE001
        same = False
    if not same or decoded.count("\n") != code.count("\n"):
        raise CoverageUnavailable("Не удалось разобрать код для покрытия: \\u-последовательности не поддерживаются")
    return decoded, omap


def _describe(exc: Exception) -> str:
    msg = getattr(exc, "description", None) or str(exc) or type(exc).__name__
    at = getattr(exc, "at", None)
    pos = getattr(at, "position", None)
    return f"{msg} (строка {pos.line})" if pos else msg


@dataclass(eq=False)
class _P:
    """A probe before numbering; ``key`` orders probes in source order."""
    kind: str
    line: int
    method: str
    label: str
    outcomes: list[str]
    key: tuple[int, int]
    slot: int = -1


@dataclass
class _Ref:
    """Placeholder in edit text for ``probe.slot + delta`` (known only after numbering)."""
    probe: _P
    delta: int = 0


@dataclass
class _Edit:
    start: int                     # char offset
    end: int                       # == start for a pure insertion
    seq: int                       # creation order: tie-break for edits at the same offset
    parts: list = field(default_factory=list)   # str | _Ref


class _Instrumenter:
    def __init__(self, code: str, tokens: list, strip: dict[int, int]):
        self.code, self.tokens, self.strip = code, tokens, strip
        # javalang positions refer to the text after \\uXXXX escapes are decoded; map them back.
        decoded, self.omap = _unescape_map(code)
        self.line_starts = [0]
        for i, ch in enumerate(decoded):
            if ch == "\n":
                self.line_starts.append(i + 1)
        self.tok_at = {(t.position.line, t.position.column): i for i, t in enumerate(tokens)}
        self.edits: list[_Edit] = []
        self.probes: list[_P] = []

    # ---- low level -----------------------------------------------------------------------------
    def _doff(self, i: int) -> int:
        """Offset of token *i* in the decoded text."""
        p = self.tokens[i].position
        return self.line_starts[p.line - 1] + p.column - 1

    def off(self, i: int) -> int:
        """Offset of token *i* in the original code."""
        d = self._doff(i)
        return d if self.omap is None else self.omap[d]

    def end_off(self, i: int) -> int:
        """Offset just past token *i* in the original code."""
        d = self._doff(i) + len(self.tokens[i].value)
        return d if self.omap is None else self.omap[d]

    def line(self, i: int) -> int:
        return self.tokens[i].position.line

    def edit(self, start: int, parts: list, end: int | None = None) -> _Edit:
        e = _Edit(start, start if end is None else end, len(self.edits), parts)
        self.edits.append(e)
        return e

    def probe(self, kind: str, line: int, method: str, label: str, outcomes: list[str], at: int) -> _P | None:
        """New probe whose code goes at char offset *at*; None when stripped on this line."""
        level = self.strip.get(line, 0)
        if level >= 2 or (level >= 1 and kind in _DECISION_KINDS):
            return None
        p = _P(kind, line, method, label, list(outcomes), (at, len(self.probes)))
        self.probes.append(p)
        return p

    def render(self) -> tuple[str, list[Probe], int]:
        slot = 0
        probes = []
        for pid, p in enumerate(sorted(self.probes, key=lambda q: q.key)):
            p.slot = slot
            probes.append(Probe(pid, p.kind, p.line, p.method, p.label, p.outcomes, slot))
            slot += len(p.outcomes)
        out, pos = [], 0
        for e in sorted(self.edits, key=lambda x: (x.start, x.seq)):
            if e.start < pos:          # overlapping replacement — never produced by this module
                raise CoverageUnavailable("Не удалось разобрать код для покрытия: пересекающиеся вставки")
            out.append(self.code[pos:e.start])
            out.extend(str(x.probe.slot + x.delta) if isinstance(x, _Ref) else x for x in e.parts)
            pos = e.end
        out.append(self.code[pos:])
        return "".join(out), probes, slot

    # ---- token spans ---------------------------------------------------------------------------
    def start_tok(self, node) -> int | None:
        """First token of a statement: javalang's position moved back over a label and over the
        modifiers/annotations of a local declaration."""
        pos = getattr(node, "position", None)
        i = self.tok_at.get((pos.line, pos.column)) if pos else None
        if i is None:
            return None
        label = getattr(node, "label", None)
        if label and i >= 2 and self.tokens[i - 1].value == ":" and self.tokens[i - 2].value == label:
            i -= 2
        if isinstance(node, (T.LocalVariableDeclaration, *_TYPE_DECLS)) and (node.modifiers or node.annotations):
            depth = 0
            while i > 0:
                v = self.tokens[i - 1].value
                if v == ")":
                    depth += 1
                elif v == "(":
                    depth -= 1
                elif depth == 0 and v in (";", "{", "}", ":"):
                    break
                i -= 1
        return i

    def scan(self, i: int, stop: str) -> int | None:
        """Index of the first *stop* token at nesting depth 0 starting from token *i*."""
        depth = 0
        for j in range(i, len(self.tokens)):
            v = self.tokens[j].value
            if depth == 0 and v == stop:
                return j
            if v in _OPEN:
                depth += 1
            elif v in _CLOSE:
                depth -= 1
        return None

    def match(self, i: int | None) -> int | None:
        """Index of the token closing the bracket at token *i*."""
        if i is None or self.tokens[i].value not in _OPEN:
            return None
        depth = 0
        for j in range(i, len(self.tokens)):
            v = self.tokens[j].value
            if v in _OPEN:
                depth += 1
            elif v in _CLOSE:
                depth -= 1
                if depth == 0:
                    return j
        return None

    def end_tok(self, node) -> int | None:
        """Last token of a statement."""
        if isinstance(node, T.IfStatement):
            return self.end_tok(node.else_statement or node.then_statement)
        if isinstance(node, (T.WhileStatement, T.ForStatement)):
            return self.end_tok(node.body)
        st = self.start_tok(node)
        if st is None:
            return None
        if isinstance(node, T.DoStatement):
            body_end = self.end_tok(node.body)
            return None if body_end is None else self.scan(body_end + 1, ";")
        if isinstance(node, (T.BlockStatement, T.SwitchStatement, T.SynchronizedStatement, *_TYPE_DECLS)):
            return self.match(self.scan(st, "{"))
        if isinstance(node, T.TryStatement):
            return self._try_end(st)
        return self.scan(st, ";")

    def _try_end(self, i: int) -> int | None:
        toks = self.tokens
        i = self.scan(i, "{")
        end = self.match(i)
        while end is not None and end + 1 < len(toks) and toks[end + 1].value in ("catch", "finally"):
            end = self.match(self.scan(end + 2, "{"))
        return end

    # ---- declarations --------------------------------------------------------------------------
    def type_decl(self, decl, method_ctx: str | None) -> None:
        """A named class/interface/enum (top-level, member or local)."""
        name = decl.name
        body = decl.body
        members = body
        if isinstance(decl, T.EnumDeclaration):
            members = body.declarations or []
            for const in body.constants or []:
                if const.body:
                    self.class_body(const.body, None, f"{name}.{const.name}")
        self.class_body(members or [], name, method_ctx)

    def class_body(self, members: list, cls: str | None, method_ctx: str | None) -> None:
        """Members of a named class (*cls*) or of an anonymous one (``cls=None``: no method probes,
        probes are attributed to *method_ctx*, the enclosing named method)."""
        for m in members:
            if isinstance(m, (T.MethodDeclaration, T.ConstructorDeclaration)):
                if m.body is not None:
                    self.method(m, cls, method_ctx)
            elif isinstance(m, list):                      # initializer block
                ctx = method_ctx if cls is None else f"{cls}.{self._initializer_name(m)}"
                self.block(m, ctx)
            elif isinstance(m, _TYPE_DECLS):
                self.type_decl(m, method_ctx)
            # FieldDeclaration / ConstantDeclaration: field initializers are not instrumented

    def _initializer_name(self, stmts: list) -> str:
        st = self.start_tok(stmts[0]) if stmts else None
        if st is not None and st >= 2 and self.tokens[st - 1].value == "{" and self.tokens[st - 2].value == "static":
            return "<clinit>"
        return "<init>"

    def method(self, m, cls: str | None, method_ctx: str | None) -> None:
        ctx = f"{cls}.{m.name}" if cls else (method_ctx or "")
        span = declaration_span(self.tokens, m.position.line, m.position.column) if m.position else None
        lbrace = span and span["body_start_tok"]
        stmts = list(m.body)
        if cls is None or lbrace is None:
            self.block(stmts, ctx)
            return
        first = stmts[0] if stmts else None
        if (isinstance(m, T.ConstructorDeclaration) and isinstance(first, T.StatementExpression)
                and isinstance(first.expression, _CTOR_CALLS)):
            semi = self.end_tok(first)
            if semi is not None:
                self.expr(first, ctx)
                at = self.end_off(semi)
                parts: list = []
                for kind, label in (("method", ctx), ("line", "")):
                    p = self.probe(kind, self.line(semi), ctx, label, _DONE, at)
                    if p:
                        parts += [" __Cov.h(", _Ref(p), ");"]
                if parts:
                    self.edit(at, parts)
                self.block(stmts[1:], ctx)
                return
        at = self.end_off(lbrace)
        p = self.probe("method", self.line(lbrace), ctx, ctx, _DONE, at)
        if p:
            self.edit(at, [" __Cov.h(", _Ref(p), ");"])
        self.block(stmts, ctx)

    # ---- statements ----------------------------------------------------------------------------
    def block(self, stmts, ctx: str) -> None:
        for s in stmts or []:
            self.stmt(s, ctx)

    def stmt(self, s, ctx: str) -> None:
        """A statement inside a statement list: line probe before it."""
        if isinstance(s, T.BlockStatement) and not s.label:
            self.block(s.statements, ctx)
            return
        st = None if type(s) is T.Statement else self.start_tok(s)   # empty statement ';': no probe
        if st is not None:
            at = self.off(st)
            p = self.probe("line", self.line(st), ctx, "", _DONE, at)
            if p:
                self.edit(at, ["__Cov.h(", _Ref(p), "); "])
        self.inner(s, ctx)

    def body(self, s, ctx: str) -> None:
        """Body of if/else/loops: an unbraced statement is wrapped in ``{ … }`` to hold its probe."""
        if s is None or type(s) is T.Statement:
            return
        if isinstance(s, T.BlockStatement) and not s.label:
            self.block(s.statements, ctx)
            return
        st, en = self.start_tok(s), self.end_tok(s)
        p = None
        if st is not None and en is not None:
            at = self.off(st)
            p = self.probe("line", self.line(st), ctx, "", _DONE, at)
            if p:
                self.edit(at, ["{ __Cov.h(", _Ref(p), "); "])
        self.inner(s, ctx)
        if p:
            self.edit(self.end_off(en), [" }"])

    def inner(self, s, ctx: str) -> None:
        """Recurse into the parts of statement *s*."""
        if isinstance(s, T.IfStatement):
            self.expr(s.condition, ctx)
            self.body(s.then_statement, ctx)
            self.body(s.else_statement, ctx)
        elif isinstance(s, T.WhileStatement):
            self.expr(s.condition, ctx)
            self.body(s.body, ctx)
        elif isinstance(s, T.DoStatement):
            self.body(s.body, ctx)
            self.expr(s.condition, ctx)
        elif isinstance(s, T.ForStatement):
            self.expr(s.control, ctx)
            self.body(s.body, ctx)
        elif isinstance(s, T.SwitchStatement):
            self.expr(s.expression, ctx)
            for case in s.cases or []:
                self.block(case.statements, ctx)
        elif isinstance(s, T.TryStatement):
            self.expr(s.resources, ctx)
            self.block(s.block, ctx)
            for c in s.catches or []:
                self.block(c.block, ctx)
            self.block(s.finally_block, ctx)
        elif isinstance(s, T.SynchronizedStatement):
            self.expr(s.lock, ctx)
            self.block(s.block, ctx)
        elif isinstance(s, T.BlockStatement):
            self.block(s.statements, ctx)
        elif isinstance(s, _TYPE_DECLS):              # local class
            self.type_decl(s, ctx)
        else:
            self.expr(s, ctx)

    def expr(self, node, ctx: str) -> None:
        """Find block lambdas and anonymous classes inside an expression (or a simple statement)."""
        if isinstance(node, (list, tuple)):
            for x in node:
                self.expr(x, ctx)
            return
        if not isinstance(node, T.Node):
            return
        if isinstance(node, T.LambdaExpression):
            if isinstance(node.body, list):
                self.block(node.body, ctx)
            else:
                self.expr(node.body, ctx)
            return
        for attr in node.attrs:
            if isinstance(node, T.ClassCreator) and attr == "body":
                continue
            self.expr(getattr(node, attr), ctx)
        if isinstance(node, T.ClassCreator) and node.body is not None:
            self.class_body(node.body, None, ctx)

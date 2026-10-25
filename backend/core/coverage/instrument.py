"""Java source instrumentation for coverage.

One pass over the javalang AST collects text edits at token offsets; probes get their ``id``/``slot``
afterwards in source order (by edit offset), so numbering is deterministic.  Edits never contain a
newline, so line numbers of the instrumented code match the original (javac errors and stack traces
point at the user's lines).

Probes:
  * ``line``   — ``__Cov.h(s);`` before every statement of a method / constructor / initializer body and
    everything nested in it (block lambdas, anonymous and local classes). Field initializers are untouched.
  * ``method`` — ``__Cov.h(s);`` right after the ``{`` of a named class' method/constructor body
    (after ``this(…);`` / ``super(…);`` when the body starts with one).
  * ``branch`` / ``cond`` / ``rel`` — decisions (conditions of ``if``/``while``/``do``/``for``/``?:``),
    ``case`` groups and ``catch`` blocks; leaves of a decision with ``&&``/``||``/``!`` get ``cond``
    probes, comparisons get ``rel`` probes (``__Cov.r`` evaluates the operands once, in order, and
    returns the original operator's result, so short-circuit and side effects are unchanged).
    ``strip`` level 1 removes these together with their loop blocks ``{ boolean __cN … }``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import javalang
import javalang.tree as T

from core.coverage.conditions import has_logic, leaves, parse_condition, split_relation, ternary_conditions
from core.source_map import declaration_span, tokenize

COV_CLASS = "__Cov"
_TEMPLATE = Path(__file__).with_name("Cov.java")
_DONE = ["выполнено"]
_TF = ["истина", "ложь"]
_LOOP = ["тело выполнялось", "тело ни разу не выполнялось"]
_HIT = ["выполнен"]
_ORDER = ["<", "==", ">"]
_EQ = ["==", "!="]
_OPS = {"<": 0, "<=": 1, ">": 2, ">=": 3, "==": 4, "!=": 5}
_LABEL_MAX = 60
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
    id: int = -1


@dataclass
class _Ref:
    """Placeholder in edit text for ``probe.slot + delta`` (or ``probe.id`` with ``attr="id"``),
    known only after numbering."""
    probe: _P
    delta: int = 0
    attr: str = "slot"


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
        self.done_q: set[int] = set()       # `?` tokens whose ternary condition is instrumented

    # low level
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
            p.slot, p.id = slot, pid
            probes.append(Probe(pid, p.kind, p.line, p.method, p.label, p.outcomes, slot))
            slot += len(p.outcomes)
        out, pos = [], 0
        for e in sorted(self.edits, key=lambda x: (x.start, x.seq)):
            if e.start < pos:          # overlapping replacement — never produced by this module
                raise CoverageUnavailable("Не удалось разобрать код для покрытия: пересекающиеся вставки")
            out.append(self.code[pos:e.start])
            out.extend(str(getattr(x.probe, x.attr) + x.delta) if isinstance(x, _Ref) else x for x in e.parts)
            pos = e.end
        out.append(self.code[pos:])
        return "".join(out), probes, slot

    # token spans
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

    # declarations
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
                self.ternaries(self.start_tok(first), semi + 1, ctx)
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

    # statements
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

    def body(self, s, ctx: str, prefix: list | None = None, first: int | None = None) -> None:
        """Body of if/else/loops: an unbraced statement is wrapped in ``{ … }`` to hold its probe.

        *prefix* (loop entry code) goes first inside the body; *first* is the body's first token
        (``{`` of a block, ``;`` of an empty statement) when the caller knows it."""
        if s is None:
            return
        if type(s) is T.Statement:                     # empty statement ';'
            if prefix and first is not None:
                self.edit(self.off(first), ["{ ", *prefix])
                self.edit(self.end_off(first), [" }"])
            return
        if isinstance(s, T.BlockStatement) and not s.label:
            lb = first if first is not None else self.start_tok(s)
            if prefix and lb is not None:
                self.edit(self.end_off(lb), [" ", *prefix])
            self.block(s.statements, ctx)
            return
        st, en = self.start_tok(s), self.end_tok(s)
        wrapped = False
        if st is not None and en is not None:
            at = self.off(st)
            p = self.probe("line", self.line(st), ctx, "", _DONE, at)
            parts = list(prefix or []) + (["__Cov.h(", _Ref(p), "); "] if p else [])
            if parts:
                self.edit(at, ["{ ", *parts])
                wrapped = True
        self.inner(s, ctx)
        if wrapped:
            self.edit(self.end_off(en), [" }"])

    def inner(self, s, ctx: str) -> None:
        """Recurse into the parts of statement *s* (and put its decision probes)."""
        if isinstance(s, T.IfStatement):
            kw = self.kw(s, "if")
            rp = None if kw is None else self.match(kw + 1)
            if rp is not None:
                self.decision(kw + 2, rp, ctx, f"if ({self.text(kw + 2, rp)})", self.line(kw))
            self.expr(s.condition, ctx)
            self.body(s.then_statement, ctx)
            self.body(s.else_statement, ctx)
        elif isinstance(s, (T.WhileStatement, T.ForStatement)):
            self.loop(s, ctx)
        elif isinstance(s, T.DoStatement):
            self.body(s.body, ctx)
            body_end = self.end_tok(s.body)
            kw = None if body_end is None else body_end + 1
            if kw is not None and kw + 1 < len(self.tokens) and self.tokens[kw].value == "while":
                rp = self.match(kw + 1)
                if rp is not None and not self.is_true(kw + 2, rp):
                    self.decision(kw + 2, rp, ctx, f"do…while ({self.text(kw + 2, rp)})", self.line(kw))
            self.expr(s.condition, ctx)
        elif isinstance(s, T.SwitchStatement):
            kw = self.kw(s, "switch")
            rp = None if kw is None else self.match(kw + 1)
            if rp is not None:
                self.ternaries(kw + 2, rp, ctx)
            self.expr(s.expression, ctx)
            for case in s.cases or []:
                if getattr(case, "arrow", False):
                    self.arrow_case(case, ctx)
                    continue
                self.case_probe(case, ctx)
                self.block(case.statements, ctx)
        elif isinstance(s, T.TryStatement):
            kw = self.kw(s, "try")
            if kw is not None and self.tokens[kw + 1].value == "(":
                rp = self.match(kw + 1)
                if rp is not None:
                    self.ternaries(kw + 2, rp, ctx)
            self.expr(s.resources, ctx)
            self.block(s.block, ctx)
            catches = s.catches or []
            braces = self.catch_braces(kw, len(catches)) if kw is not None else []
            for c, (ck, lb) in zip(catches, braces):
                types = " | ".join(getattr(c.parameter, "types", None) or [])
                at = self.end_off(lb)
                p = self.probe("branch", self.line(ck), ctx, self.short(f"catch ({types})"), _HIT, at)
                if p:
                    self.edit(at, [" __Cov.h(", _Ref(p), ");"])
                self.block(c.block, ctx)
            for c in catches[len(braces):]:
                self.block(c.block, ctx)
            self.block(s.finally_block, ctx)
        elif isinstance(s, T.SynchronizedStatement):
            kw = self.kw(s, "synchronized")
            rp = None if kw is None else self.match(kw + 1)
            if rp is not None:
                self.ternaries(kw + 2, rp, ctx)
            self.expr(s.lock, ctx)
            self.block(s.block, ctx)
        elif isinstance(s, T.BlockStatement):
            self.block(s.statements, ctx)
        elif isinstance(s, _TYPE_DECLS):              # local class
            self.type_decl(s, ctx)
        else:
            st = None if type(s) is T.Statement else self.start_tok(s)
            en = None if st is None else self.end_tok(s)
            if en is not None:
                if isinstance(s, T.AssertStatement):
                    st += 1
                self.ternaries(st, en + 1, ctx)
            self.expr(s, ctx)

    # decisions
    def kw(self, s, word: str) -> int | None:
        """Token index of the keyword *word* that starts statement *s* (after its labels)."""
        pos = getattr(s, "position", None)
        i = self.tok_at.get((pos.line, pos.column)) if pos else None
        while (i is not None and i + 2 < len(self.tokens) and self.tokens[i].value != word
               and self.tokens[i + 1].value == ":"):
            i += 2
        if i is None or self.tokens[i].value != word or i + 1 >= len(self.tokens):
            return None
        return i

    def text(self, a: int, b: int) -> str:
        """Source of tokens [a, b) with whitespace collapsed."""
        if b <= a:
            return ""
        return " ".join(self.code[self.off(a):self.end_off(b - 1)].split())

    @staticmethod
    def short(label: str) -> str:
        return label if len(label) <= _LABEL_MAX else label[:_LABEL_MAX - 1] + "…"

    def has_pattern(self, a: int, b: int) -> bool:
        """Tokens [a, b) hold ``x instanceof Type name`` (Java 16): wrapping that condition in a
        probe call would take the pattern variable out of scope, so it is left uninstrumented."""
        toks = self.tokens
        for j in range(a, b):
            if toks[j].value != "instanceof":
                continue
            k = j + 1
            if k < b and toks[k].value == "final":
                return True
            depth = 0
            while k < b:
                v = toks[k].value
                if v == "<":
                    depth += 1
                elif v == ">":
                    depth -= 1
                elif depth == 0 and v not in (".", "[", "]") and not (
                        isinstance(toks[k], javalang.tokenizer.Identifier) and toks[k - 1].value in ("instanceof", ".")):
                    break
                k += 1
            if k < b and isinstance(toks[k], javalang.tokenizer.Identifier):
                return True
        return False

    def is_true(self, a: int, b: int) -> bool:
        return b - a == 1 and self.tokens[a].value == "true"

    def decision(self, a: int, b: int, ctx: str, label: str, line: int, scan: bool = True) -> None:
        """``if``/``do``/``?:`` condition [a, b): ``__Cov.c(sb, D')``; *scan* — also the ``?:``
        conditions inside it."""
        if b <= a or self.has_pattern(a, b):
            return
        p = self.probe("branch", line, ctx, self.short(label), _TF, self.off(a))
        self.condition(a, b, ctx, ["__Cov.c(", _Ref(p), ", "] if p else None)
        if scan:
            self.ternaries(a, b, ctx)

    def condition(self, a: int, b: int, ctx: str, head: list | None) -> None:
        """Wrap the decision [a, b) in *head* … ``)`` and its leaves in cond/rel probes.

        Openings are created outside-in and closings inside-out, so edits at one offset nest."""
        if head:
            self.edit(self.off(a), head)
        root = parse_condition(self.tokens, a, b)
        logic = has_logic(root)
        for lf in leaves(root):
            self.leaf(lf.a, lf.b, ctx, logic)
        if head:
            self.edit(self.end_off(b - 1), [")"])

    def leaf(self, a: int, b: int, ctx: str, logic: bool) -> None:
        """Leaf L of a decision: ``__Cov.c(sc, L')`` when the decision has logic; ``L'`` is
        ``__Cov.r(sr, op, A, B)`` when L is a comparison."""
        if b <= a:
            return
        at, line = self.off(a), self.line(a)
        label = self.short(self.text(a, b))
        pc = self.probe("cond", line, ctx, label, _TF, at) if logic else None
        if pc:
            self.edit(at, ["__Cov.c(", _Ref(pc), ", "])
        rel = split_relation(self.tokens, a, b)
        if rel:
            i, op, _ = rel
            code = _OPS[op]
            pr = self.probe("rel", line, ctx, label, _EQ if code >= 4 else _ORDER, at)
            if pr:
                # unary + for < <= > >= (and ==/!= against a numeric literal, where Java compares
                # numerically too): boxed operands are unboxed, so a numeric overload is chosen
                plus = code < 4 or self.num_literal(a, i) or self.num_literal(i + 1, b)
                self.edit(at, ["__Cov.r(", _Ref(pr), f", {code}, " + ("+(" if plus else "")])
                self.edit(self.off(i), ["), +(" if plus else ", "], self.end_off(i))
                self.edit(self.end_off(b - 1), ["))" if plus else ")"])
        if pc:
            self.edit(self.end_off(b - 1), [")"])

    def num_literal(self, a: int, b: int) -> bool:
        """Tokens [a, b) are a numeric/char literal, optionally signed."""
        if b - a == 2 and self.tokens[a].value in ("-", "+"):
            a += 1
        if b - a != 1:
            return False
        t = self.tokens[a]
        if isinstance(t, (javalang.tokenizer.Boolean, javalang.tokenizer.Null)):
            return False
        if isinstance(t, javalang.tokenizer.String):      # javalang tokenizes 'c' as String
            return t.value.startswith("'")
        return isinstance(t, javalang.tokenizer.Literal)

    def ternaries(self, a: int | None, b: int, ctx: str) -> None:
        """Branch probes for the ``?:`` conditions in tokens [a, b), skipping block lambdas and
        anonymous class bodies (their statements are visited on their own)."""
        if a is None or b <= a:
            return
        skips = []
        j = a
        while j < b:
            if self.tokens[j].value == "{" and j > a and self.tokens[j - 1].value in ("->", ")"):
                end = self.match(j)
                if end is not None:
                    skips.append((j, end))
                    j = end
            j += 1
        for ca, q in ternary_conditions(self.tokens, a, b):
            if q in self.done_q or any(x < q < y for x, y in skips):
                continue
            self.done_q.add(q)
            self.decision(ca, q, ctx, f"?: ({self.text(ca, q)})", self.line(ca), scan=False)

    def loop(self, s, ctx: str) -> None:
        """``while``/``for``/for-each: branch "body ran / never ran" kept in a ``__cN`` flag."""
        is_while = isinstance(s, T.WhileStatement)
        word = "while" if is_while else "for"
        header = s.condition if is_while else s.control
        kw = self.kw(s, word)
        rp = None if kw is None else self.match(kw + 1)
        st = self.start_tok(s)
        if rp is None or st is None:
            self.expr(header, ctx)
            self.body(s.body, ctx)
            return
        each = not is_while and isinstance(s.control, T.EnhancedForControl)
        ca = cb = None
        if is_while:
            ca, cb = kw + 2, rp
        elif not each:
            semi1 = self.scan(kw + 2, ";")
            semi2 = None if semi1 is None else self.scan(semi1 + 1, ";")
            if semi2 is not None:
                ca, cb = semi1 + 1, semi2
        constant = not each and (ca is None or ca >= cb or self.is_true(ca, cb) or self.has_pattern(ca, cb))
        en = rp + 1 if type(s.body) is T.Statement else self.end_tok(s)
        p = None
        if not constant and en is not None:
            label = self.short(f"{word} ({self.text(kw + 2, rp)})")
            p = self.probe("branch", self.line(kw), ctx, label, _LOOP, self.off(st))
        flag = ["__c", _Ref(p, 0, "id")] if p else []
        if p:
            self.edit(self.off(st), ["{ boolean ", *flag, " = false; "])
        if not constant and not each:
            self.condition(ca, cb, ctx, ["__Cov.lp(", _Ref(p), ", ", *flag, ", "] if p else None)
        self.ternaries(kw + 2, rp, ctx)
        self.expr(header, ctx)
        prefix = ["if (!", *flag, ") { ", *flag, " = true; __Cov.h(", _Ref(p), "); } "] if p else None
        self.body(s.body, ctx, prefix, rp + 1)
        if p:
            tail = [" if (!", *flag, ") __Cov.h(", _Ref(p, 1), "); }"] if each else [" }"]
            self.edit(self.end_off(en), tail)

    def case_probe(self, case, ctx: str) -> None:
        """``__Cov.h(s);`` right after the last label of a non-empty case group."""
        if not case.statements:
            return
        st = self.start_tok(case.statements[0])
        if st is None or st < 1 or self.tokens[st - 1].value != ":":
            return
        colon = j = st - 1
        values: list[str] = []
        dflt = False
        while j >= 0 and self.tokens[j].value == ":":
            k = j - 1
            while k >= 0 and self.tokens[k].value not in ("case", "default"):
                k -= 1
            if k < 0:
                break
            if self.tokens[k].value == "default":
                dflt = True
            else:
                values.insert(0, self.text(k + 1, j))
            j = k - 1
        if not values and not dflt:
            return
        label = f"case {', '.join(values)}" if values else ""
        if dflt:
            label = f"{label}, default" if label else "default"
        at = self.end_off(colon)
        p = self.probe("branch", self.line(colon), ctx, self.short(label), _HIT, at)
        if p:
            self.edit(at, [" __Cov.h(", _Ref(p), ");"])

    def arrow_case(self, case, ctx: str) -> None:
        """Java 14 ``case A, B -> …``: branch probe first in the rule body; a body that is a single
        statement (expression / throw) is wrapped in ``{ … }`` to hold the probes."""
        if not case.statements:
            return
        st = self.start_tok(case.statements[0])
        if st is None or st < 1:
            return
        braced = self.tokens[st - 1].value == "{" and st >= 2 and self.tokens[st - 2].value == "->"
        arrow = st - 2 if braced else st - 1
        if self.tokens[arrow].value != "->":
            return
        k = arrow - 1
        while k >= 0 and self.tokens[k].value not in ("case", "default"):
            k -= 1
        label = "default" if k >= 0 and self.tokens[k].value == "default" else f"case {self.text(k + 1, arrow)}"
        if braced:
            at = self.end_off(st - 1)
            p = self.probe("branch", self.line(arrow), ctx, self.short(label), _HIT, at)
            if p:
                self.edit(at, [" __Cov.h(", _Ref(p), ");"])
            self.block(case.statements, ctx)
            return
        en = self.end_tok(case.statements[-1])
        if en is None:
            return
        at = self.off(st)
        p = self.probe("branch", self.line(arrow), ctx, self.short(label), _HIT, at)
        self.edit(at, ["{ ", *(["__Cov.h(", _Ref(p), "); "] if p else [])])
        self.block(case.statements, ctx)
        self.edit(self.end_off(en), [" }"])

    def catch_braces(self, kw: int, n: int) -> list[tuple[int, int]]:
        """(``catch`` token, ``{`` of its block) for the first *n* catch clauses of a try."""
        out = []
        end = self.match(self.scan(kw, "{"))
        while (len(out) < n and end is not None and end + 1 < len(self.tokens)
               and self.tokens[end + 1].value == "catch"):
            lb = self.scan(end + 2, "{")
            if lb is None:
                break
            out.append((end + 1, lb))
            end = self.match(lb)
        return out

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

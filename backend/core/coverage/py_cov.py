"""Python coverage: AST instrumentation, the ``_jb_cov`` runtime and the child's loader.

Stdlib only: the file is copied next to ``main.py`` and imported by ``_jb_run.py`` in the child. The
server calls :func:`instrument` for the probe list, the child calls it again for the code, so probe
numbering must depend on the source alone (probes are sorted by source position, then creation order).

Probes (same format and outcomes as ``instrument.py`` for Java):
  * ``line``   — ``_jb_cov.h(s)`` before every statement (docstrings and ``from __future__`` stay first).
  * ``method`` — ``_jb_cov.h(s)`` on entry to every ``def`` (after its docstring).
  * ``branch`` — ``if``/``elif``/``while``/``x if c else y`` conditions (``_TF``), ``for`` (``_LOOP``,
    the iterable is wrapped), ``except`` and ``case`` (``_HIT``).
  * ``cond``   — leaves of ``and``/``or``/``not`` in those conditions (``_TF``).
  * ``rel``    — a single ``<,<=,>,>=`` (``_ORDER``) or ``==,!=`` (``_EQ``) leaf; chains and ``in``/``is``
    get none.
Wrappers evaluate each operand once, in order; a condition's value is only used for its truth, so its
leaves become ``bool`` (``__bool__`` is still called exactly once per evaluated leaf) and short-circuit is
unchanged. The runtime name is ``_jb_cov`` (a builtin): a ``__name`` would be mangled inside classes.
Counters are int32 little-endian, slot ``s`` at byte ``s*4`` of the memory-mapped file ``$JB_COV``
(``$JB_COV_SLOTS`` slots), so they survive Stop / timeout / kill.
"""

from __future__ import annotations

import ast
import builtins
import mmap
import operator
import os
import struct
import sys
import tokenize
import traceback
import types

# identical to core/coverage/instrument.py (checked by tests; importing it would pull in javalang)
_DONE = ["выполнено"]
_TF = ["истина", "ложь"]
_LOOP = ["тело выполнялось", "тело ни разу не выполнялось"]
_HIT = ["выполнен"]
_ORDER = ["<", "==", ">"]
_EQ = ["==", "!="]
_LABEL_MAX = 60
_REL_OPS = {ast.Lt: 0, ast.LtE: 1, ast.Gt: 2, ast.GtE: 3, ast.Eq: 4, ast.NotEq: 5}
_RT = "_jb_cov"


# instrumentation

def instrument(source: str) -> tuple[ast.Module, list[dict]]:
    """Parse *source* and insert probes; returns the module AST and the probes as plain dicts
    (``id, kind, line, method, label, outcomes, slot``). Raises ``SyntaxError`` for invalid code."""
    tree = ast.parse(source, "main.py")
    tr = _Transformer(source, tree)
    tree.body = tr.body(tree.body, head=True, future=True)
    ast.fix_missing_locations(tree)
    return tree, tr.render()


def _is_docstring(s: ast.stmt) -> bool:
    return isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str)


class _Transformer(ast.NodeTransformer):
    def __init__(self, source: str, tree: ast.Module):
        self.src = source
        self.probes: list[tuple[tuple[int, int, int], dict, ast.Constant]] = []
        top = {s.name for s in tree.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.ctx = f"Module.{'main' if 'main' not in top else '__main__'}"   # as in py_parser
        self.owner = "Module"            # qualifies a def: Module.f, Cls.m, Cls.m.inner

    def render(self) -> list[dict]:
        out, slot = [], 0
        for pid, (_, d, ref) in enumerate(sorted(self.probes, key=lambda p: p[0])):
            ref.value = slot
            out.append(dict(d, id=pid, slot=slot))
            slot += len(d["outcomes"])
        return out

    # helpers
    def probe(self, kind: str, node: ast.AST, label: str, outcomes: list[str]) -> ast.Constant:
        ref = ast.Constant(0)
        d = {"kind": kind, "line": node.lineno, "method": self.ctx, "label": label, "outcomes": list(outcomes)}
        self.probes.append(((node.lineno, node.col_offset, len(self.probes)), d, ref))
        return ref

    def call(self, fn: str, args: list, at: ast.AST) -> ast.Call:
        func = ast.Attribute(ast.Name(_RT, ast.Load()), fn, ast.Load())
        return ast.copy_location(ast.Call(func, args, []), at)

    def hit(self, kind: str, node: ast.AST, label: str, outcomes: list[str]) -> ast.Expr:
        return ast.copy_location(ast.Expr(self.call("h", [self.probe(kind, node, label, outcomes)], node)), node)

    def text(self, node: ast.AST) -> str:
        s = ast.get_source_segment(self.src, node) or ast.unparse(node)
        s = " ".join(s.split())
        return s if len(s) <= _LABEL_MAX else s[:_LABEL_MAX - 1] + "…"

    def body(self, stmts: list[ast.stmt], head: bool = False, future: bool = False) -> list[ast.stmt]:
        """Statements with a line probe before each; *head* keeps a leading docstring (and, for a module,
        *future* keeps ``from __future__`` imports) first and without a probe."""
        out: list[ast.stmt] = []
        i = 0
        if head and stmts and _is_docstring(stmts[0]):
            out.append(stmts[0])
            i = 1
        while future and i < len(stmts) and isinstance(stmts[i], ast.ImportFrom) and stmts[i].module == "__future__":
            out.append(stmts[i])
            i += 1
        for s in stmts[i:]:
            out.append(self.hit("line", s, "", _DONE))
            out.append(self.visit(s))
        return out

    def decision(self, test: ast.expr, label: str) -> ast.Call:
        p = self.probe("branch", test, label, _TF)
        logic = isinstance(test, ast.BoolOp) or (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not))
        return self.call("c", [p, self.cond(test, logic)], test)

    def cond(self, node: ast.expr, logic: bool) -> ast.expr:
        if isinstance(node, ast.BoolOp):
            node.values = [self.cond(v, logic) for v in node.values]
            return node
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            node.operand = self.cond(node.operand, logic)
            return node
        label = self.text(node)
        pc = self.probe("cond", node, label, _TF) if logic else None
        rel = None
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _REL_OPS:
            op = _REL_OPS[type(node.ops[0])]
            rel = (self.probe("rel", node, label, _EQ if op >= 4 else _ORDER), op)
        node = self.visit(node)
        if rel:
            node = self.call("r", [rel[0], ast.Constant(rel[1]), node.left, node.comparators[0]], node)
        return self.call("c", [pc, node], node) if pc else node

    # definitions
    def visit_FunctionDef(self, node):
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        node.args = self.visit(node.args)
        if node.returns:
            node.returns = self.visit(node.returns)
        qual = f"{self.owner}.{node.name}"
        saved = self.ctx, self.owner
        self.ctx = self.owner = qual
        body = self.body(node.body, head=True)
        entry = self.hit("method", node, qual, _DONE)
        k = 1 if _is_docstring(node.body[0]) else 0
        node.body = body[:k] + [entry] + body[k:]
        self.ctx, self.owner = saved
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        node.bases = [self.visit(b) for b in node.bases]
        node.keywords = [self.visit(k) for k in node.keywords]
        saved = self.owner
        self.owner = node.name
        node.body = self.body(node.body, head=True)
        self.owner = saved
        return node

    # statements
    def visit_If(self, node):
        node.test = self.decision(node.test, f"if {self.text(node.test)}")
        node.body = self.body(node.body)
        node.orelse = self.body(node.orelse)
        return node

    def visit_While(self, node):
        node.test = self.decision(node.test, f"while {self.text(node.test)}")
        node.body = self.body(node.body)
        node.orelse = self.body(node.orelse)
        return node

    def visit_For(self, node):
        p = self.probe("branch", node, f"for {self.text(node.target)} in {self.text(node.iter)}", _LOOP)
        node.target = self.visit(node.target)
        node.iter = self.call("it", [p, self.visit(node.iter)], node.iter)
        node.body = self.body(node.body)
        node.orelse = self.body(node.orelse)
        return node

    def visit_AsyncFor(self, node):
        node.target = self.visit(node.target)
        node.iter = self.visit(node.iter)
        node.body = self.body(node.body)
        node.orelse = self.body(node.orelse)
        return node

    def visit_With(self, node):
        node.items = [self.visit(i) for i in node.items]
        node.body = self.body(node.body)
        return node

    visit_AsyncWith = visit_With

    def visit_Try(self, node):
        node.body = self.body(node.body)
        for h in node.handlers:
            label = f"except {self.text(h.type)}" if h.type else "except"
            entry = self.hit("branch", h, label, _HIT)
            if h.type:
                h.type = self.visit(h.type)
            h.body = [entry] + self.body(h.body)
        node.orelse = self.body(node.orelse)
        node.finalbody = self.body(node.finalbody)
        return node

    visit_TryStar = visit_Try

    def visit_Match(self, node):
        node.subject = self.visit(node.subject)
        for c in node.cases:
            entry = self.hit("branch", c.pattern, f"case {self.text(c.pattern)}", _HIT)
            if c.guard:
                c.guard = self.visit(c.guard)
            c.body = [entry] + self.body(c.body)
        return node

    # expressions
    def visit_IfExp(self, node):
        node.test = self.decision(node.test, self.text(node.test))
        node.body = self.visit(node.body)
        node.orelse = self.visit(node.orelse)
        return node


# runtime

_I32 = struct.Struct("<i")
_MAX = 0x7FFFFFFF
_CMP = (operator.lt, operator.le, operator.gt, operator.ge, operator.eq, operator.ne)
_SAFE = (int, float, bool)       # exact builtin types: comparing them again has no side effects


class _Cov:
    """Counters in *path* (memory-mapped) or in memory when the file cannot be used."""

    def __init__(self, path: str | None, slots: int):
        self.buf = bytearray(slots * 4)
        if path and slots:
            fd = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
            try:
                if os.fstat(fd).st_size != slots * 4:
                    raise OSError("размер файла счётчиков не совпадает")
                self.buf = mmap.mmap(fd, slots * 4)
            finally:
                os.close(fd)

    def h(self, s: int) -> None:
        """Saturating increment of slot *s*."""
        i = s * 4
        v = _I32.unpack_from(self.buf, i)[0]
        if v != _MAX:
            _I32.pack_into(self.buf, i, v + 1)

    def c(self, s: int, v) -> bool:
        """Decision / condition: true -> s, false -> s+1."""
        b = bool(v)
        self.h(s if b else s + 1)
        return b

    def r(self, s: int, op: int, a, b):
        """``a <op> b`` (op: 0 <, 1 <=, 2 >, 3 >=, 4 ==, 5 !=); records ``<``/``==``/``>`` (or ``==``/``!=``)."""
        res = _CMP[op](a, b)
        if op >= 4:
            if type(res) is bool:
                self.h(s if res == (op == 4) else s + 1)
        elif (type(a) in _SAFE and type(b) in _SAFE) or (type(a) is str and type(b) is str):
            if a < b:
                self.h(s)
            elif a == b:
                self.h(s + 1)
            elif a > b:
                self.h(s + 2)
        elif type(res) is bool:      # other types: only what the result itself tells
            if res and op == 0 or not res and op == 3:
                self.h(s)
            elif res and op == 2 or not res and op == 1:
                self.h(s + 2)
        return res

    def it(self, s: int, iterable):
        """``for`` iterable: s when the body ran, s+1 when the loop ended without entering it."""
        return self._loop(s, iter(iterable))

    def _loop(self, s: int, it):
        entered = False
        for v in it:
            if not entered:
                entered = True
                self.h(s)
            yield v
        if not entered:
            self.h(s + 1)


# loader (``_jb_run.py``: ``import py_cov; py_cov.run("main.py")``)

_loader_main = None


def _loader_frame(filename: str) -> bool:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(filename) in (os.path.abspath(__file__), os.path.join(here, "_jb_run.py"))


def _strip(te, seen: set) -> None:
    if te is None or id(te) in seen:
        return
    seen.add(id(te))
    te.stack = traceback.StackSummary.from_list([f for f in te.stack if not _loader_frame(f.filename)])
    _strip(te.__cause__, seen)
    _strip(te.__context__, seen)
    for sub in getattr(te, "exceptions", None) or []:
        _strip(sub, seen)


def _compile_cov(src: str, filename: str):
    """Instrumented code object, or None when coverage is off or unavailable (the original runs)."""
    path = os.environ.get("JB_COV")
    if not path:
        return None
    try:
        tree, probes = instrument(src)
        slots = sum(len(p["outcomes"]) for p in probes)
        if str(slots) != os.environ.get("JB_COV_SLOTS"):
            return None
        code = compile(tree, filename, "exec")
        setattr(builtins, _RT, _Cov(path, slots))
        # write into the pre-created marker (never create or follow one): the host treats it as set when non-empty
        fd = os.open(os.path.join(os.path.dirname(path), "compiled"),
                     os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        try:
            os.write(fd, b"1")
        finally:
            os.close(fd)
        return code
    except Exception:  # noqa: BLE001 — any failure: run the original without coverage
        return None


def run(path: str = "main.py") -> None:
    """Run *path* as ``__main__`` (instrumented when ``$JB_COV`` is set), like ``python path``."""
    global _loader_main
    with tokenize.open(path) as f:
        src = f.read()
    import linecache
    linecache.cache[path] = (len(src), None, src.splitlines(True), path)
    sys.argv = [path]
    main = types.ModuleType("__main__")
    main.__file__ = os.path.abspath(path)
    main.__builtins__ = builtins
    main.__spec__ = None
    try:
        code = _compile_cov(src, path) or compile(src, path, "exec")
        _loader_main = sys.modules.get("__main__")
        sys.modules["__main__"] = main
        exec(code, main.__dict__)
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — print like the interpreter, minus the loader frames
        te = traceback.TracebackException(type(exc), exc, exc.__traceback__)
        _strip(te, set())
        sys.stderr.write("".join(te.format()))
        sys.stderr.flush()
        sys.exit(1)

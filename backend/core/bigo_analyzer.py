"""Static Big-O estimation.

A cost is ``(p, l)`` meaning ``n^p · log^l n``. A method's cost is the worst of its statements:
sequential code takes the maximum, a loop multiplies its body by the loop's own cost, and a call
adds the cost of what it calls — methods of the project (resolved recursively, with memoisation)
and well-known library operations whose cost depends on the receiver's type.

Python methods (``language: "python"``) have their statement texts parsed with ``ast`` (comprehensions,
builtins, ``in`` by the known collection type); a text that does not parse falls back to the regexes.
"""

from __future__ import annotations

import ast as pyast
import re
from functools import lru_cache

LOOP_TYPES = ("ForStatement", "WhileStatement", "DoStatement")

Cost = tuple[int, int]
ZERO: Cost = (0, 0)
LOG: Cost = (0, 1)
LINEAR: Cost = (1, 0)
NLOGN: Cost = (1, 1)
EXP: Cost = (99, 0)          # exponential; dominates everything
UNKNOWN = None               # mutual / unclassified recursion

_EXPR_KEYS = ("expression", "condition", "control", "initializer", "raw", "items")
_BODY_KEYS = ("body", "then", "else", "finally", "cases", "catches")
_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "new", "synchronized", "super", "this", "throw"}

_SORT_RE = re.compile(r"(?:Collections|Arrays)\s*\.\s*sort\s*\(|\.\s*sort\s*\(|\.\s*sorted\s*\(")
_LINEAR_CALL_RE = re.compile(
    r"\.\s*(?:stream|parallelStream)\s*\(|\.\s*(?:forEach|removeIf|replaceAll|addAll|toArray)\s*\("
    r"|Collections\s*\.\s*(?:max|min|reverse|shuffle|frequency|fill|copy)\s*\("
    r"|Arrays\s*\.\s*(?:fill|copyOf|copyOfRange|toString|equals|stream)\s*\(|System\s*\.\s*arraycopy\s*\("
    r"|String\s*\.\s*join\s*\("
)
_RECEIVER_CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*\(")
_LOCAL_CALL_RE = re.compile(r"(?<![\w.])(?:this\s*\.\s*)?([A-Za-z_]\w*)\s*\(")

_LIST_TYPES = re.compile(r"\b(?:List|ArrayList|LinkedList|Vector|Collection|Stack)\b")
_TREE_TYPES = re.compile(r"\b(?:TreeSet|TreeMap|SortedSet|SortedMap|NavigableSet|NavigableMap|PriorityQueue)\b")
_HASH_TYPES = re.compile(r"\b(?:Set|HashSet|LinkedHashSet|Map|HashMap|LinkedHashMap)\b")
_SEARCH_OPS = {"contains", "indexOf", "lastIndexOf", "remove", "containsAll", "removeAll", "retainAll", "containsValue"}
_KEYED_OPS = {"contains", "containsKey", "get", "put", "remove", "add", "getOrDefault", "putIfAbsent"}


# ── statement tree helpers (also used by defect_detector) ────────────────────────────────────────

def _children(stmt: dict):
    for key in ("body", "then", "else", "finally"):
        v = stmt.get(key)
        if isinstance(v, list):
            yield from v
    for case in stmt.get("cases", []) or []:
        yield from case.get("body", [])
    for c in stmt.get("catches", []) or []:
        yield from c.get("body", [])


def _loop_else(stmt: dict) -> list[dict]:
    """The `else` of a Python for/while: it runs once after the loop, so it is not nested in it."""
    return (stmt.get("else") or []) if stmt.get("type") in LOOP_TYPES else []


def _nested(stmt: dict) -> list[dict]:
    """Children of a statement that run inside it (for a loop: on every iteration)."""
    if stmt.get("type") in LOOP_TYPES and stmt.get("else"):
        return [c for k in ("body", "then", "finally") for c in (stmt.get(k) or [])]
    return list(_children(stmt))


def loop_depth(stmts: list[dict]) -> int:
    """Maximum loop nesting depth in a statement list."""
    best = 0
    for s in stmts:
        d = loop_depth(_nested(s))
        if s.get("type") in LOOP_TYPES:
            d += 1
        best = max(best, d, loop_depth(_loop_else(s)))
    return best


def find_loops(stmts: list[dict], depth: int = 0, out: list | None = None) -> list[tuple[dict, int]]:
    """All loops with their nesting depth (outermost = 1)."""
    out = [] if out is None else out
    for s in stmts:
        d = depth + (1 if s.get("type") in LOOP_TYPES else 0)
        if s.get("type") in LOOP_TYPES:
            out.append((s, d))
        find_loops(_nested(s), d, out)
        find_loops(_loop_else(s), depth, out)
    return out


def _walk_exprs(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, str) and k in _EXPR_KEYS:
                yield v
            elif isinstance(v, (dict, list)):
                yield from _walk_exprs(v)
    elif isinstance(o, list):
        for i in o:
            yield from _walk_exprs(i)


def _own_exprs(stmt: dict):
    """Expressions of the statement itself, not of the statements nested in it."""
    for k, v in stmt.items():
        if k in _BODY_KEYS:
            continue
        if isinstance(v, str) and k in _EXPR_KEYS:
            yield v
        elif isinstance(v, (dict, list)):
            yield from _walk_exprs(v)


def _walk_stmts(stmts: list[dict]):
    for s in stmts:
        yield s
        yield from _walk_stmts(list(_children(s)))


def _call_args(text: str, name: str) -> list[str]:
    """Argument lists of every unqualified (or this.) call to `name` in text."""
    out = []
    for m in re.finditer(rf"(?<![\w.])(?:this\s*\.\s*)?{re.escape(name)}\s*\(", text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        out.append(text[m.end():i - 1])
    return out


def _argc(args: str) -> int:
    if not args.strip():
        return 0
    depth, n = 0, 1
    for ch in args:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            n += 1
    return n


# ── cost arithmetic ─────────────────────────────────────────────────────────────────────────────

def _mul(a: Cost, b: Cost) -> Cost:
    if a[0] >= EXP[0] or b[0] >= EXP[0]:
        return EXP
    return (a[0] + b[0], a[1] + b[1])


def _worst(*costs: Cost) -> Cost:
    return max(costs, default=ZERO)


def _mul_u(a: Cost | None, b: Cost | None) -> Cost | None:
    return UNKNOWN if a is UNKNOWN or b is UNKNOWN else _mul(a, b)


def _worst_u(*costs: Cost | None) -> Cost | None:
    return UNKNOWN if UNKNOWN in costs else _worst(*costs)


def _sup(k: int) -> str:
    return "²³⁴⁵"[k - 2] if 2 <= k <= 5 else f"^{k}"


def complexity_label(cost: Cost | None, recursive: bool = True) -> str:
    if cost is UNKNOWN:
        return "O(?) рекурсия" if recursive else "O(?)"
    if cost >= EXP:
        return "O(2^n)"
    p, l = cost
    parts = []
    if p:
        parts.append("n" if p == 1 else "n" + _sup(p))
    if l:
        parts.append("log n" if l == 1 else f"log{_sup(l)} n")
    return f"O({' '.join(parts)})" if parts else "O(1)"


# ── loops ───────────────────────────────────────────────────────────────────────────────────────

_DOUBLING = re.compile(r"\b2\s*\*\s*\w|\w\s*\*\s*2\b|<<\s*1\b")
_HALVING_RHS = re.compile(r"/\s*2\b|>>\s*1\b|\*\s*2\b|<<\s*1\b")
_COMPOUND_LOG = re.compile(r"(\w+)\s*(?:\*=|/?/=)\s*\d+|(\w+)\s*(?:<<=|>>=)\s*\d+")
_ASSIGN = re.compile(r"(?<![=!<>])\b([A-Za-z_]\w*)\s*=(?!=)\s*([^;]+)")


def _assignments(stmts: list[dict]):
    """(target, rhs) pairs for plain assignments and local declarations in a statement subtree."""
    for s in _walk_stmts(stmts):
        if s.get("type") == "LocalVariableDeclaration":
            for d in s.get("declarators", []):
                if d.get("initializer"):
                    yield d["name"], d["initializer"]
        for e in _own_exprs(s):
            for m in _ASSIGN.finditer(e):
                yield m.group(1), m.group(2)


def _loop_cost(loop: dict) -> Cost:
    """How many times the loop body runs, as a cost."""
    control = loop.get("control", "") or ""
    if loop.get("type") == "ForStatement" and control.count(";") == 2:
        init, cond, update = (x.strip() for x in control.split(";"))
        if re.search(r"=\s*-?\d+\s*$", init) and re.search(r"[<>]=?\s*(?:-?\d+|[A-Z][A-Z0-9_]*)\s*$", cond):
            return ZERO                                    # for (i = 0; i < 10; i++)
        if _COMPOUND_LOG.search(update) or re.search(r"\w+\s*=\s*\w+\s*[*/]\s*2\b|\w+\s*=\s*\w+\s*(?:<<|>>)\s*1\b", update):
            return LOG                                     # for (i = 1; i < n; i *= 2)
        return LINEAR
    if loop.get("type") in ("WhileStatement", "DoStatement"):
        cond_vars = set(re.findall(r"\b([A-Za-z_]\w*)\b(?!\s*\()", loop.get("condition", "") or ""))
        body = loop.get("body", []) or []
        body_text = " ".join(_walk_exprs(body))
        for m in _COMPOUND_LOG.finditer(body_text):
            if (m.group(1) or m.group(2)) in cond_vars:
                return LOG                                 # while (n > 1) n /= 2;
        assigns = list(_assignments(body))
        if any(t in cond_vars and re.search(r"\w\s*%\s*\w", rhs) for t, rhs in assigns):
            return LOG                                     # Euclid: while (b != 0) { b = a % b; ... }
        halved = {t for t, rhs in assigns if _HALVING_RHS.search(rhs)}
        for target, rhs in assigns:
            if target in cond_vars and (target in halved or any(re.search(rf"\b{re.escape(h)}\b", rhs) for h in halved)):
                return LOG                                 # binary search: lo = mid + 1, mid = (lo + hi) / 2
    return LINEAR


# ── Python expressions ──────────────────────────────────────────────────────────────────────────

_PY_SEQ_TYPES = {"list", "List", "Sequence", "MutableSequence", "tuple", "Tuple", "str", "deque", "Deque"}
_PY_HASH_TYPES = {"set", "Set", "frozenset", "FrozenSet", "AbstractSet", "MutableSet", "dict", "Dict", "Mapping",
                  "MutableMapping", "defaultdict", "DefaultDict", "OrderedDict", "Counter"}
_PY_SEQ_CTORS = {"list", "tuple", "sorted"}
_PY_HASH_CTORS = {"set", "frozenset", "dict", "defaultdict", "OrderedDict", "Counter"}
# builtins that walk their (collection) arguments once
_PY_LINEAR_BUILTINS = {"sum", "any", "all", "min", "max", "list", "set", "tuple", "dict", "frozenset", "map", "filter",
                       "enumerate", "zip", "reversed"}
_PY_LINEAR_ANY = {"join", "extend", "copy", "reverse"}             # linear whatever the receiver
_PY_LINEAR_SEQ = {"index", "count", "remove", "insert"}            # linear on a known sequence


def _py_type_kind(annotation: str) -> str:
    """'seq' / 'hash' / a bare type name from an annotation like `Optional[List[int]]` or `set[str] | None`."""
    m = re.match(r"\s*(?:typing\.)?(?:Optional\s*\[\s*)?(?:typing\.|collections\.)?([A-Za-z_]\w*)", annotation or "")
    if not m:
        return ""
    name = m.group(1)
    return "seq" if name in _PY_SEQ_TYPES else "hash" if name in _PY_HASH_TYPES else name


def _py_const_size(node) -> bool:
    """A collection whose size does not depend on the input: a literal of constants, range(10)."""
    if isinstance(node, pyast.Constant):
        return True
    if isinstance(node, (pyast.List, pyast.Tuple, pyast.Set)):
        return all(isinstance(e, pyast.Constant) for e in node.elts)
    if isinstance(node, pyast.Dict):
        return all(isinstance(e, pyast.Constant) for e in node.keys + node.values if e is not None)
    if isinstance(node, pyast.Call) and isinstance(node.func, pyast.Name) and node.func.id == "range":
        return all(isinstance(a, pyast.Constant)
                   or (isinstance(a, pyast.UnaryOp) and isinstance(a.operand, pyast.Constant)) for a in node.args)
    return False


@lru_cache(maxsize=4096)
def _py_parse(text: str, key: str = "", stype: str = "") -> tuple | None:
    """The ast nodes of a statement text (by the key it came from), or None if it does not parse.

    Cached: the nodes are shared, so callers must not modify them.
    """
    try:
        if key == "control" and stype == "ForStatement":
            return (pyast.parse(f"for {text}:\n pass").body[0].iter,)
        if key == "items":
            return tuple(i.context_expr for i in pyast.parse(f"with {text}:\n pass").body[0].items)
        try:
            return (pyast.parse(text, mode="eval").body,)
        except SyntaxError:
            return tuple(pyast.parse(text).body[:1])
    except (SyntaxError, ValueError, IndexError, AttributeError):
        return None


def _short(name: str) -> str:
    """`inner` of a nested def `outer.inner`."""
    return name.rpartition(".")[2]


def _py_bare_self_call(cls_name: str | None, method: dict) -> bool:
    """Whether a bare `f(...)` inside Python function `f` calls itself.

    True for module functions and nested defs; inside a class method a bare name is the module function
    of that name, and the method calls itself only as `self.f(...)` / `cls.f(...)`.
    """
    return cls_name in (None, "", "Module") or "." in method["name"]


def _py_self_call_text(text: str, cls_name: str | None, method: dict) -> str:
    """Text in which exactly the self-calls of a Python method are spelled as a bare `name(...)`."""
    name = re.escape(_short(method["name"]))
    if _py_bare_self_call(cls_name, method):
        return text
    text = re.sub(rf"(?<![\w.])(?={name}\s*\()", "_bare_", text)       # the module function of that name
    return re.sub(rf"\b(?:self|cls)\s*\.\s*(?={name}\s*\()", "", text)


# ── per-class context ───────────────────────────────────────────────────────────────────────────

class _Analyzer:
    def __init__(self, ast: dict):
        self.classes: dict[str, dict] = {}
        for c in self._all_classes(ast.get("classes", [])):
            self.classes.setdefault(c["name"], c)
        self.memo: dict[tuple[str, str], Cost | None] = {}
        self.stack: list[tuple[str, str]] = []
        self._py_globals: dict[str, str] | None = None     # kinds of module-level names (Python)
        self._py_attrs: dict[int, dict[str, str]] = {}      # kinds of self.* per class (Python)

    @staticmethod
    def _all_classes(classes: list[dict]):
        for c in classes:
            yield c
            yield from _Analyzer._all_classes(c.get("inner_classes", []))

    # types of names visible inside a method
    def _types(self, cls: dict, method: dict) -> dict[str, str]:
        if method.get("language") == "python":
            return self._py_types(cls, method)
        types = {f["name"]: f.get("type", "") for f in cls.get("fields", [])}
        types.update({p["name"]: p.get("type", "") for p in method.get("parameters", [])})
        for s in _walk_stmts(method.get("body", [])):
            if s.get("type") == "LocalVariableDeclaration":
                for d in s.get("declarators", []):
                    types[d["name"]] = s.get("var_type", "")
        return types

    def _lib_cost(self, receiver_type: str, op: str) -> Cost | None:
        if _TREE_TYPES.search(receiver_type) and op in _KEYED_OPS | _SEARCH_OPS:
            return LOG
        if _LIST_TYPES.search(receiver_type) and op in _SEARCH_OPS:
            return LINEAR
        if _HASH_TYPES.search(receiver_type) and op in _KEYED_OPS:
            return ZERO
        return None

    def _method_cost(self, cls_name: str, name: str, argc: int | None = None) -> Cost | None:
        """Worst cost over the overloads of cls_name.name (matching argc when known); None inside a cycle."""
        cls = self.classes.get(cls_name)
        if not cls:
            return ZERO
        overloads = [m for m in cls.get("methods", []) + cls.get("constructors", []) if m["name"] == name]
        same_arity = [m for m in overloads if argc is not None and len(m.get("parameters", [])) == argc]
        overloads = same_arity or overloads
        costs = [self.cost(cls, m) for m in overloads]
        if any(c is UNKNOWN for c in costs):
            return UNKNOWN
        return _worst(*costs) if costs else ZERO

    def _expr_cost(self, cls: dict, method: dict, types: dict[str, str], text: str) -> Cost | None:
        costs: list[Cost] = []
        if _SORT_RE.search(text):
            costs.append(NLOGN)
        if _LINEAR_CALL_RE.search(text):
            costs.append(LINEAR)
        for m in _RECEIVER_CALL_RE.finditer(text):
            recv, op = m.group(1), m.group(2)
            if recv == "this":
                continue
            rtype = types.get(recv, "")
            lib = self._lib_cost(rtype, op)
            if lib is not None:
                costs.append(lib)
                continue
            target = re.sub(r"<.*", "", rtype).strip() or recv   # field of a project class, or a static call
            if target in self.classes:
                args = _call_args(text[m.start(2):], op)
                c = self._method_cost(target, op, _argc(args[0]) if args else None)
                if c is UNKNOWN:
                    return UNKNOWN
                costs.append(c)
        own_argc = len(method.get("parameters", []))
        for name in {m.group(1) for m in _LOCAL_CALL_RE.finditer(text)} - _KEYWORDS:
            if re.search(rf"new\s+{re.escape(name)}\s*\(", text):
                continue
            for args in _call_args(text, name):
                argc = _argc(args)
                if name == method["name"] and argc == own_argc:
                    continue                          # self-recursion: handled by _recursion
                c = self._method_cost(cls["name"], name, argc)
                if c is UNKNOWN:
                    return UNKNOWN
                costs.append(c)
        return _worst(*costs)

    def _stream_cost(self, cls: dict, method: dict, types: dict[str, str], stream: dict) -> Cost | None:
        """Cost of a recognised stream chain, step by step (see core/streams.py for the shape).

        The prefix, the source and the terminal's tail are costed as plain text; every step runs once per
        element, so it costs n × its lambda; `sorted` is n log n × the comparator; `flatMap` multiplies by n
        (the inner stream it flattens). The chain text itself never reaches _SORT_RE/_LINEAR_CALL_RE.
        """
        def text_cost(text: str) -> Cost | None:
            return self._expr_cost(cls, method, types, text) if text else ZERO

        terminal = stream.get("terminal")
        costs = [text_cost(stream.get("prefix", "")), text_cost(stream["source"]["text"]), LINEAR]
        if terminal:
            costs.append(text_cost(terminal.get("tail", "")))
        for step in stream.get("ops", []) + ([terminal] if terminal else []):
            per = text_cost(step.get("args", ""))
            if per is UNKNOWN:
                return UNKNOWN
            if step["name"] == "sorted":
                costs.append(_mul(NLOGN, per))
            elif step["name"] == "flatMap":
                costs.append(_mul(LINEAR, _worst(LINEAR, per)))   # the flattened stream is itself O(n)
            else:
                costs.append(_mul(LINEAR, per))
        if UNKNOWN in costs:
            return UNKNOWN
        return _worst(*costs)

    def _stmts_cost(self, cls: dict, method: dict, types: dict[str, str], stmts: list[dict]) -> Cost | None:
        py = method.get("language") == "python"
        worst = ZERO
        for s in stmts:
            if s.get("nested_def"):    # a definition, not execution: its body is costed as its own method
                continue
            if s.get("stream"):    # the chain is the statement's whole expression: cost it by its steps
                own = [self._stream_cost(cls, method, types, s["stream"])]
            elif py:
                own = self._py_own_costs(cls, method, types, s)
            else:
                own = [self._expr_cost(cls, method, types, e) for e in _own_exprs(s)]
            inner = self._stmts_cost(cls, method, types, _nested(s))
            after = self._stmts_cost(cls, method, types, _loop_else(s))
            if UNKNOWN in own or inner is UNKNOWN or after is UNKNOWN:
                return UNKNOWN
            if py and s.get("type") == "ForStatement":     # the iterable is evaluated once, the body per item
                c = _worst(_mul(self._py_iterations(s), inner), *own)
            else:
                c = _worst(inner, *own)
                if s.get("type") in LOOP_TYPES:
                    c = _mul(_loop_cost(s), c)
            worst = _worst(worst, c, after)
        return worst

    # ── Python ──

    def _py_types(self, cls: dict, method: dict) -> dict[str, str]:
        """Collection kinds ('seq' / 'hash') or class names of the names a Python method sees."""
        if self._py_globals is None:                                     # module-level globals, once
            self._py_globals = {}
            for m in self.classes.get("Module", {}).get("methods", []):
                if m.get("synthetic"):
                    self._py_absorb(m.get("body", []), self._py_globals)
        types = dict(self._py_globals)
        if cls.get("name") != "Module":                                  # self.attr = ... anywhere in the class, once
            attrs = self._py_attrs.get(id(cls))
            if attrs is None:
                attrs = dict(self._py_globals)
                for m in cls.get("methods", []):
                    self._py_absorb(m.get("body", []), attrs, only_self=True)
                attrs = self._py_attrs[id(cls)] = {k: v for k, v in attrs.items() if k.startswith("self.")}
            types.update(attrs)
        for p in method.get("parameters", []):
            types[p["name"]] = _py_type_kind(p.get("type", ""))
        self._py_absorb(method.get("body", []), types)
        return types

    def _py_absorb(self, stmts: list[dict], types: dict[str, str], only_self: bool = False) -> None:
        """Record the kinds of names assigned in a statement subtree (`ys = set()`, `ys: list = []`)."""
        for s in _walk_stmts(stmts):
            if s.get("type") != "StatementExpression" or s.get("nested_def") or not s.get("expression"):
                continue
            nodes = _py_parse(s["expression"])
            node = nodes[0] if nodes else None
            if isinstance(node, pyast.Assign):
                pairs = []
                for t in node.targets:
                    v = node.value
                    if isinstance(t, (pyast.Tuple, pyast.List)) and isinstance(v, (pyast.Tuple, pyast.List)) \
                            and len(t.elts) == len(v.elts):          # a, b = [], set()
                        pairs += [(te, self._py_kind(types, ve)) for te, ve in zip(t.elts, v.elts)]
                    else:
                        pairs.append((t, self._py_kind(types, v)))
            elif isinstance(node, pyast.AnnAssign):
                pairs = [(node.target, _py_type_kind(pyast.unparse(node.annotation)) or self._py_kind(types, node.value))]
            else:
                continue
            for t, kind in pairs:
                if isinstance(t, pyast.Name) and not only_self:
                    types[t.id] = kind
                elif isinstance(t, pyast.Attribute) and isinstance(t.value, pyast.Name) and t.value.id == "self":
                    types[f"self.{t.attr}"] = kind

    def _py_kind(self, types: dict[str, str], node) -> str:
        """'seq' (a list/tuple/str: `in` is O(n)), 'hash' (a set/dict: O(1)), a project class name, or ''."""
        if isinstance(node, (pyast.List, pyast.Tuple, pyast.ListComp)):
            return "seq"
        if isinstance(node, (pyast.Set, pyast.Dict, pyast.SetComp, pyast.DictComp)):
            return "hash"
        if isinstance(node, pyast.Name):
            return types.get(node.id, "")
        if isinstance(node, pyast.Attribute) and isinstance(node.value, pyast.Name) and node.value.id == "self":
            return types.get(f"self.{node.attr}", "")
        if isinstance(node, pyast.Call):
            f = node.func
            if isinstance(f, pyast.Name):
                if f.id in _PY_SEQ_CTORS:
                    return "seq"
                if f.id in _PY_HASH_CTORS:
                    return "hash"
                if f.id in self.classes:
                    return f.id
            if isinstance(f, pyast.Attribute) and f.attr == "keys":
                return "hash"
            if isinstance(f, pyast.Attribute) and f.attr == "values":
                return "seq"
        return ""

    def _py_iterations(self, loop: dict) -> Cost:
        nodes = _py_parse(loop.get("control", "") or "", "control", "ForStatement")
        return ZERO if nodes and _py_const_size(nodes[0]) else LINEAR

    def _py_own_costs(self, cls: dict, method: dict, types: dict[str, str], stmt: dict) -> list[Cost | None]:
        texts = [(k, stmt[k]) for k in _EXPR_KEYS if isinstance(stmt.get(k), str)]
        if stmt.get("type") == "SwitchStatement":            # guards run at most once, like the subject
            texts += [("guard", c["guard"]) for c in stmt.get("cases", []) or [] if c.get("guard")]
        out: list[Cost | None] = []
        for key, text in texts:
            nodes = _py_parse(text, key, stmt.get("type", ""))
            if nodes is None:                                  # not Python we can read: the regex estimate
                out.append(self._expr_cost(cls, method, types, text))
            else:
                out.extend(self._py_cost(cls, method, types, n) for n in nodes)
        return out

    def _py_cost(self, cls: dict, method: dict, types: dict[str, str], node) -> Cost | None:
        def cost(n):
            return self._py_cost(cls, method, types, n)

        if isinstance(node, (pyast.ListComp, pyast.SetComp, pyast.GeneratorExp, pyast.DictComp)):
            mult, costs = ZERO, []
            for g in node.generators:              # each `for` multiplies everything after it
                costs.append(_mul_u(mult, cost(g.iter)))
                mult = _mul(mult, ZERO if _py_const_size(g.iter) else LINEAR)
                costs.extend(_mul_u(mult, cost(c)) for c in g.ifs)
            elts = [node.key, node.value] if isinstance(node, pyast.DictComp) else [node.elt]
            costs.extend(_mul_u(mult, cost(e)) for e in elts)
            return _worst_u(*costs)
        costs = [cost(c) for c in pyast.iter_child_nodes(node)]
        if isinstance(node, pyast.Compare):
            for op, right in zip(node.ops, node.comparators):
                if isinstance(op, (pyast.In, pyast.NotIn)) and self._py_kind(types, right) == "seq":
                    costs.append(LINEAR)
        elif isinstance(node, pyast.Call):
            costs.append(self._py_call_cost(cls, method, types, node))
        return _worst_u(*costs)

    def _py_call_cost(self, cls: dict, method: dict, types: dict[str, str], call) -> Cost | None:
        """Own cost of a call (its arguments are costed separately)."""
        f, args = call.func, call.args
        if isinstance(f, pyast.Name):
            name = f.id
            data = args[1:] if name in ("map", "filter") else args
            if name == "sorted":
                return ZERO if data and all(_py_const_size(a) for a in data) else NLOGN
            if name == "len":
                return ZERO
            if name in _PY_LINEAR_BUILTINS:
                if not data or all(_py_const_size(a) for a in data) or (name in ("min", "max") and len(args) > 1):
                    return ZERO
                return LINEAR
            return self._py_local_call(cls, method, name)
        if isinstance(f, pyast.Attribute):
            op, recv = f.attr, f.value
            kind = self._py_kind(types, recv)
            if op == "sort":
                return NLOGN
            if op in _PY_LINEAR_ANY:
                return LINEAR
            if kind == "seq" and (op in _PY_LINEAR_SEQ or (op == "pop" and args)):
                return LINEAR
            target = None
            if isinstance(recv, pyast.Name):
                if recv.id in ("self", "cls") and cls["name"] != "Module":
                    if op == _short(method["name"]):
                        return ZERO                    # self-recursion: handled by _recursion
                    target = cls["name"]
                elif kind in self.classes:
                    target = kind
                elif recv.id in self.classes:
                    target = recv.id
            if target:
                return self._method_cost(target, op)
        return ZERO

    def _py_local_call(self, cls: dict, method: dict, name: str) -> Cost | None:
        """An unqualified call: a nested def of this (or an enclosing) function, a module function, a class."""
        if name == _short(method["name"]) and _py_bare_self_call(cls["name"], method):
            return ZERO                                # self-recursion: handled by _recursion
        own = {m["name"] for m in cls.get("methods", [])}
        prefix = method["name"]
        while prefix:
            if f"{prefix}.{name}" in own:
                return self._method_cost(cls["name"], f"{prefix}.{name}")
            prefix = prefix.rpartition(".")[0]
        if any(m["name"] == name for m in self.classes.get("Module", {}).get("methods", [])):
            return self._method_cost("Module", name)
        if name in self.classes:
            return self._method_cost(name, "__init__")
        return ZERO

    def _recursion(self, cls: dict, method: dict, base: Cost) -> Cost | None:
        """Cost of a directly recursive method, from how it calls itself."""
        text = " ".join(_walk_exprs(method.get("body", [])))
        if method.get("language") == "python":      # f(...) or self.f(...); no overloads, defaults change argc
            text = _py_self_call_text(text, cls["name"], method)
            calls = _call_args(text, _short(method["name"]))
        else:
            own_argc = len(method.get("parameters", []))
            calls = [a for a in _call_args(text, method["name"]) if _argc(a) == own_argc]
        if not calls:
            return base
        halving = bool(re.search(r"/\s*2\b|>>\s*1\b", text))
        decrement = all(re.search(r"-\s*\d+\b", args) for args in calls)
        # an argument derived from 2·i walks down a binary tree/heap: depth log n (heapify, BST descent)
        assigns = list(_assignments(method.get("body", [])))
        doubled = {t for t, rhs in assigns if _DOUBLING.search(rhs)}
        while True:                                  # largest = left, left = 2 * i + 1  →  largest is doubled too
            more = {t for t, rhs in assigns if t not in doubled and any(re.search(rf"\b{re.escape(v)}\b", rhs) for v in doubled)}
            if not more:
                break
            doubled |= more
        doubling = any(_DOUBLING.search(a) or any(re.search(rf"\b{re.escape(v)}\b", a) for v in doubled) for a in calls)
        if len(calls) == 1:
            if halving or doubling or any("%" in a for a in calls):   # binary search, heapify, Euclid's gcd(b, a % b)
                return _mul(LOG, base)
            return _mul(LINEAR, base)
        if halving:                                  # divide and conquer, e.g. merge sort
            return (base[0], base[1] + 1) if base[0] >= 1 else LINEAR
        if decrement:                                # f(n-1) + f(n-2), towers of Hanoi
            return EXP
        return UNKNOWN

    def cost(self, cls: dict, method: dict) -> Cost | None:
        key = (cls["name"], f'{method["name"]}/{id(method)}')
        if key in self.memo:
            return self.memo[key]
        if key in self.stack:                        # mutual recursion
            return UNKNOWN
        self.stack.append(key)
        types = self._types(cls, method)
        base = self._stmts_cost(cls, method, types, method.get("body", []))
        result = UNKNOWN if base is UNKNOWN else self._recursion(cls, method, base)
        self.stack.pop()
        self.memo[key] = result
        return result


def is_recursive(method: dict, cls_name: str | None = None) -> bool:
    if method.get("language") == "python":
        name = re.escape(_short(method["name"]))
        return any(re.search(rf"(?<![\w.]){name}\s*\(", _py_self_call_text(t, cls_name, method))
                   for t in _walk_exprs(method.get("body", [])))
    else:
        name = method["name"]
        pat = re.compile(rf"(?<![\w.]){re.escape(name)}\s*\(|this\.{re.escape(name)}\s*\(")
    return any(pat.search(t) for t in _walk_exprs(method.get("body", [])))


def analyze_method(method: dict, cls: dict | None = None) -> str:
    cls = cls or {"name": "", "methods": [method], "fields": []}
    a = _Analyzer({"classes": [cls]})
    return complexity_label(a.cost(cls, method), is_recursive(method, cls["name"]))


def _rank(cost: Cost | None) -> Cost:
    return (98, 0) if cost is UNKNOWN else cost


def analyze_ast(ast: dict) -> dict[str, str]:
    """Return {'Class.method': 'O(...)'} plus bare 'method' keys when unambiguous (Java only)."""
    a = _Analyzer(ast)
    costs: dict[str, Cost | None] = {}
    recursive: dict[str, bool] = {}
    counts: dict[str, int] = {}
    for cls in ast.get("classes", []):
        names = set()
        for m in cls["methods"] + cls.get("constructors", []):
            key = f"{cls['name']}.{m['name']}"
            c = a.cost(cls, m)
            if key not in costs or _rank(c) > _rank(costs[key]):   # overloads share a key: keep the worst
                costs[key] = c
                recursive[key] = is_recursive(m, cls["name"])
            names.add(m["name"])
        for n in names:
            counts[n] = counts.get(n, 0) + 1
    result = {k: complexity_label(c, recursive[k]) for k, c in costs.items()}
    if ast.get("language") == "python":
        return result
    for cls in ast.get("classes", []):
        for m in cls["methods"]:
            if counts[m["name"]] == 1:
                result[m["name"]] = result[f"{cls['name']}.{m['name']}"]
    return result

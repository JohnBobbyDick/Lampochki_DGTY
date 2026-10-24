"""Static Big-O estimation.

A cost is ``(p, l)`` meaning ``n^p · log^l n``. A method's cost is the worst of its statements:
sequential code takes the maximum, a loop multiplies its body by the loop's own cost, and a call
adds the cost of what it calls — methods of the project (resolved recursively, with memoisation)
and well-known library operations whose cost depends on the receiver's type.
"""

from __future__ import annotations

import re

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


def loop_depth(stmts: list[dict]) -> int:
    """Maximum loop nesting depth in a statement list."""
    best = 0
    for s in stmts:
        d = loop_depth(list(_children(s)))
        if s.get("type") in LOOP_TYPES:
            d += 1
        best = max(best, d)
    return best


def find_loops(stmts: list[dict], depth: int = 0, out: list | None = None) -> list[tuple[dict, int]]:
    """All loops with their nesting depth (outermost = 1)."""
    out = [] if out is None else out
    for s in stmts:
        d = depth + (1 if s.get("type") in LOOP_TYPES else 0)
        if s.get("type") in LOOP_TYPES:
            out.append((s, d))
        find_loops(list(_children(s)), d, out)
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
_COMPOUND_LOG = re.compile(r"(\w+)\s*(?:\*=|/=)\s*\d+|(\w+)\s*(?:<<=|>>=)\s*\d+")
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


# ── per-class context ───────────────────────────────────────────────────────────────────────────

class _Analyzer:
    def __init__(self, ast: dict):
        self.classes: dict[str, dict] = {}
        for c in self._all_classes(ast.get("classes", [])):
            self.classes.setdefault(c["name"], c)
        self.memo: dict[tuple[str, str], Cost | None] = {}
        self.stack: list[tuple[str, str]] = []

    @staticmethod
    def _all_classes(classes: list[dict]):
        for c in classes:
            yield c
            yield from _Analyzer._all_classes(c.get("inner_classes", []))

    # types of names visible inside a method
    def _types(self, cls: dict, method: dict) -> dict[str, str]:
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
        worst = ZERO
        for s in stmts:
            if s.get("stream"):    # the chain is the statement's whole expression: cost it by its steps
                own = [self._stream_cost(cls, method, types, s["stream"])]
            else:
                own = [self._expr_cost(cls, method, types, e) for e in _own_exprs(s)]
            inner = self._stmts_cost(cls, method, types, list(_children(s)))
            if UNKNOWN in own or inner is UNKNOWN:
                return UNKNOWN
            c = _worst(inner, *own)
            if s.get("type") in LOOP_TYPES:
                c = _mul(_loop_cost(s), c)
            worst = _worst(worst, c)
        return worst

    def _recursion(self, method: dict, base: Cost) -> Cost | None:
        """Cost of a directly recursive method, from how it calls itself."""
        text = " ".join(_walk_exprs(method.get("body", [])))
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
        result = UNKNOWN if base is UNKNOWN else self._recursion(method, base)
        self.stack.pop()
        self.memo[key] = result
        return result


def is_recursive(method: dict) -> bool:
    name = method["name"]
    pat = re.compile(rf"(?<![\w.]){re.escape(name)}\s*\(|this\.{re.escape(name)}\s*\(")
    return any(pat.search(t) for t in _walk_exprs(method.get("body", [])))


def analyze_method(method: dict, cls: dict | None = None) -> str:
    cls = cls or {"name": "", "methods": [method], "fields": []}
    a = _Analyzer({"classes": [cls]})
    return complexity_label(a.cost(cls, method), is_recursive(method))


def _rank(cost: Cost | None) -> Cost:
    return (98, 0) if cost is UNKNOWN else cost


def analyze_ast(ast: dict) -> dict[str, str]:
    """Return {'Class.method': 'O(...)'} plus bare 'method' keys when unambiguous."""
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
                recursive[key] = is_recursive(m)
            names.add(m["name"])
        for n in names:
            counts[n] = counts.get(n, 0) + 1
    result = {k: complexity_label(c, recursive[k]) for k, c in costs.items()}
    for cls in ast.get("classes", []):
        for m in cls["methods"]:
            if counts[m["name"]] == 1:
                result[m["name"]] = result[f"{cls['name']}.{m['name']}"]
    return result

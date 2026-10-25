"""Static defect detection on the parsed AST."""

from __future__ import annotations

import ast as pyast
import io
import json
import re
import tokenize

from core.bigo_analyzer import (LOOP_TYPES, _Analyzer, _children, _loop_else, _nested, _py_parse, _walk_exprs,
                                complexity_label, find_loops, is_recursive)
from core.cfg_builder import build_cfg, build_cfg_with_map, max_line
from models.schemas import Defect

GENERIC_EXC = {"Exception", "Throwable", "RuntimeException"}


_CFG_CACHE: dict[int, tuple[dict, list]] = {}


def _cfg_nodes(method: dict) -> list:
    """CFG nodes of *method*, cached during one detect_defects run (the cache holds the dict, so ids stay unique)."""
    hit = _CFG_CACHE.get(id(method))
    if hit is not None and hit[0] is method:
        return hit[1]
    try:
        nodes, _ = build_cfg(method)
    except Exception:  # noqa: BLE001
        nodes = []
    _CFG_CACHE[id(method)] = (method, nodes)
    return nodes


def _node_id_for_line(method: dict, line: int | None) -> str:
    if line is None:
        return ""
    for n in _cfg_nodes(method):
        if n.data.get("line_start") == line and n.type not in ("start", "end"):
            return n.id
    return ""


def _start_node_id(method: dict) -> str:
    return next((n.id for n in _cfg_nodes(method) if n.type == "start"), "")


def _node_id_for_part(method: dict, part: dict | None, line: int | None) -> str:
    """Id of the CFG node built from *part* (a stream source / op / terminal dict), else by *line*."""
    if part is not None:
        try:
            nodes, _, stmt_of = build_cfg_with_map(method)
        except Exception:  # noqa: BLE001
            nodes, stmt_of = [], {}
        for n in nodes:
            if stmt_of.get(n.id) is part:
                return n.id
    return _node_id_for_line(method, line)


def _iterable(loop: dict) -> str | None:
    ctl = loop.get("control", "")
    return ctl.split(":", 1)[1].strip() if loop.get("type") == "ForStatement" and ":" in ctl else None


def _walk_stmts(stmts: list[dict]):
    for s in stmts:
        yield s
        yield from _walk_stmts(list(_children(s)))


def _contains(stmts: list[dict], pred) -> bool:
    return any(pred(s) for s in _walk_stmts(stmts))


def detect_defects(ast: dict, code: str, bigo: dict[str, str] | None = None) -> list[Defect]:
    _CFG_CACHE.clear()          # CFGs are cached only within one detection run (ASTs may change in between)
    try:
        return _detect(ast, code, bigo)
    finally:
        _CFG_CACHE.clear()


def _detect(ast: dict, code: str, bigo: dict[str, str] | None) -> list[Defect]:
    defects: list[Defect] = []
    lines = code.splitlines()
    python = ast.get("language") == "python"

    for cls in ([] if python else ast.get("classes", [])):
        for m in cls["methods"] + cls.get("constructors", []):
            qname = f"{cls['name']}.{m['name']}"
            body = m.get("body", [])

            # 1. nested loops
            loops = find_loops(body)
            for loop, depth in loops:
                if depth < 2:
                    continue
                outer = _enclosing_loop(body, loop)
                same_iter = (
                    outer is not None
                    and _iterable(outer) is not None
                    and _iterable(outer) == _iterable(loop)
                )
                power = depth
                big = _power(power)
                if same_iter:
                    msg = (f"Вложенный цикл по одной и той же коллекции «{_iterable(loop)}» — "
                           f"повторная обработка пар элементов в {qname}")
                    rec = ("Индексировать элементы через HashMap<ключ, значение> или сгруппировать за один "
                           "проход — сложность упадёт до O(n)")
                else:
                    msg = f"Вложенные циклы (глубина {depth}) в {qname}"
                    rec = "Вынести внутренний цикл в индекс/Set/Map или объединить проходы по данным"
                line = loop.get("line")
                defects.append(Defect(
                    line_start=line or 0, line_end=max_line(loop, line) or line or 0,
                    node_id=_node_id_for_line(m, line), method=qname,
                    severity="error" if power >= 3 else "warning",
                    big_o=big, big_o_after=_power(power - 1), message=msg, recommendation=rec,
                ))

            # 2/3. catch blocks
            for s in _walk_stmts(body):
                if s.get("type") != "TryStatement":
                    continue
                for c in s.get("catches", []):
                    types = c.get("types", [])
                    line = s.get("line")
                    if not c.get("body"):
                        defects.append(Defect(
                            line_start=line or 0, line_end=max_line(c, line) or line or 0,
                            node_id="", method=qname, severity="error",
                            message=f"Пустой catch ({', '.join(types)}) в {qname} — исключение проглатывается",
                            recommendation="Залогировать исключение или пробросить его дальше",
                        ))
                    if any(t.split(".")[-1] in GENERIC_EXC for t in types):
                        defects.append(Defect(
                            line_start=line or 0, line_end=line or 0, method=qname,
                            severity="warning",
                            message=f"Общий catch ({', '.join(types)}) в {qname} вместо конкретных исключений",
                            recommendation="Ловить конкретные типы исключений (IOException, NumberFormatException…)",
                        ))

            # 4. unused locals
            all_text = " ".join(_walk_exprs(body))
            for s in _walk_stmts(body):
                if s.get("type") == "LocalVariableDeclaration":
                    for d in s.get("declarators", []):
                        n = d["name"]
                        uses = len(re.findall(rf"\b{re.escape(n)}\b", all_text))
                        # the declarator itself isn't in expression strings; any use counts
                        if uses == 0:
                            defects.append(Defect(
                                line_start=s.get("line") or 0, line_end=s.get("line") or 0,
                                node_id=_node_id_for_line(m, s.get("line")), method=qname,
                                severity="hint",
                                message=f"Переменная «{n}» объявлена, но не используется",
                                recommendation="Удалить неиспользуемую переменную",
                            ))

    if python:
        defects.extend(_python_defects(ast, code))
    else:
        defects.extend(_stream_defects(ast))

    # 5. unused imports
    body_text = "\n".join(l for l in lines if not l.strip().startswith("import "))
    for imp in ([] if python else ast.get("imports", [])):
        if imp.get("wildcard") or imp.get("static"):
            continue
        simple = imp["path"].split(".")[-1]
        if not re.search(rf"\b{re.escape(simple)}\b", body_text):
            ln = next((i + 1 for i, l in enumerate(lines) if imp["path"] in l and l.strip().startswith("import")), 1)
            defects.append(Defect(
                line_start=ln, line_end=ln, severity="hint",
                message=f"Неиспользуемый импорт {imp['path']}",
                recommendation="Удалить импорт",
            ))

    # 6. duplicated methods
    seen: dict[str, str] = {}
    for cls in ast.get("classes", []):
        for m in cls["methods"]:
            if len(m.get("body", [])) < 2:
                continue
            key = json.dumps(_strip_lines(m["body"], _PY_POS_KEYS if python else ("line",)), sort_keys=True)
            q = f"{cls['name']}.{m['name']}"
            if key in seen:
                defects.append(Defect(
                    line_start=m.get("line_start") or 0, line_end=(m.get("span") or {}).get("end", 0),
                    method=q, severity="warning",
                    message=f"Дублирование кода: тело {q} совпадает с {seen[key]}",
                    recommendation="Вынести общую логику в один метод",
                ))
            else:
                seen[key] = q

    # 7. recursion hint
    for key, val in (bigo or {}).items():
        exponential = val == "O(2^n)"
        if ("рекурсия" in val or exponential) and "." in key:
            cls_name, mname = key.split(".", 1)
            for cls in ast.get("classes", []):
                for m in cls["methods"]:
                    if cls["name"] == cls_name and m["name"] == mname:
                        if python and not is_recursive(m, cls_name):
                            continue        # O(2^n) inherited from a call (print_table → fib), not its own recursion
                        span = dict(line_start=m.get("line_start") or 0, line_end=(m.get("span") or {}).get("end", 0), method=key)
                        if exponential:
                            defects.append(Defect(
                                **span, severity="warning", big_o="O(2^n)", big_o_after="O(n)",
                                message=f"Рекурсия в {key} вызывает себя дважды с уменьшением на 1 — "
                                        f"время растёт экспоненциально",
                                recommendation="Запоминать уже посчитанные значения (мемоизация) или считать "
                                               "итеративно снизу вверх — сложность упадёт до O(n)",
                            ))
                        else:
                            defects.append(Defect(
                                **span, severity="hint", big_o="O(?)",
                                message=f"Рекурсия в {key} — сложность требует анализа",
                                recommendation="Проверить глубину рекурсии и рассмотреть мемоизацию/итерацию",
                            ))

    order = {"error": 0, "warning": 1, "hint": 2, "info": 2}
    defects.sort(key=lambda d: (order.get(d.severity, 3), d.line_start))
    return defects


_PY_POS_KEYS = ("line", "line_end", "id", "span", "header")


def _power(n: int) -> str:
    """O(n^k) in the analyzer's notation: O(1), O(n), O(n²)…"""
    return complexity_label((max(n, 0), 0))


def _strip_lines(o, keys: tuple[str, ...] = ("line",)):
    """*o* without its position keys (Python statements also carry ids and spans)."""
    if isinstance(o, dict):
        return {k: _strip_lines(v, keys) for k, v in o.items() if k not in keys}
    if isinstance(o, list):
        return [_strip_lines(i, keys) for i in o]
    return o


def _enclosing_loop(stmts: list[dict], target: dict) -> dict | None:
    def rec(items: list[dict], parent: dict | None) -> dict | None | bool:
        for s in items:
            if s is target:
                return parent if parent is not None else False
            nxt = s if s.get("type") in LOOP_TYPES else parent
            r = rec(_nested(s), nxt)
            if r is None:
                r = rec(_loop_else(s), parent)     # a Python loop's `else` runs after the loop, not in it
            if r is not None:
                return r
        return None

    r = rec(stmts, None)
    return r or None


# Stream API rules (decomposed chains only: see `stmt["stream"]`)

_TO_COLLECTION = re.compile(r"^Collectors\.(toList|toSet)\(\)$")
_MUTATE = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*(add|put|remove)\s*\(")
_LAMBDA_PARAMS = re.compile(r"^\s*(?:\(([^)]*)\)|([A-Za-z_]\w*))\s*->")
_LIST_ADD = re.compile(r"^[A-Za-z_][\w.]*\.add\(.*\)$", re.S)


def _loop_collection(loop: dict) -> str | None:
    it = _iterable(loop)
    if it:
        return it
    if loop.get("type") == "ForStatement":
        m = re.search(r"([A-Za-z_][\w.]*)\.size\(\)", loop.get("control", ""))
        if m:
            return m.group(1)
    return None


def _unwrap(stmts: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in stmts:
        if s.get("type") in ("BlockStatement", "WithStatement"):
            out.extend(_unwrap(s.get("body", [])))
        else:
            out.append(s)
    return out


def _is_add_loop(loop: dict) -> bool:
    if loop.get("type") != "ForStatement" or _iterable(loop) is None:
        return False
    body = _unwrap(loop.get("body", []))
    if len(body) != 1:
        return False
    s = body[0]
    if s.get("type") == "IfStatement":
        if _unwrap(s.get("else", [])):
            return False
        inner = _unwrap(s.get("then", []))
        if len(inner) != 1:
            return False
        s = inner[0]
    return s.get("type") == "StatementExpression" and bool(_LIST_ADD.match(s.get("expression", "")))


def _stream_defects(ast: dict) -> list[Defect]:
    found: list[Defect] = []
    for cls in ast.get("classes", []):
        for m in cls["methods"] + cls.get("constructors", []):
            qname = f"{cls['name']}.{m['name']}"
            body = m.get("body", [])

            def add(line, severity, message, rec, big_o="", part=None, after=""):
                found.append(Defect(
                    line_start=line or 0, line_end=line or 0, node_id=_node_id_for_part(m, part, line),
                    method=qname, severity=severity, big_o=big_o, big_o_after=after, message=message,
                    recommendation=rec,
                ))

            # 1. stream over the collection that the enclosing loop iterates
            reported: set[int] = set()
            for loop, _ in find_loops(body):
                coll = _loop_collection(loop)
                if not coll:
                    continue
                for s in _walk_stmts(_nested(loop)):
                    st = s.get("stream")
                    if not st or id(s) in reported:
                        continue
                    if st["source"]["text"] in (f"{coll}.stream()", f"{coll}.parallelStream()"):
                        reported.add(id(s))
                        add(st["source"]["line"], "warning",
                            f"Повторный стрим по коллекции «{coll}» внутри цикла по ней в {qname} — "
                            f"на каждый элемент коллекция обходится заново",
                            "Вынести стрим из цикла или посчитать результат за один проход (Map/Set) — O(n) вместо O(n²)",
                            "O(n²)", part=st["source"], after="O(n)")

            for s in _walk_stmts(body):
                st = s.get("stream")
                if st:
                    ops, term = st["ops"], st["terminal"]
                    if term:
                        name, tail = term["name"], term["tail"]
                        if name == "collect" and _TO_COLLECTION.match(term["args"].strip()) \
                                and tail.startswith(".size()"):
                            add(term["line"], "hint",
                                f"Подсчёт элементов через сбор в коллекцию и size() в {qname} — используйте count()",
                                "Заменить collect(...).size() на count(): список не нужно создавать ради размера",
                                part=term)
                        if name in ("findFirst", "findAny") and tail.startswith(".isPresent()") \
                                and ops and ops[-1]["name"] == "filter":
                            add(term["line"], "hint",
                                f"filter(...).{name}().isPresent() в {qname} — используйте anyMatch(...)",
                                "Заменить на anyMatch(условие): короче и сразу прекращает обход",
                                part=term)
                        if name == "findFirst" and ops and ops[-1]["name"] == "sorted":
                            add(term["line"], "warning",
                                f"sorted(...).findFirst() в {qname} сортирует всё ради одного элемента — "
                                f"используйте min(...)/max(...)",
                                "Заменить на min(...)/max(...) с компаратором — O(n) вместо O(n log n)",
                                "O(n log n)", part=term, after="O(n)")
                        if name in ("forEach", "forEachOrdered"):
                            args = term["args"]
                            lm = _LAMBDA_PARAMS.match(args)
                            params = set()
                            if lm:
                                params = {p.strip().split()[-1] for p in (lm.group(1) or lm.group(2)).split(",") if p.strip()}
                            if lm and any(mm.group(1) not in params for mm in _MUTATE.finditer(args)):
                                add(term["line"], "hint",
                                    f"forEach в {qname} изменяет внешнюю коллекцию — соберите результат через collect(...)",
                                    "Заменить forEach(x -> list.add(x)) на collect(Collectors.toList()) и т. п.",
                                    part=term)
                if _is_add_loop(s):
                    add(s.get("line"), "hint",
                        f"Цикл можно заменить стримом в {qname}: xs.stream().filter(...).collect(...)",
                        "Заменить цикл на xs.stream().filter(условие).map(...).collect(Collectors.toList())")
    return found


# Python rules (methods with `language: "python"`, see core/py_parser.py)

_PY_GENERIC_EXC = {"Exception", "BaseException"}
_PY_MUTABLE_CALLS = {"list", "dict", "set", "bytearray", "defaultdict", "OrderedDict", "Counter", "deque"}
_PY_STR_ANN = re.compile(r"^\s*(?:typing\.)?(?:Optional\s*\[\s*)?str\b")
_PY_EXPR_KEYS = ("expression", "condition", "control", "items")
_PY_COMPS = (pyast.ListComp, pyast.SetComp, pyast.DictComp, pyast.GeneratorExp)


def _py_for(loop: dict):
    """The `ast.For` of a Python for loop's header, or None."""
    if loop.get("type") != "ForStatement":
        return None
    try:
        return pyast.parse(f"for {loop.get('control', '')}:\n pass").body[0]
    except (SyntaxError, ValueError, IndexError):
        return None


def _py_iterable(loop: dict) -> str | None:
    node = _py_for(loop)
    return pyast.unparse(node.iter) if node is not None else None


def _py_is_str_expr(node) -> bool:
    if isinstance(node, pyast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, pyast.JoinedStr):
        return True
    return isinstance(node, pyast.Call) and isinstance(node.func, pyast.Name) and node.func.id == "str"


def _py_stmt_node(s: dict):
    if s.get("type") != "StatementExpression" or s.get("nested_def") or not s.get("expression"):
        return None
    nodes = _py_parse(s["expression"])
    return nodes[0] if nodes else None


def _py_str_names(method: dict) -> set[str]:
    """Names a Python method binds to a string: `s = ""`, `s = str(x)`, `s: str = …`, a `str` parameter."""
    names = {p["name"] for p in method.get("parameters", []) if _PY_STR_ANN.match(p.get("type", "") or "")}
    for s in _walk_stmts(method.get("body", [])):
        node = _py_stmt_node(s)
        if isinstance(node, pyast.Assign) and _py_is_str_expr(node.value):
            names |= {t.id for t in node.targets if isinstance(t, pyast.Name)}
        elif isinstance(node, pyast.AnnAssign) and isinstance(node.target, pyast.Name) \
                and (_PY_STR_ANN.match(pyast.unparse(node.annotation))
                     or (node.value is not None and _py_is_str_expr(node.value))):
            names.add(node.target.id)
    return names


def _py_concat_target(node, str_names: set[str]) -> str | None:
    """`s` of `s += …` / `s = s + …` where `s` is a known string."""
    if isinstance(node, pyast.AugAssign) and isinstance(node.op, pyast.Add) \
            and isinstance(node.target, pyast.Name) and node.target.id in str_names:
        return node.target.id
    if isinstance(node, pyast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], pyast.Name) \
            and isinstance(node.value, pyast.BinOp) and isinstance(node.value.op, pyast.Add):
        name, left = node.targets[0].id, node.value
        while isinstance(left, pyast.BinOp) and isinstance(left.op, pyast.Add):
            left = left.left
        if name in str_names and isinstance(left, pyast.Name) and left.id == name:
            return name
    return None


def _py_memberships(node, in_loop: bool, out: list) -> None:
    """Collections searched by `x in c` / `x not in c` once per iteration (of a loop or a comprehension)."""
    if isinstance(node, _PY_COMPS):
        for i, gen in enumerate(node.generators):
            _py_memberships(gen.iter, in_loop or i > 0, out)
            for cond in gen.ifs:
                _py_memberships(cond, True, out)
        for part in ((node.key, node.value) if isinstance(node, pyast.DictComp) else (node.elt,)):
            _py_memberships(part, True, out)
        return
    if isinstance(node, pyast.Compare) and in_loop:
        out += [right for op, right in zip(node.ops, node.comparators) if isinstance(op, (pyast.In, pyast.NotIn))]
    for child in pyast.iter_child_nodes(node):
        _py_memberships(child, in_loop, out)


def _py_range_len(loop: dict) -> str | None:
    """`x` of `for i in range(len(x))`."""
    node = _py_for(loop)
    if node is None or not isinstance(node.target, pyast.Name):
        return None
    it = node.iter
    if isinstance(it, pyast.Call) and isinstance(it.func, pyast.Name) and it.func.id == "range" \
            and len(it.args) == 1 and not it.keywords:
        inner = it.args[0]
        if isinstance(inner, pyast.Call) and isinstance(inner.func, pyast.Name) and inner.func.id == "len" \
                and len(inner.args) == 1 and not inner.keywords:
            return pyast.unparse(inner.args[0])
    return None


def _python_defects(ast: dict, code: str) -> list[Defect]:
    """The Python rules; the shared ones (duplication, recursion) run in detect_defects."""
    found: list[Defect] = []
    analyzer = _Analyzer(ast)
    by_line: dict[int, tuple[str, dict]] = {}

    for cls in ast.get("classes", []):
        for m in cls["methods"]:
            qname = f"{cls['name']}.{m['name']}"
            if not m.get("synthetic"):
                by_line.setdefault(m.get("line_start") or 0, (qname, m))
            body = m.get("body", [])
            loops = find_loops(body)
            str_names = _py_str_names(m)
            types: dict[str, str] | None = None
            seen: set[tuple[int, str]] = set()

            def add(line, severity, message, rec, big_o="", line_end=None, after="", m=m, qname=qname):
                found.append(Defect(
                    line_start=line or 0, line_end=line_end or line or 0, node_id=_node_id_for_line(m, line),
                    method=qname, severity=severity, big_o=big_o, big_o_after=after, message=message,
                    recommendation=rec,
                ))

            def memberships(s: dict, keys: tuple[str, ...], in_loop: bool, m=m, cls=cls, qname=qname,
                            str_names=str_names, seen=seen):
                nonlocal types
                if s.get("nested_def"):
                    return
                colls: list = []
                for key in keys:
                    text = s.get(key)
                    if isinstance(text, str) and text:
                        for node in _py_parse(text, key, s.get("type", "")) or ():
                            _py_memberships(node, in_loop, colls)
                for coll in colls:
                    if isinstance(coll, pyast.Name) and coll.id in str_names:
                        continue        # `in` on a string is a substring search, a set does not help
                    types = types if types is not None else analyzer._py_types(cls, m)
                    text = pyast.unparse(coll)
                    if not analyzer._py_searches_seq(types, coll) or (id(s), text) in seen:
                        continue
                    seen.add((id(s), text))
                    add(s.get("line"), "warning",
                        f"Поиск в списке «{text}» внутри цикла в {qname} — каждая проверка in перебирает весь список",
                        f"Превратите «{text}» в set до цикла (или храните элементы сразу в set) — проверка in "
                        f"станет O(1)", "O(n²)", after="O(n)")

            # 3. nested loops (the same collection → pairs)
            for loop, depth in loops:
                if depth < 2:
                    continue
                outer = _enclosing_loop(body, loop)
                it = _py_iterable(loop)
                big = _power(depth)
                if outer is not None and it is not None and _py_iterable(outer) == it:
                    msg = f"Вложенный цикл по одной и той же коллекции «{it}» — повторная обработка пар элементов в {qname}"
                    rec = ("Сгруппировать элементы по ключу в dict/set за один проход, а пары перебирать через "
                           "itertools.combinations — без повторной обработки")
                else:
                    msg = f"Вложенные циклы (глубина {depth}) в {qname}"
                    rec = "Заменить внутренний поиск проверкой в set/dict или объединить проходы по данным"
                line = loop.get("line")
                add(line, "error" if depth >= 3 else "warning", msg, rec, big, max_line(loop, line) or line,
                    after=_power(depth - 1))

            # 1/2. string concatenation and list membership once per iteration
            in_loops: set[int] = set()
            for loop, _ in loops:
                if loop.get("type") == "WhileStatement":      # the condition is evaluated on every iteration
                    memberships(loop, ("condition",), True)
                for s in _walk_stmts(_nested(loop)):
                    in_loops.add(id(s))
                    name = _py_concat_target(_py_stmt_node(s), str_names)
                    if name and (id(s), "+=") not in seen:
                        seen.add((id(s), "+="))
                        add(s.get("line"), "warning",
                            f"Конкатенация строки «{name}» в цикле в {qname} — каждое сложение копирует всю строку",
                            "Собрать части в список и объединить один раз: ''.join(parts)", "O(n²)", after="O(n)")
                    memberships(s, _PY_EXPR_KEYS, True)
            for s in _walk_stmts(body):                       # comprehensions outside loops
                if id(s) not in in_loops:
                    memberships(s, _PY_EXPR_KEYS, False)

            # 6. for i in range(len(x))
            for loop, _ in loops:
                coll = _py_range_len(loop)
                if coll is not None:
                    add(loop.get("line"), "hint",
                        f"Перебор индексов «for {loop.get('control', '')}» в {qname} — элементы удобнее "
                        f"перебирать напрямую",
                        f"Писать for item in {coll}, а если нужен индекс — for i, item in enumerate({coll})")

            # 4. swallowed / general except
            for s in _walk_stmts(body):
                if s.get("type") != "TryStatement":
                    continue
                for c in s.get("catches", []):
                    exc = [t for raw in c.get("types", []) or [] for t in re.split(r"[\s(),]+", raw) if t]
                    label = f"except {', '.join(exc)}" if exc else "except"
                    line = c.get("line") or s.get("line")
                    cbody = c.get("body", [])
                    stub = (cbody[0].get("expression") or "").strip() \
                        if len(cbody) == 1 and cbody[0].get("type") == "StatementExpression" else ""
                    generic = not exc or any(t.split(".")[-1] in _PY_GENERIC_EXC for t in exc)
                    if stub in ("pass", "...") and generic:
                        add(line, "error",
                            f"Исключение проглатывается: «{label}: {stub}» в {qname} — ошибка исчезает без следа",
                            "Перехватывать конкретное исключение и залогировать его (logging.exception) "
                            "или пробросить дальше через raise", line_end=max_line(c, line) or line)
                    if not exc:
                        add(line, "warning",
                            f"Общий except без типа в {qname} перехватывает все исключения, включая "
                            f"KeyboardInterrupt и SystemExit",
                            "Указать конкретный тип исключения: except ValueError: (или хотя бы except Exception:)")

    # 5. mutable default arguments and unused imports: straight from the source
    try:
        tree = pyast.parse(code)
    except (SyntaxError, ValueError):
        return found
    imports: list = []
    for node in pyast.walk(tree):
        if isinstance(node, (pyast.Import, pyast.ImportFrom)):
            imports.append(node)
        if not isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
            continue
        args = node.args
        positional = args.posonlyargs + args.args
        pairs = list(zip(positional[len(positional) - len(args.defaults):], args.defaults))
        pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None]
        qname, owner = by_line.get(node.lineno, (node.name, None))
        for arg, default in pairs:
            mutable = isinstance(default, (pyast.List, pyast.Dict, pyast.Set, *_PY_COMPS)) or (
                isinstance(default, pyast.Call) and isinstance(default.func, pyast.Name)
                and default.func.id in _PY_MUTABLE_CALLS)
            if not mutable:
                continue
            seg = pyast.get_source_segment(code, default) or pyast.unparse(default)
            found.append(Defect(
                line_start=default.lineno, line_end=default.end_lineno or default.lineno, method=qname,
                node_id=_start_node_id(owner) if owner is not None else "",
                severity="warning",
                message=f"Изменяемое значение по умолчанию «{arg.arg}={seg}» в {qname} — один и тот же объект "
                        f"общий для всех вызовов",
                recommendation=f"Используйте None по умолчанию и создавайте объект в теле: "
                               f"if {arg.arg} is None: {arg.arg} = {seg}",
            ))

    skip = {ln for imp in imports for ln in range(imp.lineno, (imp.end_lineno or imp.lineno) + 1)}
    used: set[str] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(code).readline):
            if tok.type == tokenize.NAME and tok.start[0] not in skip:
                used.add(tok.string)
    except (tokenize.TokenError, SyntaxError):
        return found
    for node in tree.body:                                   # names exported through __all__ count as used
        if isinstance(node, (pyast.Assign, pyast.AugAssign, pyast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, pyast.Assign) else [node.target]
            if any(isinstance(t, pyast.Name) and t.id == "__all__" for t in targets)                     and isinstance(node.value, (pyast.List, pyast.Tuple)):
                used |= {e.value for e in node.value.elts
                         if isinstance(e, pyast.Constant) and isinstance(e.value, str)}
    for imp in sorted(imports, key=lambda i: (i.lineno, i.col_offset)):
        if isinstance(imp, pyast.ImportFrom) and imp.module == "__future__":
            continue
        for alias in imp.names:
            if alias.name == "*":
                continue
            if isinstance(imp, pyast.ImportFrom):
                bound = alias.asname or alias.name
                what = f"{alias.name} из {'.' * imp.level}{imp.module or ''}"
            else:
                bound = alias.asname or alias.name.split(".")[0]
                what = alias.name
            if alias.asname:
                what += f" (как {alias.asname})"
            if bound not in used:
                found.append(Defect(
                    line_start=imp.lineno, line_end=imp.lineno, severity="hint",
                    message=f"Неиспользуемый импорт {what}", recommendation="Удалить импорт",
                ))
    return found

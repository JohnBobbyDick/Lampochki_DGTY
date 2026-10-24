"""Static defect detection on the parsed AST."""

from __future__ import annotations

import json
import re

from core.bigo_analyzer import LOOP_TYPES, _children, _walk_exprs, find_loops
from core.cfg_builder import build_cfg, build_cfg_with_map, max_line
from models.schemas import Defect

GENERIC_EXC = {"Exception", "Throwable", "RuntimeException"}


def _node_id_for_line(method: dict, line: int | None) -> str:
    if line is None:
        return ""
    try:
        nodes, _ = build_cfg(method)
    except Exception:  # noqa: BLE001
        return ""
    for n in nodes:
        if n.data.get("line_start") == line and n.type not in ("start", "end"):
            return n.id
    return ""


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
    defects: list[Defect] = []
    lines = code.splitlines()

    for cls in ast.get("classes", []):
        for m in cls["methods"] + cls.get("constructors", []):
            qname = f"{cls['name']}.{m['name']}"
            body = m.get("body", [])

            # 1. nested loops ------------------------------------------------
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
                big = "O(n²)" if power == 2 else "O(n³)" if power == 3 else f"O(n^{power})"
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
                    big_o=big, message=msg, recommendation=rec,
                ))

            # 2/3. catch blocks ---------------------------------------------
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

            # 4. unused locals -----------------------------------------------
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

    defects.extend(_stream_defects(ast))

    # 5. unused imports -------------------------------------------------------
    body_text = "\n".join(l for l in lines if not l.strip().startswith("import "))
    for imp in ast.get("imports", []):
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

    # 6. duplicated methods ----------------------------------------------------
    seen: dict[str, str] = {}
    for cls in ast.get("classes", []):
        for m in cls["methods"]:
            if len(m.get("body", [])) < 2:
                continue
            key = json.dumps(_strip_lines(m["body"]), sort_keys=True)
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

    # 7. recursion hint ----------------------------------------------------------
    for key, val in (bigo or {}).items():
        exponential = val == "O(2^n)"
        if ("рекурсия" in val or exponential) and "." in key:
            cls_name, mname = key.split(".", 1)
            for cls in ast.get("classes", []):
                for m in cls["methods"]:
                    if cls["name"] == cls_name and m["name"] == mname:
                        span = dict(line_start=m.get("line_start") or 0, line_end=(m.get("span") or {}).get("end", 0), method=key)
                        if exponential:
                            defects.append(Defect(
                                **span, severity="warning", big_o="O(2^n)",
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


def _strip_lines(o):
    if isinstance(o, dict):
        return {k: _strip_lines(v) for k, v in o.items() if k != "line"}
    if isinstance(o, list):
        return [_strip_lines(i) for i in o]
    return o


def _enclosing_loop(stmts: list[dict], target: dict) -> dict | None:
    def rec(items: list[dict], parent: dict | None) -> dict | None | bool:
        for s in items:
            if s is target:
                return parent if parent is not None else False
            nxt = s if s.get("type") in LOOP_TYPES else parent
            r = rec(list(_children(s)), nxt)
            if r is not None:
                return r
        return None

    r = rec(stmts, None)
    return r or None


# ---------------------------------------------------------------------------
# Stream API rules (decomposed chains only: see `stmt["stream"]`)
# ---------------------------------------------------------------------------

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

            def add(line, severity, message, rec, big_o="", part=None):
                found.append(Defect(
                    line_start=line or 0, line_end=line or 0, node_id=_node_id_for_part(m, part, line),
                    method=qname, severity=severity, big_o=big_o, message=message, recommendation=rec,
                ))

            # 1. stream over the collection that the enclosing loop iterates
            reported: set[int] = set()
            for loop, _ in find_loops(body):
                coll = _loop_collection(loop)
                if not coll:
                    continue
                for s in _walk_stmts(list(_children(loop))):
                    st = s.get("stream")
                    if not st or id(s) in reported:
                        continue
                    if st["source"]["text"] in (f"{coll}.stream()", f"{coll}.parallelStream()"):
                        reported.add(id(s))
                        add(st["source"]["line"], "warning",
                            f"Повторный стрим по коллекции «{coll}» внутри цикла по ней в {qname} — "
                            f"на каждый элемент коллекция обходится заново",
                            "Вынести стрим из цикла или посчитать результат за один проход (Map/Set) — O(n) вместо O(n²)",
                            "O(n²)", part=st["source"])

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
                                "O(n log n)", part=term)
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

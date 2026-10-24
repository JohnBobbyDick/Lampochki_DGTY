"""Static defect detection on the parsed AST."""

from __future__ import annotations

import json
import re

from core.bigo_analyzer import LOOP_TYPES, _children, _walk_exprs, find_loops
from core.cfg_builder import build_cfg, max_line
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

"""Big O «было → станет» for a patch: complexity of the affected methods before and after applying it."""
from __future__ import annotations

import re

from ai import patcher
from core.bigo_analyzer import analyze_ast


def _parse(code: str, language: str | None = None) -> dict:
    """Normalised AST of Java or Python source (Python module functions live in the pseudo-class "Module")."""
    from core import lang
    from core.runner import is_python_code
    return lang.get("python" if is_python_code(code, language) else "java").parse(code)["ast"] or {}


def _labels(code: str, language: str | None = None) -> dict[str, str]:
    return {k: v for k, v in analyze_ast(_parse(code, language)).items() if "." in k}


def affected_methods(code: str, start: int, end: int, language: str | None = None) -> set[str]:
    """``Class.method`` whose span intersects lines [start, end]."""
    out: set[str] = set()
    for cls in _parse(code, language).get("classes", []):
        for m in cls.get("methods", []) + cls.get("constructors", []):
            span = m.get("span") or {}
            s, e = span.get("start"), span.get("end")
            if s is not None and e is not None and s <= end and start <= e:
                out.add(f"{cls['name']}.{m['name']}")
    return out


def bigo_change(code: str, patched: str, start: int, end: int, language: str | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """(before, after): methods touched by the patch plus any method whose label changed."""
    before_all, after_all = _labels(code, language), _labels(patched, language)
    names = affected_methods(code, start, end, language) | {
        k for k in before_all.keys() & after_all.keys() if before_all[k] != after_all[k]
    }
    names = {n for n in names if n in before_all and n in after_all}
    return {n: before_all[n] for n in names}, {n: after_all[n] for n in names}


_RANK_EXP = (99, 0)
_SUP = {"²": 2, "³": 3, "⁴": 4, "⁵": 5}


def _rank(label: str) -> tuple[int, int] | None:
    """(p, l) of n^p * log^l n; O(2^n) above every polynomial; None when unknown."""
    if "2^n" in label:
        return _RANK_EXP
    if "?" in label or not label.startswith("O("):
        return None
    inner = label[2:-1].strip()
    if inner == "1":
        return (0, 0)
    p = l = 0
    m = re.search(r"log(?:([²³⁴⁵])|\^(\d+))? n", inner)
    if m:
        l = _SUP.get(m.group(1)) or int(m.group(2) or 1)
        inner = inner[:m.start()] + inner[m.end():]
    m = re.search(r"n(?:([²³⁴⁵])|\^(\d+))?", inner)
    if m:
        p = _SUP.get(m.group(1)) or int(m.group(2) or 1)
    return (p, l)


def _score(before: dict[str, str], after: dict[str, str]) -> tuple[int, int]:
    """Sum of ranks of the patch's affected methods (unknown after -> its before)."""
    tp = tl = 0
    for name, lab in after.items():
        r = _rank(lab) or _rank(before.get(name, "")) or (0, 0)
        tp, tl = tp + r[0], tl + r[1]
    return tp, tl


def combined_bigo(code: str, patches: list[dict], language: str | None = None) -> dict[str, str]:
    """``after`` labels when several patches are applied together (estimate, not compiled).

    Overlapping patches form a group of which only the best single one is applied.
    """
    found = []  # (start, end, patch)
    for p in patches:
        rng = patcher.locate(code, p.get("old_code", ""), p.get("start_line") or None)
        if rng:
            found.append((rng[0], rng[1], p))
    if not found:
        return {}
    found.sort(key=lambda t: (t[0], t[1]))
    groups: list[list[tuple[int, int, dict]]] = []
    cur_end = 0
    for item in found:
        if groups and item[0] <= cur_end:
            groups[-1].append(item)
            cur_end = max(cur_end, item[1])
        else:
            groups.append([item])
            cur_end = item[1]
    chosen = []
    for g in groups:
        best, best_score = None, None
        for s, e, p in g:
            if len(g) == 1:
                best = (s, e, p)
                break
            patched, _ = patcher.replace_range(code, s, e, p["new_code"], p.get("imports"), language)
            sc = _score(*bigo_change(code, patched, s, e, language))
            if best_score is None or sc < best_score:
                best, best_score = (s, e, p), sc
        chosen.append(best)
    patched, imports = code, []
    for s, e, p in sorted(chosen, key=lambda t: -t[0]):
        patched, _ = patcher.replace_range(patched, s, e, p["new_code"], None, language)
        imports += list(p.get("imports") or [])
    patched, _ = patcher.add_imports(patched, imports, language)
    before_all, after_all = _labels(code, language), _labels(patched, language)
    names: set[str] = set()
    for s, e, _ in chosen:
        names |= affected_methods(code, s, e, language)
    names |= {k for k in before_all.keys() & after_all.keys() if before_all[k] != after_all[k]}
    return {n: after_all[n] for n in sorted(names) if n in before_all and n in after_all}

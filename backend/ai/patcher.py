"""Turn an LLM "replace this fragment with that one" suggestion into a safe edit of the source.

The model returns ``old_code`` (a verbatim fragment of the user's code) and ``new_code``. We locate the
fragment (whitespace-tolerant, must be unambiguous), re-indent the replacement, add missing imports and
validate the result (syntax + compiler/interpreter) *before* anything is offered for application.
"""

from __future__ import annotations

import asyncio
import re

from core import runner
from core import lang

from ai import bigo_diff

_IMPORT_RE = re.compile(r"^\s*import\s+(static\s+)?([\w.]+(?:\.\*)?)\s*;", re.M)


def normalize(code: str) -> str:
    return code.replace("\r\n", "\n").replace("\r", "\n")


def locate(code: str, old: str, hint_line: int | None = None) -> tuple[int, int] | None:
    """1-based inclusive line range of *old* inside *code*, or None if absent / ambiguous.

    Lines are compared stripped and blank lines are ignored, so indentation differences don't matter.
    With several hits the one closest to *hint_line* wins (None without a hint).
    """
    lines = code.split("\n")
    want = [l.strip() for l in normalize(old).split("\n") if l.strip()]
    if not want:
        return None
    idx = [i for i, l in enumerate(lines) if l.strip()]
    stripped = [lines[i].strip() for i in idx]
    hits = [
        (idx[p], idx[p + len(want) - 1])
        for p in range(len(stripped) - len(want) + 1)
        if stripped[p:p + len(want)] == want
    ]
    if not hits:
        return None
    if len(hits) > 1:
        if hint_line is None:
            return None
        hits.sort(key=lambda h: abs(h[0] + 1 - hint_line))
    return hits[0][0] + 1, hits[0][1] + 1


def reindent(new: str, base_indent: str) -> str:
    """Dedent *new* to its own minimum indent, then indent every line with *base_indent*."""
    rows = normalize(new).strip("\n").split("\n")
    common = min((len(r) - len(r.lstrip()) for r in rows if r.strip()), default=0)
    return "\n".join((base_indent + r[common:]).rstrip() if r.strip() else "" for r in rows)


def add_imports(code: str, imports: list[str], language: str | None = None) -> tuple[str, list[str]]:
    """Insert missing ``import`` lines; returns (new code, imports actually added)."""
    if runner.is_python_code(code, language) and not _IMPORT_RE.search(code):
        # Python imports: e.g. "math", "from typing import List"
        lines = code.split("\n")
        added = []
        for raw in imports:
            clean = raw.strip()
            if not any(clean == l.strip() for l in lines):
                added.append(clean if clean.startswith("import ") or clean.startswith("from ") else f"import {clean}")
        if not added:
            return code, []
        return "\n".join(added) + "\n\n" + code, added

    have = {m.group(2) for m in _IMPORT_RE.finditer(code)}
    added: list[str] = []
    for raw in imports:
        imp = raw.strip().removeprefix("import ").rstrip(";").strip()
        if not re.fullmatch(r"[\w.]+(\.\*)?", imp or ""):
            continue
        pkg_wild = imp.rsplit(".", 1)[0] + ".*" if "." in imp else None
        if imp in have or (pkg_wild and pkg_wild in have) or imp in added:
            continue
        added.append(imp)
    if not added:
        return code, []

    lines = code.split("\n")
    block = [f"import {i};" for i in added]
    last_import = max((i for i, l in enumerate(lines) if _IMPORT_RE.match(l)), default=None)
    if last_import is not None:
        lines[last_import + 1:last_import + 1] = block
    else:
        pkg = next((i for i, l in enumerate(lines) if l.strip().startswith("package ")), None)
        at = 0 if pkg is None else pkg + 1
        lines[at:at] = ([""] if pkg is not None else []) + block + ([""] if at < len(lines) and lines[at].strip() else [])
    return "\n".join(lines), added


def replace_range(code: str, start: int, end: int, new: str, imports: list[str] | None = None,
                  language: str | None = None) -> tuple[str, list[str]]:
    lines = code.split("\n")
    first = lines[start - 1]
    base = first[: len(first) - len(first.lstrip())]
    lines[start - 1:end] = reindent(new, base).split("\n")
    return add_imports("\n".join(lines), imports or [], language)


def _compile_errors(code: str, language: str | None = None) -> list[dict] | None:
    return runner.check_compiles(code, language)


def _syntax_errors(code: str, language: str) -> list:
    return lang.get(language).parse(code)["errors"]


async def validate(original: str, patched: str, *, fix_line: int | None = None,
                   language: str | None = None) -> tuple[bool, list[str], list[str]]:
    """(valid, problems, warnings): a patch must not add compile errors; in fix mode it must also remove the target one.

    Ordinary mode: ``len(E(patched)) <= len(E(original))`` and a compiling original stays compiling.
    Fix mode (*fix_line* set): strictly fewer errors and no error left on *fix_line* with its original text.
    Without a local javac only syntax is checked. Python is checked by its parser + ``compile()`` instead of javac.
    """
    language = "python" if runner.is_python_code(original, language) else "java"
    syntax_before = _syntax_errors(original, language)
    syntax_after = _syntax_errors(patched, language)
    if syntax_after and not syntax_before:
        return False, [f"Синтаксическая ошибка: {syntax_after[0]}"], []
    before, after = await asyncio.gather(
        asyncio.to_thread(_compile_errors, original, language), asyncio.to_thread(_compile_errors, patched, language)
    )
    if before is None or after is None:    # no local javac (docker mode): syntax check only
        if syntax_after:
            return False, [f"Синтаксическая ошибка: {syntax_after[0]}"], []
        return True, [], [] if fix_line is not None else ["Компиляция не проверялась (только синтаксис)"]
    if fix_line is not None:
        target = {e["message"] for e in before if e["line"] == fix_line}
        if any(e["line"] == fix_line and e["message"] in target for e in after):
            return False, [f"Правка не устраняет ошибку в строке {fix_line}"], []
        if len(after) >= len(before):
            return False, ["Правка не уменьшает число ошибок компиляции"], []
        return True, [], []
    if not before:
        return (True, [], []) if not after else (False, [_explain(e) for e in after[:3]], [])
    if len(after) <= len(before):
        warn = ["В исходном коде уже были ошибки компиляции — патч их не добавляет"] if after else []
        return True, [], warn
    return False, [_explain(e) for e in after[:3]], []


_KIND = {"method": "метод", "variable": "переменная", "class": "класс"}


def _explain(e: dict) -> str:
    """Compile error in words: a missing symbol is the usual case — the patch calls a helper it didn't add."""
    m = re.match(r"cannot find symbol \(symbol:\s*(\w+)\s+([\w$]+)", e.get("message", ""))
    if m:
        kind, name = _KIND.get(m[1], m[1]), m[2]
        return (f"Не компилируется (стр. {e['line']}): правка использует {kind} «{name}», "
                f"которого нет в коде — ИИ не добавил его определение")
    return f"Не компилируется (стр. {e['line']}): {e.get('message', '')}"


async def build_patch(code: str, old: str, new: str, imports: list[str] | None,
                      hint_line: int | None = None, *, fix_line: int | None = None) -> dict | None:
    """Full patch description for the UI, or None when the fragment can't be located unambiguously."""
    code = normalize(code)
    if not (old or "").strip() or not (new or "").strip():
        return None
    span = locate(code, old, hint_line)
    if not span:
        return None
    start, end = span
    old_text = "\n".join(code.split("\n")[start - 1:end])
    patched, added = replace_range(code, start, end, new, imports)
    if patched == code:
        return None
    lines = code.split("\n")
    base = lines[start - 1][: len(lines[start - 1]) - len(lines[start - 1].lstrip())]
    valid, problems, warnings = await validate(code, patched, fix_line=fix_line)
    before, after = bigo_diff.bigo_change(code, patched, start, end) if valid else ({}, {})
    return {
        "bigo_before": before, "bigo_after": after,
        "old_code": old_text, "new_code": reindent(new, base), "imports": added,
        "start_line": start, "end_line": end,
        "valid": valid, "problems": problems, "warnings": warnings,
    }


async def apply_patch(code: str, old: str, new: str, imports: list[str] | None,
                      hint_line: int | None, *, fix_line: int | None = None,
                      language: str | None = None) -> dict:
    """Apply to the *current* code (which may have changed since the suggestion was made)."""
    code = normalize(code)
    span = locate(code, old, hint_line)
    if not span:
        return {"ok": False, "code": code, "problems": ["Код изменился: исходный фрагмент не найден или встречается "
                                                        "несколько раз. Дождитесь нового ревью."],
                "warnings": [], "start_line": 0, "end_line": 0}
    patched, _ = replace_range(code, span[0], span[1], new, imports, language)
    valid, problems, warnings = await validate(code, patched, fix_line=fix_line, language=language)
    if not valid:
        return {"ok": False, "code": code, "problems": problems, "warnings": warnings,
                "start_line": 0, "end_line": 0}
    return {"ok": True, "code": patched, "problems": [], "warnings": warnings,
            "start_line": span[0], "end_line": span[1]}

"""Language registry: thin adapters over the per-language parser / checker / generator / decomposer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


def _java_parse(code: str) -> dict:
    from core.parser import parse_java
    return parse_java(code)


def _py_parse(code: str) -> dict:
    from core.py_parser import parse_python
    return parse_python(code)


def _check(language: str) -> Callable[[str], list[dict]]:
    def check(code: str) -> list[dict]:
        from core import runner
        return runner.check_compiles(code, language) or []
    return check


def _java_regenerate(code: str, method: dict, edits: dict[str, str]) -> tuple[str, list[str]]:
    from core.code_generator import regenerate_method, splice_edits, splice_method
    spliced = splice_edits(code, method, edits)
    if spliced is not None:
        return spliced
    body, changed = regenerate_method(method, edits)
    return splice_method(code, method, body), changed


def _py_regenerate(code: str, method: dict, edits: dict[str, str]) -> tuple[str, list[str]]:
    from core.py_codegen import apply_edits
    return apply_edits(code, method, edits)


def _decompose(code: str, ast: dict):
    from core.decomposer import decompose
    return decompose(code, ast)


@dataclass(frozen=True)
class Language:
    name: str
    title: str                     # human-readable, for messages
    extensions: tuple[str, ...]
    entry_file: str
    parse: Callable[[str], dict]
    check: Callable[[str], list[dict]]
    regenerate: Callable[[str, dict, dict[str, str]], tuple[str, list[str]]]
    decompose: Callable[[str, dict], object]


JAVA = Language("java", "Java", (".java",), "Main.java", _java_parse, _check("java"), _java_regenerate, _decompose)
PYTHON = Language("python", "Python", (".py",), "main.py", _py_parse, _check("python"), _py_regenerate,
                  _decompose)

LANGS: dict[str, Language] = {"java": JAVA, "python": PYTHON}


def get(name: str | None) -> Language:
    """Unknown / missing language falls back to Java."""
    return LANGS.get((name or "").lower(), JAVA)


def by_filename(name: str) -> Language:
    low = (name or "").lower()
    for lang in LANGS.values():
        if low.endswith(lang.extensions):
            return lang
    return JAVA

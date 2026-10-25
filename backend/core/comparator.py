"""Compare program outputs of two runs."""

from __future__ import annotations

import difflib
import re

from core.runner import run_code, run_java
from models.schemas import CompareResponse, RunResponse


_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def normalize(text: str) -> str:
    """Mask volatile parts (timestamps, ANSI) and normalize line endings/whitespace."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ANSI_RE.sub("", text)
    text = _TS_RE.sub("<TIMESTAMP>", text)
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def unified_diff(before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="before", tofile="after",
    ))


def _toolchain_missing(*runs: RunResponse) -> bool:
    """Neither version ran at all (no toolchain): identical failures say nothing about behaviour."""
    return any("toolchain not found" in r.stderr for r in runs)


def compare_runs(before: RunResponse, after: RunResponse) -> CompareResponse:
    nb, na = normalize(before.stdout), normalize(after.stdout)
    diff = unified_diff(nb, na)
    preserved = (
        nb == na
        and before.exit_code == after.exit_code
        and not after.compile_errors
        and not _toolchain_missing(before, after)
    )
    return CompareResponse(before=before, after=after, diff=diff, behavior_preserved=preserved)


def compare_code(original: str, modified: str, main_class: str | None = None, stdin_input: str = "", language: str | None = None) -> CompareResponse:
    return compare_runs(
        run_code(original, main_class, stdin_input, language=language),
        run_code(modified, main_class, stdin_input, language=language),
    )

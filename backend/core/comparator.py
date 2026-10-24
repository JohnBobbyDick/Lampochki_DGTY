"""Compare program outputs of two runs."""

from __future__ import annotations

import difflib
import re

from core.runner import run_java
from models.schemas import CompareResponse, RunResponse


_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?")


def normalize(text: str) -> str:
    """Mask volatile parts (timestamps) so that equal behaviour compares equal."""
    return _TS_RE.sub("<TIMESTAMP>", text)


def unified_diff(before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="before", tofile="after",
    ))


def _toolchain_missing(*runs: RunResponse) -> bool:
    """Neither version ran at all (no JDK): identical failures say nothing about behaviour."""
    return any("Java toolchain not found" in r.stderr for r in runs)


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


def compare_code(original: str, modified: str, main_class: str | None = None, stdin_input: str = "") -> CompareResponse:
    return compare_runs(
        run_java(original, main_class, stdin_input),
        run_java(modified, main_class, stdin_input),
    )

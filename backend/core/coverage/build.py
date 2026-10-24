"""Local compile of an instrumented program, with graceful fallback to the original code.

Order (controller decision): compile the instrumented code; on failure compile the original — if that
fails too, it is the user's error; otherwise retry twice (round 1 strips branch/cond/rel probes on the
javac error lines, round 2 strips every probe on them) and finally run the original without coverage.
Whatever happens, a runnable program ends up in ``tmp/"out"`` unless the user's code does not compile.
"""

from __future__ import annotations

import os
import shutil
import stat
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from core.coverage import instrument
from core.coverage.instrument import COV_CLASS, CoverageUnavailable, Probe
from core.runner import parse_compile_errors

UNAVAILABLE = "Покрытие недоступно: инструментированный код не скомпилировался"
USER_ERROR = "Программа не скомпилировалась"


@dataclass
class CovPlan:
    probes: list[Probe] = field(default_factory=list)
    slots: int = 0
    data_file: Path | None = None
    error: str | None = None


def _javac(tmp: Path, names: list[str]) -> subprocess.CompletedProcess:
    out = tmp / "out"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    return subprocess.run(
        ["javac", "-encoding", "UTF-8", "-d", "out", *names],
        cwd=tmp, capture_output=True, text=True, timeout=60,
    )


def _error_lines(stderr: str, fname: str) -> set[int]:
    return {e["line"] for e in parse_compile_errors(stderr) if Path(e["file"]).name == fname}


def _compile_instrumented(tmp: Path, fname: str, inst: instrument.Instrumented) -> subprocess.CompletedProcess:
    (tmp / fname).write_text(inst.code, encoding="utf-8")
    (tmp / f"{COV_CLASS}.java").write_text(inst.cov_source, encoding="utf-8")
    return _javac(tmp, [fname, f"{COV_CLASS}.java"])


def _compile_original(tmp: Path, fname: str, code: str) -> subprocess.CompletedProcess:
    (tmp / f"{COV_CLASS}.java").unlink(missing_ok=True)
    (tmp / fname).write_text(code, encoding="utf-8")
    return _javac(tmp, [fname])


def _without_coverage(tmp: Path, fname: str, code: str, error: str):
    proc = _compile_original(tmp, fname, code)
    if proc.returncode != 0:
        return proc, CovPlan(error=USER_ERROR)
    return None, CovPlan(error=error)


def _success(tmp: Path, inst: instrument.Instrumented):
    cov_dir = tmp / "cov"
    cov_dir.mkdir(exist_ok=True)
    os.chmod(cov_dir, 0o755)              # not world-writable: the sandbox must not swap cov.bin
    data = cov_dir / "cov.bin"
    data.write_bytes(bytes(inst.slots * 4))
    os.chmod(data, 0o666)                 # the docker runner maps it read-write as another user
    return None, CovPlan(inst.probes, inst.slots, data, None)


def compile_local(tmp: Path, fname: str, code: str) -> tuple[subprocess.CompletedProcess | None, CovPlan]:
    """Compile *code* (saved as ``tmp/fname``) into ``tmp/"out"``.

    Returns ``(None, plan)`` when something runnable was compiled (``plan.error`` says why there is no
    coverage, if so) or ``(proc, plan)`` with the failed javac run of the user's original code.
    """
    try:
        inst = instrument.instrument_java(code)
    except CoverageUnavailable as exc:
        return _without_coverage(tmp, fname, code, str(exc))
    proc = _compile_instrumented(tmp, fname, inst)
    if proc.returncode == 0:
        return _success(tmp, inst)

    orig = _compile_original(tmp, fname, code)
    if orig.returncode != 0:
        return orig, CovPlan(error=USER_ERROR)

    bad = _error_lines(proc.stderr, fname)
    for level in (1, 2):
        if not bad:
            break
        try:
            inst = instrument.instrument_java(code, strip={line: level for line in bad})
        except CoverageUnavailable:
            break
        proc = _compile_instrumented(tmp, fname, inst)
        if proc.returncode == 0:
            return _success(tmp, inst)
        bad |= _error_lines(proc.stderr, fname)
    return _without_coverage(tmp, fname, code, UNAVAILABLE)


def read_hits(plan: CovPlan) -> list[int] | None:
    """Counters written by the program; None if the data file is missing or has the wrong size."""
    if plan.data_file is None:
        return None
    size = plan.slots * 4
    try:
        # never follow a symlink planted by the program: it could point at any host file
        fd = os.open(plan.data_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size != size:
            return None
        raw = b""
        while len(raw) < size:
            chunk = os.read(fd, size - len(raw))
            if not chunk:
                return None
            raw += chunk
    except OSError:
        return None
    finally:
        os.close(fd)
    return list(struct.unpack(f"<{plan.slots}i", raw))

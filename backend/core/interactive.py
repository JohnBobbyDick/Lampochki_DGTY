"""Interactive execution: stream a Java process' stdout/stderr, feed stdin live."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Awaitable, Callable

from core import runner
from core.coverage import build, instrument
from core.coverage.build import CovPlan

Emit = Callable[[dict], Awaitable[None]]
MAX_SESSION_SEC = 300
MAX_OUT_BYTES = 1_000_000


def _prepare_docker(tmp: Path, fname: str, code: str) -> tuple[bool, CovPlan]:
    """Lay the files out for the container: original in orig/, instrumented code + __Cov in cov/."""
    try:
        inst = instrument.instrument_java(code)
    except instrument.CoverageUnavailable as exc:
        (tmp / fname).write_text(code, encoding="utf-8")
        return False, CovPlan(error=str(exc))
    (tmp / "orig").mkdir()
    (tmp / "orig" / fname).write_text(code, encoding="utf-8")
    _, plan = build._success(tmp, inst)
    cov_dir = tmp / "cov"
    (cov_dir / fname).write_text(inst.code, encoding="utf-8")
    (cov_dir / f"{instrument.COV_CLASS}.java").write_text(inst.cov_source, encoding="utf-8")
    os.chmod(cov_dir, 0o777)   # the container user (65534) must be able to leave the "compiled" marker
    return True, plan


def coverage_message(plan: CovPlan, marker: Path | None = None) -> dict:
    """The ``coverage`` WS message.  *marker* (docker mode): file the container creates once the instrumented code compiled."""
    if marker is not None and plan.error is None and not marker.exists():
        plan.error = build.UNAVAILABLE
    if plan.error:
        return {"type": "coverage", "error": plan.error}
    hits = build.read_hits(plan)
    if hits is None:
        return {"type": "coverage", "error": "Данные покрытия не получены"}
    return {"type": "coverage", "probes": [p.to_json() for p in plan.probes], "hits": hits}


def final_coverage(exit_code: int, plan: CovPlan, tmp: Path) -> dict | None:
    """The coverage message to send before ``exit``; None after a docker compile error (exit 98)."""
    docker = runner.SANDBOX_MODE == "docker"
    if docker and exit_code == runner.DOCKER_COMPILE_EXIT:
        return None
    marker = tmp / "cov" / "compiled" if docker and plan.data_file else None
    return coverage_message(plan, marker)


async def start_session(
    code: str, main_class: str | None, emit: Emit,
) -> tuple[asyncio.subprocess.Process, Path, CovPlan] | None:
    """Compile *code* and launch it.  Returns (process, tmpdir, coverage plan) or None on compile error."""
    main_class = main_class or runner.detect_main_class(code) or runner._public_class(code) or "Main"
    fname = f"{runner._public_class(code) or main_class}.java"
    files = {fname: code}
    try:
        runner._validate(files, main_class)
    except ValueError as exc:
        await emit({"type": "stderr", "data": str(exc) + "\n"})
        await emit({"type": "exit", "code": 2, "durationMs": 0})
        return None

    tmp = Path(tempfile.mkdtemp(prefix="jb_ws_"))

    if runner.SANDBOX_MODE == "docker":
        cov, plan = await asyncio.to_thread(_prepare_docker, tmp, fname, code)
        cmd = runner.docker_command(tmp, [fname], main_class, cov=cov, slots=plan.slots)
        cwd = None
    else:
        proc, plan = await asyncio.to_thread(build.compile_local, tmp, fname, code)
        if proc is not None:
            shutil.rmtree(tmp, ignore_errors=True)
            await emit({"type": "compile_error", "text": proc.stderr,
                        "errors": runner.parse_compile_errors(proc.stderr)})
            await emit({"type": "exit", "code": proc.returncode, "durationMs": 0})
            return None
        cmd = ["java", "-Xmx256m", "-Dfile.encoding=UTF-8"]
        if plan.data_file is not None:
            cmd.append(f"-Djb.cov={plan.data_file}")
        cmd += ["-cp", "out", main_class]
        cwd = tmp

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        await emit({"type": "stderr", "data": f"Java toolchain not found: {exc}\n"})
        await emit({"type": "exit", "code": 127, "durationMs": 0})
        return None
    return proc, tmp, plan


async def pump(proc: asyncio.subprocess.Process, emit: Emit) -> int:
    """Forward output until the process exits (or limits are hit); returns exit code."""
    sent = 0

    async def forward(stream: asyncio.StreamReader, kind: str) -> None:
        nonlocal sent
        while chunk := await stream.read(1024):
            sent += len(chunk)
            if sent > MAX_OUT_BYTES:
                await emit({"type": kind, "data": "\n…[output limit reached, process killed]\n"})
                proc.kill()
                return
            await emit({"type": kind, "data": chunk.decode("utf-8", "replace")})

    tasks = [asyncio.create_task(forward(proc.stdout, "stdout")),
             asyncio.create_task(forward(proc.stderr, "stderr"))]
    try:
        await asyncio.wait_for(proc.wait(), MAX_SESSION_SEC)
    except asyncio.TimeoutError:
        proc.kill()
        await emit({"type": "stderr", "data": f"\nTimeout: сессия дольше {MAX_SESSION_SEC} с\n"})
    await asyncio.gather(*tasks, return_exceptions=True)
    return proc.returncode if proc.returncode is not None else -1


async def feed(proc: asyncio.subprocess.Process, data: str) -> None:
    if proc.stdin is None or proc.stdin.is_closing():
        return
    try:
        proc.stdin.write(data.encode("utf-8"))
        await proc.stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass


def cleanup(tmp: Path | None) -> None:
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)

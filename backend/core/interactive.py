"""Interactive execution: stream a Java process' stdout/stderr, feed stdin live."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Awaitable, Callable

from core import runner

Emit = Callable[[dict], Awaitable[None]]
MAX_SESSION_SEC = 300
MAX_OUT_BYTES = 1_000_000


async def start_session(code: str, main_class: str | None, emit: Emit) -> tuple[asyncio.subprocess.Process, Path] | None:
    """Compile *code* and launch it.  Returns (process, tmpdir) or None on compile error."""
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
    (tmp / fname).write_text(code, encoding="utf-8")

    if runner.SANDBOX_MODE == "docker":
        cmd = runner.docker_command(tmp, [fname], main_class)
        cwd = None
    else:
        comp = await asyncio.to_thread(
            subprocess.run, ["javac", "-encoding", "UTF-8", "-d", ".", fname],
            cwd=tmp, capture_output=True, text=True, timeout=60,
        )
        if comp.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            await emit({"type": "compile_error", "text": comp.stderr,
                        "errors": runner.parse_compile_errors(comp.stderr)})
            await emit({"type": "exit", "code": comp.returncode, "durationMs": 0})
            return None
        cmd = ["java", "-Xmx256m", "-Dfile.encoding=UTF-8", "-cp", ".", main_class]
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
    return proc, tmp


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

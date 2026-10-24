"""Interactive execution: stream a Java or Python process' stdout/stderr, feed stdin live."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Awaitable, Callable

from core import runner

Emit = Callable[[dict], Awaitable[None]]
MAX_SESSION_SEC = 300
MAX_OUT_BYTES = 1_000_000


class InteractiveProcess:
    """Wrapper around subprocess.Popen providing an async-friendly interface
    that works consistently across all event loops (including Windows SelectorEventLoop)."""

    def __init__(self, popen: subprocess.Popen, tmp: Path):
        self.popen = popen
        self.tmp = tmp
        self.stdin = popen.stdin

    @property
    def returncode(self) -> int | None:
        return self.popen.poll()

    def kill(self) -> None:
        try:
            self.popen.kill()
        except OSError:
            pass


async def start_session(
    code: str, main_class: str | None, emit: Emit, language: str | None = None
) -> tuple[InteractiveProcess, Path] | None:
    """Compile/check *code* and launch it. Returns (process, tmpdir) or None on compile error."""
    if runner.is_python_code(code, language):
        tmp = Path(tempfile.mkdtemp(prefix="jb_ws_py_"))
        (tmp / "main.py").write_text(code, encoding="utf-8")
        try:
            compile(code, "main.py", "exec")
        except SyntaxError as exc:
            shutil.rmtree(tmp, ignore_errors=True)
            await emit({
                "type": "compile_error",
                "text": f"SyntaxError: {exc.msg} (line {exc.lineno})\n",
                "errors": [{"file": "main.py", "line": exc.lineno or 1, "message": exc.msg or "SyntaxError"}],
            })
            await emit({"type": "exit", "code": 1, "durationMs": 0})
            return None

        cmd = [sys.executable, "-u", "main.py"]
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
        }
        try:
            popen = subprocess.Popen(
                cmd,
                cwd=tmp,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env=env,
            )
            return InteractiveProcess(popen, tmp), tmp
        except Exception as exc:
            shutil.rmtree(tmp, ignore_errors=True)
            err_msg = str(exc) or repr(exc)
            await emit({"type": "stderr", "data": f"Python launch failed: {err_msg}\n"})
            await emit({"type": "exit", "code": 127, "durationMs": 0})
            return None

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
        javac_cmd = runner.get_javac_cmd()
        try:
            comp = await asyncio.to_thread(
                subprocess.run,
                [javac_cmd, "-encoding", "UTF-8", "-d", ".", fname],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError as exc:
            shutil.rmtree(tmp, ignore_errors=True)
            await emit({"type": "stderr", "data": f"Java toolchain (javac) not found: {exc}\n"})
            await emit({"type": "exit", "code": 127, "durationMs": 0})
            return None
        except subprocess.TimeoutExpired:
            shutil.rmtree(tmp, ignore_errors=True)
            await emit({"type": "stderr", "data": "Compilation timed out after 60s\n"})
            await emit({"type": "exit", "code": 124, "durationMs": 0})
            return None

        if comp.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            await emit({
                "type": "compile_error",
                "text": comp.stderr,
                "errors": runner.parse_compile_errors(comp.stderr),
            })
            await emit({"type": "exit", "code": comp.returncode, "durationMs": 0})
            return None

        cmd = [runner.get_java_cmd(), "-Xmx256m", "-Dfile.encoding=UTF-8", "-cp", ".", main_class]
        cwd = tmp

    try:
        popen = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        return InteractiveProcess(popen, tmp), tmp
    except FileNotFoundError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        await emit({"type": "stderr", "data": f"Java toolchain not found: {exc}\n"})
        await emit({"type": "exit", "code": 127, "durationMs": 0})
        return None
    except Exception as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        err_msg = str(exc) or repr(exc)
        await emit({"type": "stderr", "data": f"Java launch failed: {err_msg}\n"})
        await emit({"type": "exit", "code": 127, "durationMs": 0})
        return None


async def pump(proc: InteractiveProcess, emit: Emit) -> int:
    """Forward output until the process exits (or limits are hit); returns exit code."""
    loop = asyncio.get_running_loop()
    q: asyncio.Queue[tuple[str, bytes | None]] = asyncio.Queue()
    sent = 0

    def stream_reader(pipe, kind: str):
        try:
            while True:
                chunk = pipe.read(1024)
                if not chunk:
                    break
                loop.call_soon_threadsafe(q.put_nowait, (kind, chunk))
        except Exception:
            pass
        finally:
            loop.call_soon_threadsafe(q.put_nowait, (kind, None))

    t_out = threading.Thread(target=stream_reader, args=(proc.popen.stdout, "stdout"), daemon=True)
    t_err = threading.Thread(target=stream_reader, args=(proc.popen.stderr, "stderr"), daemon=True)
    t_out.start()
    t_err.start()

    active_streams = 2
    started = time.monotonic()

    while active_streams > 0:
        elapsed = time.monotonic() - started
        remaining = max(0.1, MAX_SESSION_SEC - elapsed)
        try:
            kind, chunk = await asyncio.wait_for(q.get(), timeout=remaining)
        except asyncio.TimeoutError:
            proc.kill()
            await emit({"type": "stderr", "data": f"\nTimeout: сессия дольше {MAX_SESSION_SEC} с\n"})
            break

        if chunk is None:
            active_streams -= 1
            continue

        sent += len(chunk)
        if sent > MAX_OUT_BYTES:
            await emit({"type": kind, "data": "\n…[output limit reached, process killed]\n"})
            proc.kill()
            break

        await emit({"type": kind, "data": chunk.decode("utf-8", "replace")})

    try:
        await asyncio.wait_for(asyncio.to_thread(proc.popen.wait), timeout=5.0)
    except (asyncio.TimeoutError, Exception):
        proc.kill()

    return proc.popen.returncode if proc.popen.returncode is not None else -1


async def feed(proc: InteractiveProcess, data: str) -> None:
    if proc.stdin and not proc.stdin.closed:
        try:
            proc.stdin.write(data.encode("utf-8"))
            proc.stdin.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


def cleanup(tmp: Path | None) -> None:
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)

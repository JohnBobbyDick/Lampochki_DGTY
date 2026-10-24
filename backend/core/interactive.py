"""Interactive execution: stream a Java or Python process' stdout/stderr, feed stdin live."""

from __future__ import annotations

import asyncio
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Awaitable, Callable

from core import runner
from core.coverage import build, instrument
from core.coverage.build import CovPlan

Emit = Callable[[dict], Awaitable[None]]
MAX_SESSION_SEC = 300
MAX_OUT_BYTES = 1_000_000
STDIN_LIMIT = 1_048_576   # total stdin bytes per run
STDIN_LIMIT_MSG = "Слишком много ввода: лимит 1 МБ на запуск\n"


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


class InteractiveProcess:
    """Wrapper around subprocess.Popen providing an async-friendly interface
    that works consistently across all event loops (including Windows SelectorEventLoop)."""

    def __init__(self, popen: subprocess.Popen, tmp: Path):
        self.popen = popen
        self.tmp = tmp
        self.stdin = popen.stdin
        self._q: queue.Queue[bytes | None] = queue.Queue()
        self._writer: threading.Thread | None = None
        self._queued = 0
        self._over = False

    def _write_loop(self) -> None:
        """Writer thread: blocking pipe writes happen here, never on the event loop."""
        try:
            while True:
                item = self._q.get()
                if item is None:
                    break
                self.stdin.write(item)
                self.stdin.flush()
        except (OSError, ValueError):
            pass   # process died / pipe closed
        finally:
            try:
                self.stdin.close()
            except (OSError, ValueError):
                pass

    def _ensure_writer(self) -> None:
        if self._writer is None and self.stdin:
            self._writer = threading.Thread(target=self._write_loop, daemon=True)
            self._writer.start()

    def send(self, data: str) -> bool:
        """Queue *data* for stdin.  False once the per-run cap is exceeded (this and later input is dropped)."""
        if not self.stdin or self._over:
            return not self._over
        raw = data.encode("utf-8")
        if self._queued + len(raw) > STDIN_LIMIT:
            self._over = True
            return False
        self._queued += len(raw)
        self._ensure_writer()
        self._q.put(raw)
        return True

    def close_stdin(self) -> None:
        """Close stdin after everything already queued has been written."""
        if self._writer is not None:
            self._q.put(None)
        elif self.stdin:
            try:
                self.stdin.close()
            except (OSError, ValueError):
                pass

    @property
    def returncode(self) -> int | None:
        return self.popen.poll()

    def kill(self) -> None:
        try:
            self.popen.kill()
        except OSError:
            pass
        if self._writer is not None:
            self._q.put(None)   # unblock the writer if it is idle


PY_COVERAGE_UNSUPPORTED = "Покрытие для Python пока не поддерживается"


async def start_session(
    code: str, main_class: str | None, emit: Emit, language: str | None = None,
) -> tuple[InteractiveProcess, Path, CovPlan] | None:
    """Compile/check *code* and launch it.  Returns (process, tmpdir, coverage plan) or None on compile error.

    Coverage is Java-only: a Python run gets a plan whose ``error`` says so.
    """
    if runner.is_python_code(code, language):
        return await _start_python(code, emit)
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
        cmd = [runner.get_java_cmd(), "-Xmx256m", "-Dfile.encoding=UTF-8"]
        if plan.data_file is not None:
            cmd.append(f"-Djb.cov={plan.data_file}")
        cmd += ["-cp", "out", main_class]
        cwd = tmp

    try:
        popen = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            env=None if runner.SANDBOX_MODE == "docker" else runner.child_env(),
        )
        return InteractiveProcess(popen, tmp), tmp, plan
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


async def _start_python(code: str, emit: Emit) -> tuple[InteractiveProcess, Path, CovPlan] | None:
    try:
        compile(code, "main.py", "exec")
    except SyntaxError as exc:
        await emit({
            "type": "compile_error",
            "text": f"SyntaxError: {exc.msg} (line {exc.lineno})\n",
            "errors": [{"file": "main.py", "line": exc.lineno or 1, "message": exc.msg or "SyntaxError"}],
        })
        await emit({"type": "exit", "code": 1, "durationMs": 0})
        return None
    tmp = Path(tempfile.mkdtemp(prefix="jb_ws_py_"))
    (tmp / "main.py").write_text(code, encoding="utf-8")
    docker = runner.SANDBOX_MODE == "docker"
    if docker:
        os.chmod(tmp, 0o755)
    cmd, env = runner.python_command(tmp, "main.py")
    try:
        popen = subprocess.Popen(
            cmd, cwd=None if docker else tmp, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0, env=env, preexec_fn=None if docker else runner.python_preexec(),
        )
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmp, ignore_errors=True)
        await emit({"type": "stderr", "data": f"Python launch failed: {str(exc) or repr(exc)}\n"})
        await emit({"type": "exit", "code": 127, "durationMs": 0})
        return None
    return InteractiveProcess(popen, tmp), tmp, CovPlan(error=PY_COVERAGE_UNSUPPORTED)


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


async def feed(proc: InteractiveProcess, data: str) -> bool:
    """Queue stdin data (non-blocking).  False when the per-run cap was exceeded."""
    return proc.send(data)


def close_stdin(proc: InteractiveProcess) -> None:
    proc.close_stdin()


def cleanup(tmp: Path | None) -> None:
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)

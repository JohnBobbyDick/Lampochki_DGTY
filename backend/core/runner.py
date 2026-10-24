"""Compile and run Java sources in an isolated temp directory.

Modes (env ``JAVA_SANDBOX_MODE``):
  * ``subprocess`` (default, DEV ONLY) – local ``javac``/``java`` with a timeout and -Xmx256m.
    NOT a sandbox: submitted code runs with the server's privileges. Use ``docker`` for any
    deployment reachable by untrusted users.
  * ``docker`` – ``docker run`` on the sandbox image with no network, 256 MB RAM
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from models.schemas import RunResponse

SANDBOX_MODE = os.getenv("JAVA_SANDBOX_MODE", "subprocess")
SANDBOX_IMAGE = os.getenv("JAVA_SANDBOX_IMAGE", "lampochki-sandbox")
_ERR_RE = re.compile(r"^(?P<file>[\w./-]+\.java):(?P<line>\d+):\s*(?:error:\s*)?(?P<msg>.*)$")
_MAX_OUT = 200_000
DOCKER_COMPILE_EXIT = 98   # exit code of the docker script when the user's code does not compile
_IDENT = re.compile(r"[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*")
_FILENAME = re.compile(r"[A-Za-z_$][\w$]*\.java")


def _validate(files: dict[str, str], main_class: str) -> None:
    """Reject names that could escape the temp dir or inject CLI/shell text."""
    if not _IDENT.fullmatch(main_class or ""):
        raise ValueError(f"Недопустимое имя главного класса: {main_class!r}")
    for name in files:
        if not _FILENAME.fullmatch(name):
            raise ValueError(f"Недопустимое имя файла: {name!r}")


def detect_main_class(code: str) -> str | None:
    """Name of the first class that declares ``public static void main``."""
    from core.parser import parse_java

    ast = parse_java(code)["ast"]
    for cls in ast["classes"]:
        for m in cls["methods"]:
            if m["name"] == "main" and "static" in m["modifiers"]:
                return cls["name"]
    return None


def _public_class(code: str) -> str | None:
    m = re.search(r"\bpublic\s+(?:final\s+|abstract\s+)?(?:class|interface|enum)\s+(\w+)", code)
    return m.group(1) if m else None


def parse_compile_errors(text: str) -> list[dict]:
    errors = []
    for line in text.splitlines():
        m = _ERR_RE.match(line.strip())
        if m:
            errors.append({"file": m["file"], "line": int(m["line"]), "message": m["msg"]})
        elif errors and line.strip().startswith("symbol:"):
            # javac names the missing symbol on a separate line: "  symbol:   method swap(int[],int,int)"
            errors[-1]["message"] += " (" + " ".join(line.split()) + ")"
    return errors


def check_compiles(code: str) -> list[dict] | None:
    """javac-only check (nothing is executed). None when no local javac is used (docker mode)."""
    if SANDBOX_MODE == "docker":
        return None
    fname = f"{_public_class(code) or 'Snippet'}.java"
    tmp = Path(tempfile.mkdtemp(prefix="jb_chk_"))
    try:
        (tmp / fname).write_text(code, encoding="utf-8")
        proc = subprocess.run(
            ["javac", "-proc:none", "-XDshould-stop.ifError=FLOW", "-encoding", "UTF-8", "-d", str(tmp / "out"), fname],
            cwd=tmp, capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if proc.returncode == 0:
        return []
    return parse_compile_errors(proc.stderr) or [{"file": fname, "line": 0, "message": proc.stderr.strip()[:200]}]


def run_files(files: dict[str, str], main_class: str, stdin_input: str = "", timeout_sec: int = 10) -> RunResponse:
    """Compile every file in *files* (name -> source) and run *main_class*."""
    try:
        _validate(files, main_class)
    except ValueError as exc:
        return RunResponse(stderr=str(exc), exit_code=2)
    tmp = Path(tempfile.mkdtemp(prefix="jb_run_"))
    try:
        for name, src in files.items():
            (tmp / name).write_text(src, encoding="utf-8")
        names = list(files)
        started = time.monotonic()
        try:
            if SANDBOX_MODE == "docker":
                return _run_docker(tmp, names, main_class, stdin_input, timeout_sec, started)
            return _run_local(tmp, names, main_class, stdin_input, timeout_sec, started)
        except FileNotFoundError as exc:
            return RunResponse(stderr=f"Java toolchain not found: {exc}", exit_code=127)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_java(code: str, main_class: str | None = None, stdin_input: str = "", timeout_sec: int = 10) -> RunResponse:
    """Compile and run a single-file program."""
    main_class = main_class or detect_main_class(code) or _public_class(code) or "Main"
    fname = f"{_public_class(code) or main_class}.java"
    return run_files({fname: code}, main_class, stdin_input, timeout_sec)


def _trim(s: str) -> str:
    return s if len(s) <= _MAX_OUT else s[:_MAX_OUT] + "\n…[output truncated]"


def _run_local(tmp: Path, names: list[str], main_class: str, stdin_input: str, timeout: int, started: float) -> RunResponse:
    try:
        comp = subprocess.run(
            ["javac", "-encoding", "UTF-8", "-d", ".", *names],
            cwd=tmp, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return RunResponse(stderr="Compilation timed out", exit_code=124)
    if comp.returncode != 0:
        return RunResponse(
            stderr=_trim(comp.stderr), exit_code=comp.returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
            compile_errors=parse_compile_errors(comp.stderr),
        )
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["java", "-Xmx256m", "-Dfile.encoding=UTF-8", "-cp", ".", main_class],
            cwd=tmp, input=stdin_input, capture_output=True, text=True, timeout=timeout,
        )
        return RunResponse(
            stdout=_trim(proc.stdout), stderr=_trim(proc.stderr), exit_code=proc.returncode,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return RunResponse(
            stdout=_trim(out), stderr=f"Timeout: выполнение превысило {timeout} с",
            exit_code=124, duration_ms=timeout * 1000,
        )


def docker_command(tmp: Path, names: list[str], main_class: str, cov: bool = False, slots: int = 0) -> list[str]:
    if cov:
        # the container can write into the host-mounted /cov: cap file size to the counter file (512-byte blocks)
        fsize = -(-slots * 4 // 512) + 8
        # cov/ holds the instrumented code + __Cov and is the (rw) data dir; the original is in orig/
        script = (
            "javac -encoding UTF-8 -d /tmp/out cov/*.java 2> /dev/null && touch /cov/compiled || "
            f"{{ rm -rf /tmp/out/*; javac -encoding UTF-8 -d /tmp/out {' '.join('orig/' + n for n in names)} 2> /tmp/javac.err || "
            "{ cat /tmp/javac.err >&2; exit 98; }; }; "
            f"ulimit -f {fsize}; java -Xmx256m -Djb.cov=/cov/cov.bin -cp /tmp/out {main_class}"
        )
    else:
        script = (
            f"javac -encoding UTF-8 -d /tmp/out {' '.join(names)} 2> /tmp/javac.err || "
            f"{{ cat /tmp/javac.err >&2; exit 98; }}; "
            f"java -Xmx256m -cp /tmp/out {main_class}"
        )
    cmd = [
        "docker", "run", "--rm", "-i", "--network", "none", "-m", "256m", "--cpus", "1",
        "--pids-limit", "128", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--user", "65534", "-v", f"{tmp}:/workspace:ro", "-w", "/workspace",
    ]
    if cov:
        cmd += ["-v", f"{tmp / 'cov'}:/cov:rw"]
    cmd += ["--tmpfs", "/tmp:rw,exec", SANDBOX_IMAGE, "sh", "-c", script]
    return cmd


def _run_docker(tmp: Path, names: list[str], main_class: str, stdin_input: str, timeout: int, started: float) -> RunResponse:
    cmd = docker_command(tmp, names, main_class)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, input=stdin_input, capture_output=True, text=True, timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        return RunResponse(stderr=f"Timeout: выполнение превысило {timeout} с", exit_code=124,
                           duration_ms=timeout * 1000)
    resp = RunResponse(
        stdout=_trim(proc.stdout), stderr=_trim(proc.stderr), exit_code=proc.returncode,
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
    if proc.returncode == 98:
        resp.compile_errors = parse_compile_errors(proc.stderr)
    return resp

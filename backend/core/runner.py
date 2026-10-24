"""Compile and run Java and Python sources in an isolated temp directory.

Modes (env ``JAVA_SANDBOX_MODE``):
  * ``subprocess`` (default, DEV ONLY) – local execution with a timeout and memory limits.
  * ``docker`` – ``docker run`` on the sandbox image with no network, 256 MB RAM
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from models.schemas import RunResponse

SANDBOX_MODE = os.getenv("JAVA_SANDBOX_MODE", "subprocess")
SANDBOX_IMAGE = os.getenv("JAVA_SANDBOX_IMAGE", "lampochki-sandbox")
_ERR_RE = re.compile(r"^(?P<file>[\w./-]+\.java):(?P<line>\d+):\s*(?:error:\s*)?(?P<msg>.*)$")
_MAX_OUT = 200_000
_IDENT = re.compile(r"[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*")
_FILENAME = re.compile(r"[A-Za-z_$][\w$]*\.(java|py)")

_JAVAC_PATH: str | None = None
_JAVA_PATH: str | None = None


def _find_jdk() -> tuple[str, str]:
    """Find working javac and java binaries, auto-discovering on Windows if needed."""
    global _JAVAC_PATH, _JAVA_PATH
    if _JAVAC_PATH and _JAVA_PATH:
        return _JAVAC_PATH, _JAVA_PATH

    jc = shutil.which("javac")
    ja = shutil.which("java")
    if jc and ja:
        _JAVAC_PATH, _JAVA_PATH = jc, ja
        return _JAVAC_PATH, _JAVA_PATH

    # Check JAVA_HOME
    jh = os.getenv("JAVA_HOME")
    if jh:
        p = Path(jh) / "bin"
        c_exe = p / ("javac.exe" if sys.platform == "win32" else "javac")
        j_exe = p / ("java.exe" if sys.platform == "win32" else "java")
        if c_exe.is_file() and j_exe.is_file():
            _JAVAC_PATH, _JAVA_PATH = str(c_exe), str(j_exe)
            _ensure_path(p)
            return _JAVAC_PATH, _JAVA_PATH

    # Common Windows directories
    if sys.platform == "win32":
        import glob
        patterns = [
            r"C:\Program Files\Android\openjdk\jdk-*\bin\javac.exe",
            r"C:\Program Files\JetBrains\*\jbr\bin\javac.exe",
            r"C:\Program Files\Java\jdk*\bin\javac.exe",
            r"C:\Program Files\Eclipse Adoptium\jdk*\bin\javac.exe",
            r"C:\Program Files\Microsoft\jdk*\bin\javac.exe",
            r"C:\Program Files\Amazon Corretto\jdk*\bin\javac.exe",
            r"C:\Program Files\Zulu\zulu-*\bin\javac.exe",
            os.path.expanduser(r"~/.jdks/*/bin/javac.exe"),
            os.path.expanduser(r"~\AppData\Local\Programs\Eclipse Adoptium\jdk*\bin\javac.exe"),
        ]
        for pat in patterns:
            for match in sorted(glob.glob(pat), reverse=True):
                bin_dir = Path(match).parent
                j_exe = bin_dir / "java.exe"
                if j_exe.is_file():
                    _JAVAC_PATH, _JAVA_PATH = match, str(j_exe)
                    _ensure_path(bin_dir)
                    return _JAVAC_PATH, _JAVA_PATH

    _JAVAC_PATH = jc or "javac"
    _JAVA_PATH = ja or "java"
    return _JAVAC_PATH, _JAVA_PATH


def _ensure_path(bin_dir: Path) -> None:
    s = str(bin_dir)
    cur = os.environ.get("PATH", "")
    if s.lower() not in cur.lower().split(os.pathsep):
        os.environ["PATH"] = s + os.pathsep + cur
    jh = os.environ.get("JAVA_HOME")
    if not jh or not Path(jh).is_dir():
        os.environ["JAVA_HOME"] = str(bin_dir.parent)


def get_javac_cmd() -> str:
    return _find_jdk()[0]


def get_java_cmd() -> str:
    return _find_jdk()[1]


def is_python_code(code: str, lang_hint: str | None = None) -> bool:
    """Determine if the source code is Python or Java."""
    if lang_hint in ("python", "py"):
        return True
    if lang_hint in ("java",):
        return False
    # Explicit Java indicators
    if re.search(r"\b(public|private|protected)\s+(class|interface|enum|static|void)\b", code):
        return False
    if re.search(r"\bimport\s+java\.", code) or "System.out." in code:
        return False
    # Explicit Python indicators
    if re.search(r"^\s*(def|async\s+def)\s+\w+\s*\(", code, re.M):
        return True
    if "__name__" in code and "__main__" in code:
        return True
    if re.search(r"^\s*from\s+\w+\s+import", code, re.M):
        return True
    if re.search(r"^\s*import\s+\w+", code, re.M) and not code.strip().endswith(";"):
        return True
    if re.search(r"^\s*class\s+\w+\s*(\([^)]*\))?:", code, re.M):
        return True
    if re.search(r"\b(print|input)\s*\(", code):
        return True
    # Fallback to AST verification
    import ast
    try:
        ast.parse(code)
        return True
    except Exception:
        return False


def _validate(files: dict[str, str], main_class: str) -> None:
    """Reject names that could escape the temp dir or inject CLI/shell text."""
    if main_class and not _IDENT.fullmatch(main_class):
        raise ValueError(f"Недопустимое имя главного класса: {main_class!r}")
    for name in files:
        if not _FILENAME.fullmatch(name):
            raise ValueError(f"Недопустимое имя файла: {name!r}")


def detect_main_class(code: str) -> str | None:
    """Name of the first class that declares ``public static void main``."""
    if is_python_code(code):
        return "main"
    from core.parser import parse_java

    ast = parse_java(code)["ast"]
    for cls in ast.get("classes", []):
        for m in cls.get("methods", []):
            if m["name"] == "main" and "static" in m.get("modifiers", []):
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
            errors[-1]["message"] += " (" + " ".join(line.split()) + ")"
    return errors


def check_compiles(code: str, language: str | None = None) -> list[dict] | None:
    """Syntax/compilation check. Returns [] if clean, list of error dicts if failed."""
    if is_python_code(code, language):
        try:
            compile(code, "snippet.py", "exec")
            return []
        except SyntaxError as exc:
            return [{"file": "snippet.py", "line": exc.lineno or 1, "message": exc.msg or "Syntax error"}]

    if SANDBOX_MODE == "docker":
        return None
    fname = f"{_public_class(code) or 'Snippet'}.java"
    tmp = Path(tempfile.mkdtemp(prefix="jb_chk_"))
    try:
        (tmp / fname).write_text(code, encoding="utf-8")
        proc = subprocess.run(
            [get_javac_cmd(), "-proc:none", "-encoding", "UTF-8", "-d", str(tmp / "out"), fname],
            cwd=tmp, capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if proc.returncode == 0:
        return []
    return parse_compile_errors(proc.stderr) or [{"file": fname, "line": 0, "message": proc.stderr.strip()[:200]}]


def _trim(s: str) -> str:
    return s if len(s) <= _MAX_OUT else s[:_MAX_OUT] + "\n…[output truncated]"


def run_python(code: str, stdin_input: str = "", timeout_sec: int = 10) -> RunResponse:
    """Compile and run modern Python code with stdin/stdout capture."""
    try:
        compile(code, "main.py", "exec")
    except SyntaxError as exc:
        return RunResponse(
            stderr=f"SyntaxError: {exc.msg} (line {exc.lineno})\n",
            exit_code=1,
            compile_errors=[{"file": "main.py", "line": exc.lineno or 1, "message": exc.msg or "SyntaxError"}],
        )

    tmp = Path(tempfile.mkdtemp(prefix="jb_py_run_"))
    try:
        script = tmp / "main.py"
        script.write_text(code, encoding="utf-8")
        started = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-u", "main.py"],
                cwd=tmp,
                input=stdin_input,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            return RunResponse(
                stdout=_trim(proc.stdout),
                stderr=_trim(proc.stderr),
                exit_code=proc.returncode,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            return RunResponse(
                stdout=_trim(out),
                stderr=f"Timeout: выполнение превысило {timeout_sec} с",
                exit_code=124,
                duration_ms=timeout_sec * 1000,
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_python_files(files: dict[str, str], entry_file: str = "main.py", stdin_input: str = "", timeout_sec: int = 10) -> RunResponse:
    """Run a multi-file Python project."""
    compile_errs = []
    for fname, content in files.items():
        try:
            compile(content, fname, "exec")
        except SyntaxError as exc:
            compile_errs.append({"file": fname, "line": exc.lineno or 1, "message": exc.msg or "SyntaxError"})
    if compile_errs:
        return RunResponse(stderr="SyntaxError in files\n", exit_code=1, compile_errors=compile_errs)

    tmp = Path(tempfile.mkdtemp(prefix="jb_py_files_"))
    try:
        for fname, content in files.items():
            fpath = tmp / fname
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

        target = entry_file if (tmp / entry_file).is_file() else list(files.keys())[0]
        started = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-u", target],
                cwd=tmp,
                input=stdin_input,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            return RunResponse(
                stdout=_trim(proc.stdout),
                stderr=_trim(proc.stderr),
                exit_code=proc.returncode,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            return RunResponse(
                stdout=_trim(out),
                stderr=f"Timeout: выполнение превысило {timeout_sec} с",
                exit_code=124,
                duration_ms=timeout_sec * 1000,
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_files(files: dict[str, str], main_class: str, stdin_input: str = "", timeout_sec: int = 10) -> RunResponse:
    """Compile every file in *files* (name -> source) and run *main_class*."""
    # Check if this is a Python project
    if any(name.endswith(".py") for name in files):
        entry = f"{main_class}.py" if not main_class.endswith(".py") else main_class
        return run_python_files(files, entry_file=entry, stdin_input=stdin_input, timeout_sec=timeout_sec)

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
    """Compile and run a single-file Java program."""
    main_class = main_class or detect_main_class(code) or _public_class(code) or "Main"
    fname = f"{_public_class(code) or main_class}.java"
    return run_files({fname: code}, main_class, stdin_input, timeout_sec)


def run_code(code: str, main_class: str | None = None, stdin_input: str = "", timeout_sec: int = 10, language: str | None = None) -> RunResponse:
    """Universal runner for both Java and Python."""
    if is_python_code(code, language):
        return run_python(code, stdin_input, timeout_sec)
    return run_java(code, main_class, stdin_input, timeout_sec)


def _run_local(tmp: Path, names: list[str], main_class: str, stdin_input: str, timeout: int, started: float) -> RunResponse:
    javac_cmd = get_javac_cmd()
    java_cmd = get_java_cmd()
    try:
        comp = subprocess.run(
            [javac_cmd, "-encoding", "UTF-8", "-d", ".", *names],
            cwd=tmp, capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError as exc:
        return RunResponse(stderr=f"Java toolchain (javac) not found: {exc}", exit_code=127)
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
            [java_cmd, "-Xmx256m", "-Dfile.encoding=UTF-8", "-cp", ".", main_class],
            cwd=tmp, input=stdin_input, capture_output=True, text=True, timeout=timeout,
        )
        return RunResponse(
            stdout=_trim(proc.stdout), stderr=_trim(proc.stderr), exit_code=proc.returncode,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    except FileNotFoundError as exc:
        return RunResponse(stderr=f"Java toolchain (java) not found: {exc}", exit_code=127)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return RunResponse(
            stdout=_trim(out), stderr=f"Timeout: выполнение превысило {timeout} с",
            exit_code=124, duration_ms=timeout * 1000,
        )


def docker_command(tmp: Path, names: list[str], main_class: str) -> list[str]:
    script = (
        f"javac -encoding UTF-8 -d /tmp/out {' '.join(names)} 2> /tmp/javac.err || "
        f"{{ cat /tmp/javac.err >&2; exit 98; }}; "
        f"java -Xmx256m -cp /tmp/out {main_class}"
    )
    cmd = [
        "docker", "run", "--rm", "-i", "--network", "none", "-m", "256m", "--cpus", "1",
        "--pids-limit", "128", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--user", "65534", "-v", f"{tmp}:/workspace:ro", "-w", "/workspace",
        "--tmpfs", "/tmp:rw,exec", SANDBOX_IMAGE, "sh", "-c", script,
    ]
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

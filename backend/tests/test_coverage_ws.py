import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from tests.test_ws import ECHO, collect
from tests.test_coverage_instrument import UNPARSEABLE


def _run(code, stdin=None):
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": code}))
        if stdin is not None:
            first = json.loads(ws.receive_text())
            ws.send_text(json.dumps({"type": "stdin", "data": stdin}))
            return [first] + collect(ws)
        return collect(ws)


def _stdout(msgs):
    return "".join(m["data"] for m in msgs if m["type"] == "stdout")


def test_coverage_before_exit():
    msgs = _run(ECHO, stdin="Bob\n")
    types = [m["type"] for m in msgs]
    assert types[-2:] == ["coverage", "exit"] and types.count("coverage") == 1
    assert set(types[:-2]) <= {"stdout", "stderr"}
    cov = msgs[-2]
    assert "error" not in cov
    assert len(cov["hits"]) == sum(len(p["outcomes"]) for p in cov["probes"])
    assert _stdout(msgs).replace("\r\n", "\n") == "name: hello Bob\n"  # CRLF on Windows
    assert msgs[0]["data"] == "name: "


LOOP = """public class Spin { public static void main(String[] a){
  System.out.println("go");
  int i = 0;
  while (true) {
    i++;
  }
} }"""


def test_coverage_after_kill():
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": LOOP}))
        assert json.loads(ws.receive_text())["type"] == "stdout"
        ws.send_text(json.dumps({"type": "kill"}))
        msgs = collect(ws)
    assert [m["type"] for m in msgs][-2:] == ["coverage", "exit"]
    cov = msgs[-2]
    assert "error" not in cov
    body = [p for p in cov["probes"] if p["kind"] == "line" and p["line"] == 5]
    assert body and cov["hits"][body[0]["slot"]] > 0


THROW = """public class Boom { public static void main(String[] a){
  int x = 1;
  int y = x + 1;
  throw new RuntimeException("boom");
} }"""


def test_coverage_on_exception():
    msgs = _run(THROW)
    cov = msgs[-2]
    assert cov["type"] == "coverage" and "error" not in cov
    lines = {p["line"]: cov["hits"][p["slot"]] for p in cov["probes"] if p["kind"] == "line"}
    assert lines[2] >= 1 and lines[3] >= 1
    assert msgs[-1]["code"] != 0


def test_no_coverage_after_compile_error():
    msgs = _run("public class B {\n int x = ;\n}")
    assert [m["type"] for m in msgs] == ["compile_error", "exit"]
    assert msgs[0]["errors"][0]["line"] == 2


def test_coverage_unavailable_reason():
    msgs = _run(UNPARSEABLE)
    assert _stdout(msgs).strip() == "o"
    cov = msgs[-2]
    assert cov["type"] == "coverage" and cov["error"].startswith("Не удалось разобрать код для покрытия")
    assert "probes" not in cov


def test_no_coverage_after_docker_compile_error(monkeypatch, tmp_path):
    from core import interactive, runner
    from core.coverage.build import CovPlan

    monkeypatch.setattr(runner, "SANDBOX_MODE", "docker")
    plan = CovPlan(error="x")
    assert interactive.final_coverage(98, plan, tmp_path) is None
    assert interactive.final_coverage(0, plan, tmp_path) == {"type": "coverage", "error": "x"}


def test_exit_sent_when_final_coverage_raises(monkeypatch):
    from core import interactive

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(interactive, "final_coverage", boom)
    msgs = _run(ECHO, stdin="Bob\n")
    assert [m["type"] for m in msgs][-2:] == ["coverage", "exit"]
    assert msgs[-2]["error"] == "Данные покрытия не получены"


# ---- Python ------------------------------------------------------------------------------------

def _run_py(code):
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": code, "language": "python"}))
        return collect(ws)


def _hits_by_line(cov, kind="line"):
    return {p["line"]: cov["hits"][p["slot"]] for p in cov["probes"] if p["kind"] == kind}


def test_python_coverage_before_exit():
    code = (Path(__file__).resolve().parents[2] / "test_monoliths" / "calculator.py").read_text(encoding="utf-8")
    msgs = _run_py(code)
    types = [m["type"] for m in msgs]
    assert types[-2:] == ["coverage", "exit"] and types.count("coverage") == 1
    assert set(types[:-2]) <= {"stdout", "stderr"}
    cov = msgs[-2]
    assert "error" not in cov and cov["probes"]
    assert len(cov["hits"]) == sum(len(p["outcomes"]) for p in cov["probes"])
    assert any(h > 0 for h in cov["hits"]) and msgs[-1]["code"] == 0
    assert {p["kind"] for p in cov["probes"]} >= {"line", "method", "branch"}


def test_python_no_coverage_after_syntax_error():
    msgs = _run_py("def f(:\n  pass\n")
    assert [m["type"] for m in msgs] == ["compile_error", "exit"]


PY_LOOP = "print('go', flush=True)\ni = 0\nwhile True:\n    i += 1\n"


def test_python_coverage_after_kill():
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": PY_LOOP, "language": "python"}))
        assert json.loads(ws.receive_text())["type"] == "stdout"
        ws.send_text(json.dumps({"type": "kill"}))
        msgs = collect(ws)
    assert [m["type"] for m in msgs][-2:] == ["coverage", "exit"]
    cov = msgs[-2]
    assert "error" not in cov and _hits_by_line(cov)[4] > 0


def test_python_coverage_after_session_timeout(monkeypatch):
    from core import interactive

    monkeypatch.setattr(interactive, "MAX_SESSION_SEC", 1)
    msgs = _run_py(PY_LOOP)
    assert "Timeout" in "".join(m.get("data", "") for m in msgs if m["type"] == "stderr")
    assert [m["type"] for m in msgs][-2:] == ["coverage", "exit"]
    assert _hits_by_line(msgs[-2])[4] > 0


def test_python_instrumentation_error_runs_original(monkeypatch):
    from core.coverage import py_cov

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(py_cov, "instrument", boom)
    msgs = _run_py("print('ok')\n")
    assert _stdout(msgs).strip() == "ok" and msgs[-1]["code"] == 0
    cov = msgs[-2]
    # the bare reason: the frontend adds «Покрытие недоступно: »
    assert cov == {"type": "coverage", "error": "не удалось инструментировать код"}


def test_python_docker_command_mounts_cov(monkeypatch):
    """Docker mode: /cov is mounted rw, JB_COV is the container path, the loader is the entry, no host fallback."""
    import asyncio
    import dataclasses
    import subprocess

    from core import interactive, runner
    from core.coverage import build

    seen = {}
    real_popen = subprocess.Popen

    def fake_popen(cmd, **kw):
        seen.update(cmd=cmd, kw=kw)
        return real_popen([sys.executable, "-c", "pass"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    monkeypatch.setattr(runner, "SANDBOX_MODE", "docker")
    monkeypatch.setattr(interactive.subprocess, "Popen", fake_popen)

    async def emit(_):
        pass

    proc, tmp, plan = asyncio.run(interactive.start_session("print(1)\n", None, emit, language="python"))
    try:
        proc.popen.wait()
        cmd = seen["cmd"]
        assert cmd[:2] == ["docker", "run"] and cmd[cmd.index("--network") + 1] == "none"
        assert f"{tmp}:/workspace:ro" in cmd and "--ulimit" in cmd
        rw = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v" and cmd[i + 1].endswith(":rw")]
        cov = tmp / "cov"
        # only the two pre-created files are writable: no rw directory for untrusted code
        assert rw == [f"{cov / 'hits.bin'}:/cov/hits.bin:rw", f"{cov / 'compiled'}:/cov/compiled:rw"]
        assert (cov.stat().st_mode & 0o777) == 0o755
        assert "JB_COV=/cov/hits.bin" in cmd and f"JB_COV_SLOTS={plan.slots}" in cmd
        assert cmd[-3:] == ["python3", "-u", "_jb_run.py"]
        assert not any(c == str(cov / "hits.bin") or c.startswith("JB_COV=" + str(tmp)) for c in cmd)
        assert seen["kw"].get("env") is None and seen["kw"].get("preexec_fn") is None
        # the marker is empty until the container writes into it → coverage is unavailable
        assert interactive.final_coverage(0, dataclasses.replace(plan), tmp)["error"] == build.PY_UNAVAILABLE
        (cov / "compiled").write_text("1")
        assert "hits" in interactive.final_coverage(0, dataclasses.replace(plan), tmp)
        # a Python run has no compile step in the container: exit 98 is the program's own
        assert interactive.final_coverage(98, dataclasses.replace(plan), tmp) is not None
        # a symlinked marker never counts
        target = tmp / "elsewhere"
        target.write_text("1")
        (cov / "compiled").unlink()
        try:
            (cov / "compiled").symlink_to(target)
        except OSError:
            return
        assert "error" in interactive.final_coverage(0, dataclasses.replace(plan), tmp)
    finally:
        interactive.cleanup(tmp)


def test_java_docker_prepare_keeps_cov_dir_private(tmp_path):
    from core import interactive

    ok, plan = interactive._prepare_docker(tmp_path, "Echo.java", ECHO)
    assert ok and plan.language == "java"
    cov = tmp_path / "cov"
    assert (cov.stat().st_mode & 0o777) == 0o755
    marker = cov / "compiled"
    assert marker.is_file() and marker.stat().st_size == 0 and (marker.stat().st_mode & 0o777) == 0o666


def test_python_child_instrumentation_failure_is_reported(monkeypatch):
    """The child cannot instrument (slot count mismatch) → no marker → an error, not 0 %."""
    from core.coverage import build

    real = build.prepare_python

    def mismatched(tmp, code):
        plan = real(tmp, code)
        plan.slots += 1
        plan.data_file.write_bytes(bytes(plan.slots * 4))
        return plan

    monkeypatch.setattr(build, "prepare_python", mismatched)
    msgs = _run_py("print('ok')\n")
    assert _stdout(msgs).strip() == "ok" and msgs[-1]["code"] == 0
    assert msgs[-2] == {"type": "coverage", "error": build.PY_UNAVAILABLE}

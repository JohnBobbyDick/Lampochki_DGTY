"""User code must not see the backend's secrets; Python runs are limited and go through docker in docker mode."""

import json
import os

import pytest
from fastapi.testclient import TestClient

from core import interactive, runner
from main import app

PY_ENV = "import os\nprint(os.environ.get('GEMINI_API_KEY'))\nprint(os.environ.get('HTTPS_PROXY'))\n"
JAVA_ENV = """public class Env { public static void main(String[] a){
  System.out.println(System.getenv("GEMINI_API_KEY"));
  System.out.println(System.getenv("HTTPS_PROXY"));
} }"""


@pytest.fixture
def secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key-1234")
    monkeypatch.setenv("HTTPS_PROXY", "http://user:pass@1.2.3.4:8080")


def _collect(ws):
    out = []
    while True:
        m = json.loads(ws.receive_text())
        out.append(m)
        if m["type"] == "exit":
            return out


def test_child_env_is_allowlisted(secrets):
    env = runner.python_env()
    assert "GEMINI_API_KEY" not in env and "HTTPS_PROXY" not in env
    assert env["PYTHONIOENCODING"] == "utf-8" and env["PYTHONUNBUFFERED"] == "1" and "PATH" in env


def test_batch_python_does_not_see_secrets(secrets):
    r = runner.run_code(PY_ENV, language="python")
    assert r.exit_code == 0 and r.stdout.split() == ["None", "None"]


def test_batch_java_does_not_see_secrets(secrets):
    r = runner.run_java(JAVA_ENV)
    assert r.exit_code == 0 and r.stdout.split() == ["null", "null"]


def test_interactive_python_does_not_see_secrets_and_reports_coverage(secrets):
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": PY_ENV, "language": "python"}))
        msgs = _collect(ws)
    out = "".join(m.get("data", "") for m in msgs if m["type"] == "stdout")
    assert out.split() == ["None", "None"]
    cov = [m for m in msgs if m["type"] == "coverage"]
    assert len(cov) == 1 and "error" not in cov[0] and cov[0]["probes"]
    assert msgs[-1] == {**msgs[-1], "type": "exit", "code": 0}
    assert msgs.index(cov[0]) == len(msgs) - 2     # after all output, right before exit


def test_interactive_java_does_not_see_secrets(secrets):
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": JAVA_ENV}))
        msgs = _collect(ws)
    out = "".join(m.get("data", "") for m in msgs if m["type"] == "stdout")
    assert out.split() == ["null", "null"]


def test_python_syntax_error_sends_no_coverage():
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": "def f(:\n  pass\n", "language": "python"}))
        msgs = _collect(ws)
    assert msgs[0]["type"] == "compile_error" and msgs[0]["errors"][0]["line"] == 1
    assert not any(m["type"] == "coverage" for m in msgs)


@pytest.mark.skipif(os.name != "posix", reason="RLIMIT_AS is POSIX-only")
def test_python_memory_limit_is_set_in_child():
    code = "import resource\nprint(resource.getrlimit(resource.RLIMIT_AS)[0])\n"
    r = runner.run_code(code, language="python")
    assert r.exit_code == 0
    limit = int(r.stdout.strip())
    # the macOS kernel ignores RLIMIT_AS (the limit stays unlimited there); Linux — the docker/prod target — applies it
    if os.uname().sysname == "Linux":
        assert limit == runner.PY_MEMORY_LIMIT


def test_python_uses_docker_in_docker_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "SANDBOX_MODE", "docker")
    cmd, env = runner.python_command(tmp_path, "main.py")
    assert cmd[:2] == ["docker", "run"] and "--network" in cmd and cmd[cmd.index("--network") + 1] == "none"
    assert "-m" in cmd and "--read-only" in cmd and runner.SANDBOX_IMAGE in cmd
    assert cmd[-3:] == ["python3", "-u", "main.py"]
    assert not any("GEMINI" in c for c in cmd)


def test_batch_python_in_docker_mode_never_runs_on_host(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        import subprocess
        return subprocess.CompletedProcess(cmd, 0, "ok\n", "")

    monkeypatch.setattr(runner, "SANDBOX_MODE", "docker")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    r = runner.run_code("print('ok')\n", language="python")
    assert r.stdout == "ok\n" and seen["cmd"][0] == "docker"

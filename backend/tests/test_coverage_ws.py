import json

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

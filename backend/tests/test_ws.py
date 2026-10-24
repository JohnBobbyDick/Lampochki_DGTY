import json
import sys

import pytest
from fastapi.testclient import TestClient

from main import app

ECHO = """import java.util.Scanner;
public class Echo { public static void main(String[] a){
  Scanner s = new Scanner(System.in);
  System.out.print("name: ");
  String n = s.nextLine();
  System.out.println("hello " + n);
} }"""


def collect(ws):
    out = []
    while True:
        m = json.loads(ws.receive_text())
        out.append(m)
        if m["type"] == "exit":
            return out


def test_interactive_prompt_then_input():
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": ECHO}))
        first = json.loads(ws.receive_text())
        assert first["type"] == "stdout" and first["data"] == "name: "   # prompt arrives before any input
        ws.send_text(json.dumps({"type": "stdin", "data": "Bob\n"}))
        rest = collect(ws)
        assert "hello Bob" in "".join(m.get("data", "") for m in rest)
        assert rest[-1]["code"] == 0


def test_compile_error_is_reported():
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": "public class B { int x = ; }"}))
        msgs = collect(ws)
        assert msgs[0]["type"] == "compile_error" and msgs[0]["errors"][0]["line"] == 1


def test_foreign_origin_is_rejected():
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with TestClient(app).websocket_connect("/api/ws/run", headers={"origin": "https://evil.example"}):
            pass


def test_dev_origin_is_accepted():
    with TestClient(app).websocket_connect("/api/ws/run", headers={"origin": "http://localhost:3000"}) as ws:
        ws.send_text(json.dumps({"type": "start", "code": "public class B { int x = ; }"}))
        assert json.loads(ws.receive_text())["type"] == "compile_error"


SLEEPER = "import time\ntime.sleep(60)\n"
CHUNK = "x" * 262_144
LIMIT_MSG = "Слишком много ввода: лимит 1 МБ на запуск"


def _run_unread(chunks: int) -> list[dict]:
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": SLEEPER, "language": "python"}))
        for _ in range(chunks):
            ws.send_text(json.dumps({"type": "stdin", "data": CHUNK}))
        ws.send_text(json.dumps({"type": "kill"}))
        return collect(ws)


def _run_with_deadline(chunks: int, seconds: float = 20.0) -> list[dict]:
    import threading

    box: list = []
    t = threading.Thread(target=lambda: box.append(_run_unread(chunks)), daemon=True)
    t.start()
    t.join(seconds)
    assert box, "сервер завис: exit не пришёл"
    return box[0]


def test_unread_stdin_does_not_block_stop():
    msgs = _run_with_deadline(3)   # 768 KB: больше буфера канала, меньше лимита
    assert msgs[-1]["type"] == "exit"
    assert not any(LIMIT_MSG in m.get("data", "") for m in msgs)


def test_stdin_limit_is_reported():
    msgs = _run_with_deadline(5)   # 1.25 MB > 1 MB
    assert msgs[-1]["type"] == "exit"
    assert sum(1 for m in msgs if m["type"] == "stderr" and LIMIT_MSG in m["data"]) == 1


READ_ALL = "import sys\nprint(sys.stdin.read().replace(chr(10), '|'))\n"


def _writers_alive() -> int:
    import threading

    return sum(1 for t in threading.enumerate() if t.name == "jb-stdin-writer" and t.is_alive())


def test_eof_after_queued_input_ends_run_naturally():
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": READ_ALL, "language": "python"}))
        ws.send_text(json.dumps({"type": "stdin", "data": "a\n"}))
        ws.send_text(json.dumps({"type": "stdin", "data": "b\n"}))
        ws.send_text(json.dumps({"type": "eof"}))
        msgs = collect(ws)
    assert "a|b|" in "".join(m.get("data", "") for m in msgs if m["type"] == "stdout"), msgs
    assert msgs[-1]["code"] == 0


def test_writer_thread_finishes_after_natural_exit():
    import time

    before = _writers_alive()
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": "print(1)\n", "language": "python"}))
        ws.send_text(json.dumps({"type": "stdin", "data": "unused\n"}))
        collect(ws)
    deadline = time.monotonic() + 5
    while _writers_alive() > before and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _writers_alive() <= before


def test_interactive_timeout_limit(monkeypatch):
    from core import interactive
    monkeypatch.setattr(interactive, "MAX_SESSION_SEC", 1)
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": "public class Inf { public static void main(String[] a){ while(true){} } }"}))
        msgs = collect(ws)
        stderr = "".join(m.get("data", "") for m in msgs if m["type"] == "stderr")
        assert "Timeout: сессия дольше 1 с" in stderr
        assert msgs[-1]["code"] != 0


def test_interactive_java_memory_limit():
    code = "public class OOM { public static void main(String[] a){ byte[] b = new byte[120 * 1024 * 1024]; } }"
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": code}))
        msgs = collect(ws)
        stderr = "".join(m.get("data", "") for m in msgs if m["type"] == "stderr")
        assert "OutOfMemoryError" in stderr
        assert msgs[-1]["code"] != 0


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS ignores RLIMIT_AS; the limit works on Linux and Windows")
def test_interactive_python_memory_limit():
    code = "a = bytearray(150 * 1024 * 1024)"
    with TestClient(app).websocket_connect("/api/ws/run") as ws:
        ws.send_text(json.dumps({"type": "start", "code": code, "language": "python"}))
        msgs = collect(ws)
        stderr = "".join(m.get("data", "") for m in msgs if m["type"] == "stderr")
        assert "MemoryError" in stderr or msgs[-1]["code"] != 0

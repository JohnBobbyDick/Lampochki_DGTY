import json

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

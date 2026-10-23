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

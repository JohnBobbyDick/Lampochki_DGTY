import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ai import llm_client
from main import app

client = TestClient(app)
DEFECT = {"message": "Вложенный цикл по одной и той же коллекции «items» — повторная обработка пар элементов",
          "lineStart": 47, "lineEnd": 50, "severity": "warning", "bigO": "O(n²)",
          "method": "Analyzer.mergeItems", "recommendation": "HashMap"}


@pytest.fixture(autouse=True)
def parsed(read_java, monkeypatch):
    for k in ("LLM_ENABLED", "GEMINI_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    client.post("/api/parse", json={"code": read_java("Analyzer")})


def test_status_disabled_by_default():
    assert client.get("/api/ai/status").json()["enabled"] is False


def test_explain_falls_back_to_static_tips():
    r = client.post("/api/ai/explain", json={"defect": DEFECT}).json()
    assert r["source"] == "static" and "HashMap" in r["explanation"] and r["fixedCode"]
    assert "LLM" in r["note"]


def test_explain_with_mocked_gemini(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["key"], seen["body"] = str(request.url), request.headers.get("x-goog-api-key"), json.loads(request.content)
        text = json.dumps({"explanation": "Используйте HashMap", "fixed_code": "Map<String,Item> m = new HashMap<>();"})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    r = client.post("/api/ai/explain", json={"defect": DEFECT}).json()
    assert r["source"] == "gemini" and r["explanation"] == "Используйте HashMap"
    assert seen["key"] == "SECRET-KEY" and "SECRET-KEY" not in seen["url"]
    prompt = seen["body"]["contents"][0]["parts"][0]["text"]
    assert "mergeItems" in prompt and "O(n²)" in prompt     # method code + defect reach the prompt


def test_llm_http_error_does_not_leak_key(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY")
    real = httpx.AsyncClient
    monkeypatch.setattr(llm_client.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(403, text="bad key")), **kw))
    r = client.post("/api/ai/explain", json={"defect": DEFECT}).json()
    assert r["source"] == "static" and "403" in r["note"] and "SECRET-KEY" not in json.dumps(r)


def test_garbage_llm_answer_falls_back(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    async def fake(prompt, **kw):
        return "просто текст без json"

    monkeypatch.setattr(llm_client, "generate", fake)
    r = client.post("/api/ai/suggest", json={"codeFragment": "for(;;){}", "context": "пустой catch"}).json()
    assert r["source"] == "static" and r["suggestion"]


def test_decompose_advice_static(read_java):
    client.post("/api/parse", json={"code": read_java("Logger")})
    r = client.post("/api/ai/decompose").json()
    assert r["source"] == "static" and r["advice"]


def test_dotenv_inline_comments_and_quotes(tmp_path, monkeypatch):
    import importlib

    import config

    env = tmp_path / ".env"
    env.write_text('LLM_PROVIDER=gemini   # gemini | ollama\nGEMINI_API_KEY="abc #1"\nX_PLAIN=v\n')
    monkeypatch.delenv("JB_NO_DOTENV", raising=False)
    monkeypatch.setattr(config, "__file__", str(tmp_path / "config.py"))
    for k in ("LLM_PROVIDER", "GEMINI_API_KEY", "X_PLAIN"):
        monkeypatch.delenv(k, raising=False)
    config._load_dotenv()
    import os
    assert os.environ["LLM_PROVIDER"] == "gemini" and os.environ["GEMINI_API_KEY"] == "abc #1"
    assert os.environ["X_PLAIN"] == "v"

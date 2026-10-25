"""Test API endpoints with Python source code."""

import asyncio

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

PYTHON_CODE = """def sum_pairs(items: list[int]) -> int:
    total = 0
    for a in items:
        for b in items:
            if a < b:
                total += a * b
    return total

def main():
    xs = [1, 2, 3, 4]
    print(f"pairs = {sum_pairs(xs)}")

if __name__ == '__main__':
    main()
"""


def test_api_parse_python():
    resp = client.post("/api/parse", json={"code": PYTHON_CODE, "language": "python"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["language"] == "python"
    assert "sum_pairs" in data["methods"]
    assert "main" in data["methods"]
    assert not data["errors"]


def test_api_graph_cfg_python():
    client.post("/api/parse", json={"code": PYTHON_CODE, "language": "python"})
    resp = client.get("/api/graph", params={"type": "cfg", "method": "sum_pairs"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) >= 5
    assert len(data["edges"]) >= 5


def test_api_graph_call_python():
    client.post("/api/parse", json={"code": PYTHON_CODE, "language": "python"})
    resp = client.get("/api/graph", params={"type": "call"})
    assert resp.status_code == 200
    data = resp.json()
    assert any(n["id"] == "sum_pairs" for n in data["nodes"])


def test_api_analyze_python():
    client.post("/api/parse", json={"code": PYTHON_CODE, "language": "python"})
    resp = client.post("/api/analyze")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["defects"]) >= 1


def test_api_run_python():
    resp = client.post("/api/run", json={"code": PYTHON_CODE, "language": "python"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exitCode"] == 0
    assert "pairs = 35" in data["stdout"]


def test_api_run_compare_python():
    modified = PYTHON_CODE.replace("total = 0", "total = 0 # init")
    resp = client.post("/api/run/compare", json={"original": PYTHON_CODE, "modified": modified, "language": "python"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["behaviorPreserved"] is True


def test_api_quality_gate_python():
    modified = PYTHON_CODE.replace("total = 0", "total = 0 # gate test")
    resp = client.post("/api/quality-gate", json={"original": PYTHON_CODE, "modified": modified, "language": "python"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is True


def test_api_ai_explain_python_mocked_gemini(monkeypatch):
    import json
    import httpx
    from ai import llm_client

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        text = json.dumps({
            "explanation": "Используйте словарь или множества в Python",
            "old_code": "        for b in items:\n            if a < b:\n                total += a * b",
            "fixed_code": "        # optimized with set\n        total += sum(b for b in items if a < b)",
            "imports": []
        })
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    client.post("/api/parse", json={"code": PYTHON_CODE, "language": "python"})
    defect = {
        "message": "Вложенный цикл O(n²)",
        "lineStart": 10,
        "lineEnd": 13,
        "severity": "warning",
        "bigO": "O(n²)",
        "method": "sum_pairs",
        "recommendation": "Используйте dict/set"
    }
    resp = client.post("/api/ai/explain", json={"defect": defect, "language": "python"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "gemini"
    assert "словарь" in data["explanation"]
    prompt = seen["body"]["contents"][0]["parts"][0]["text"]
    assert "Python-ревьюер" in prompt
    assert "```python" in prompt


def test_api_ai_suggest_python_prompt(monkeypatch):
    import json
    import httpx
    from ai import llm_client

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        text = json.dumps({"suggestion": "Используйте list comprehension", "example": "[x * 2 for x in items]"})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    resp = client.post("/api/ai/suggest", json={"codeFragment": "for x in items: res.append(x * 2)", "context": "генератор списка", "language": "python"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "gemini"
    assert "list comprehension" in data["suggestion"]
    prompt = seen["body"]["contents"][0]["parts"][0]["text"]
    assert "Python-разработчик" in prompt
    assert "```python" in prompt


def test_api_ai_review_python_prompt(monkeypatch):
    import json
    import httpx
    from ai import llm_client

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        text = json.dumps({
            "summary": "Отличный код, но можно добавить type hints",
            "suggestions": [{
                "line": 8,
                "title": "Добавить docstring",
                "detail": "Опишите назначение функции",
                "old_code": "def sum_pairs(items: list[int]) -> int:\n    total = 0",
                "new_code": 'def sum_pairs(items: list[int]) -> int:\n    """Calculate pair sum."""\n    total = 0',
                "imports": []
            }]
        })
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    resp = client.post("/api/ai/review", json={"code": PYTHON_CODE, "language": "python"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "gemini"
    assert "type hints" in data["summary"]
    prompt = seen["body"]["contents"][0]["parts"][0]["text"]
    assert "Python-ревьюер" in prompt
    assert "PEP 8" in prompt


PY_WITH_JAVA_WORDS = '''# System.out.println — так было бы в Java; public class здесь не нужен
def total(items):
    s = 0
    for x in items:
        s = s + x
    return s

print(total([1, 2, 3]))
'''


def test_patch_for_python_with_java_words_validated_as_python(monkeypatch):
    """The known language reaches build_patch: a Python file is never validated as Java by a text guess."""
    import json
    from ai import ai_analyzer, llm_client, patcher

    async def fake(prompt, **kw):
        return json.dumps({"summary": "ок", "suggestions": [{
            "line": 3, "title": "sum()", "detail": "встроенная функция",
            "old_code": "    s = 0\n    for x in items:\n        s = s + x\n    return s",
            "new_code": "    return sum(items)", "imports": []}]})

    monkeypatch.setattr(llm_client, "generate", fake)
    seen = []
    real_validate = patcher.validate

    async def spy(original, patched, **kw):
        seen.append(kw.get("language"))
        return await real_validate(original, patched, **kw)

    monkeypatch.setattr(patcher, "validate", spy)
    res = asyncio.run(ai_analyzer.review(PY_WITH_JAVA_WORDS, [], language="python"))
    [item] = res["suggestions"]  # an invalid patch is dropped from the review
    assert seen == ["python"]
    p = item["patch"]
    assert p["valid"], p["problems"]
    assert p["bigo_before"] == p["bigo_after"] == {"Module.total": "O(n)"}  # sum() is O(n) too; not empty

    direct = asyncio.run(patcher.build_patch(PY_WITH_JAVA_WORDS, "s = s + x", "s += x", [], 5,
                                             language="python"))
    assert direct["valid"], direct["problems"]
    assert direct["bigo_before"] == direct["bigo_after"] == {"Module.total": "O(n)"}

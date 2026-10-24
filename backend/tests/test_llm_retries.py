import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ai import gemini_pool as gp
from ai import proxy_scheme
from ai import llm_client
from main import app


# ── list parsing ────────────────────────────────────────────────────────────────

def test_parse_proxy_formats():
    assert gp.parse_proxy("1.2.3.4:8080:user:pa:ss") == "http://user:pa%3Ass@1.2.3.4:8080"
    assert gp.parse_proxy("1.2.3.4:u:p", default_port="3128") == "http://u:p@1.2.3.4:3128"
    assert gp.parse_proxy("1.2.3.4:u:p", scheme="https", default_port="1") == "https://u:p@1.2.3.4:1"
    assert gp.parse_proxy("socks5://h:1080") == "socks5://h:1080"
    assert gp.parse_proxy("garbage") is None
    assert gp.parse_proxy("1.2.3.4:p") is None


def test_parse_lists_and_key_cap():
    assert gp.parse_keys("a, b;c\n a ,") == ["a", "b", "c"]
    assert gp.parse_keys("a,b,c", "2") == ["a", "b"]
    assert gp.parse_keys("a,b,c", "oops") == ["a", "b", "c"]
    assert len(gp.parse_proxies("1.1.1.1:80:u:p, 2.2.2.2:80:u:p, bad")) == 2


def test_credentials_are_masked_in_logs():
    assert gp.mask_proxy("http://user:secret@1.2.3.4:8080") == "http://1.2.3.4:8080"
    assert gp.mask_proxy(None) == "direct"


# ── retry algorithm ─────────────────────────────────────────────────────────────

@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "key-A,key-B,key-C")
    monkeypatch.setenv("GEMINI_PROXIES", "9.9.9.9:80:login:pw1,8.8.8.8:80:login:pw2")
    monkeypatch.setenv("GEMINI_MODEL", "m-main")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "m-mid,m-lite")
    monkeypatch.delenv("GEMINI_KEYS_COUNT", raising=False)
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "3")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_PROXY_SCHEME", raising=False)

    async def silent_sniff(*a, **k):
        return None

    monkeypatch.setattr(proxy_scheme, "sniff", silent_sniff)
    proxy_scheme._cache.clear()
    sleeps: list[float] = []

    async def fake_sleep(t):
        sleeps.append(t)

    monkeypatch.setattr(llm_client.asyncio, "sleep", fake_sleep)
    return sleeps


def install(monkeypatch, handler):
    """Replace httpx.AsyncClient with a mock transport; remember which proxy each client was given."""
    proxies: list[str | None] = []
    real = httpx.AsyncClient

    def factory(**kw):
        proxies.append(kw.pop("proxy", None))
        return real(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", factory)
    return proxies


def ok(text="{}"):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def test_rotates_keys_degrades_models_and_backs_off(env, monkeypatch):
    calls = []

    def handler(req: httpx.Request):
        calls.append((req.headers["x-goog-api-key"], str(req.url).split("/models/")[1].split(":")[0]))
        return ok('{"a": 1}') if len(calls) == 3 else httpx.Response(500, text="boom")

    proxies = install(monkeypatch, handler)
    out = asyncio.run(llm_client.generate("hi"))
    assert out == '{"a": 1}'
    assert [m for _, m in calls] == ["m-main", "m-mid", "m-lite"]           # lighter model each attempt
    assert len({k for k, _ in calls}) == 3                                    # a different key every time
    assert env == [2, 4]                                                      # pause grows by 2 s
    assert all(p and "://login:" in p for p in proxies)          # every attempt went via a proxy


def test_all_attempts_fail_reports_last_error_without_secrets(env, monkeypatch):
    install(monkeypatch, lambda r: httpx.Response(
        400, json={"error": {"message": "User location is not supported for key-A key-B key-C"}}))
    with pytest.raises(llm_client.LLMUnavailable) as e:
        asyncio.run(llm_client.generate("hi"))
    msg = str(e.value)
    assert "3 попытки" in msg and "location is not supported" in msg
    assert not any(s in msg for s in ("key-A", "key-B", "key-C", "pw1", "pw2"))


def test_connection_error_is_retried(env, monkeypatch):
    n = {"i": 0}

    def handler(req):
        n["i"] += 1
        if n["i"] == 1:
            raise httpx.ConnectError("proxy down http://login:pw1@9.9.9.9:80")
        return ok("{}")

    install(monkeypatch, handler)
    assert asyncio.run(llm_client.generate("hi")) == "{}"
    assert n["i"] == 2


def test_unparsable_answer_counts_as_failed_attempt(env, monkeypatch):
    answers = iter(["не json", '{"suggestions": []}'])
    install(monkeypatch, lambda r: ok(next(answers)))
    out = asyncio.run(llm_client.generate(
        "hi", validate=lambda t: isinstance(llm_client.parse_json(t).get("suggestions"), list)))
    assert "suggestions" in out and env == [2]


def test_key_list_wraps_around_when_exhausted(monkeypatch, env):
    monkeypatch.setenv("GEMINI_API_KEY", "only-key")
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "3")
    seen = []

    def handler(req):
        seen.append(req.headers["x-goog-api-key"])
        return httpx.Response(500) if len(seen) < 3 else ok()

    install(monkeypatch, handler)
    asyncio.run(llm_client.generate("hi"))
    assert seen == ["only-key"] * 3


def test_no_proxies_means_direct_connection(env, monkeypatch):
    monkeypatch.delenv("GEMINI_PROXIES")
    proxies = install(monkeypatch, lambda r: ok())
    asyncio.run(llm_client.generate("hi"))
    assert proxies == [None]


# ── /api/ai/review ──────────────────────────────────────────────────────────────

def test_review_endpoint(env, monkeypatch, read_java):
    review = {"summary": "Хороший код", "suggestions": [
        {"line": 47, "title": "HashMap", "detail": "Замените вложенный цикл", "example": "Map<K,V> m;"},
        {"line": "bad", "title": "Без строки", "detail": "x", "example": None},
        {"junk": True}]}
    install(monkeypatch, lambda r: ok(json.dumps(review)))
    r = TestClient(app).post("/api/ai/review", json={"code": read_java("Analyzer")}).json()
    assert r["source"] == "gemini" and r["summary"] == "Хороший код"
    assert r["suggestions"] == []     # advice-only items (no applicable patch) are hidden


def test_review_is_silent_when_llm_is_off(monkeypatch, read_java):
    monkeypatch.setenv("LLM_ENABLED", "false")
    r = TestClient(app).post("/api/ai/review", json={"code": read_java("Analyzer")}).json()
    assert r["suggestions"] == [] and r["source"] == "none"


# ── proxy protocol auto-rotation ────────────────────────────────────────────────

def test_proxy_without_scheme_is_auto():
    url = gp.parse_proxy("1.2.3.4:8080:u:p", scheme="auto")
    assert url == "auto://u:p@1.2.3.4:8080" and proxy_scheme.is_auto(url)


def test_scheme_rotates_across_attempts_and_secrets_stay_hidden(env, monkeypatch):
    monkeypatch.setenv("GEMINI_PROXIES", "9.9.9.9:80:login:pw1")
    seen = []
    proxies = install(monkeypatch, lambda r: httpx.Response(500, text="x"))
    with pytest.raises(llm_client.LLMUnavailable) as e:
        asyncio.run(llm_client.generate("hi"))
    seen = [p.split("://")[0] for p in proxies]
    assert seen[:3] == ["http", "socks5", "https"]
    assert "pw1" not in str(e.value)


def test_detected_scheme_is_used_and_remembered(env, monkeypatch):
    async def sniff(host, port, timeout=3.0):
        return "socks5"

    monkeypatch.setattr(proxy_scheme, "sniff", sniff)
    monkeypatch.setenv("GEMINI_PROXIES", "9.9.9.9:80:login:pw1")
    proxies = install(monkeypatch, lambda r: ok())
    asyncio.run(llm_client.generate("hi"))
    assert proxies[0].startswith("socks5://")
    assert proxy_scheme._cache["9.9.9.9:80"][0] == "socks5"

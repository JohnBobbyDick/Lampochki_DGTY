import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ai import llm_client, patcher
from main import app

CODE = """import java.util.List;

public class Demo {
    public static int sumPairs(List<Integer> items) {
        int total = 0;
        for (Integer a : items) {
            for (Integer b : items) {
                if (a < b) {
                    total += a * b;
                }
            }
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(sumPairs(java.util.Arrays.asList(1, 2, 3)));
    }
}
"""
OLD = """for (Integer a : items) {
    for (Integer b : items) {
        if (a < b) {
            total += a * b;
        }
    }
}"""
NEW = """int prefix = 0;
for (Integer b : items) {
    total += prefix * b;
    prefix += b;
}"""


def run(coro):
    return asyncio.run(coro)


# ── locate / reindent / imports ─────────────────────────────────────────────────

def test_locate_ignores_indentation_and_blank_lines():
    assert patcher.locate(CODE, OLD) == (6, 12)
    assert patcher.locate(CODE, "   int total = 0;\n\n return total;") is None   # not adjacent → not found


def test_locate_ambiguous_needs_hint():
    code = "class A {\n void f(){\n  x();\n }\n void g(){\n  x();\n }\n}"
    assert patcher.locate(code, "x();") is None
    assert patcher.locate(code, "x();", hint_line=6) == (6, 6)


def test_reindent_keeps_relative_structure():
    assert patcher.reindent("if (a) {\n    b();\n}", "        ") == "        if (a) {\n            b();\n        }"
    assert patcher.reindent("\n  x();\n", "\t") == "\tx();"


def test_add_imports_skips_existing_and_wildcards():
    code = "package p;\n\nimport java.util.*;\nimport java.io.File;\n\nclass A {}"
    out, added = patcher.add_imports(code, ["java.util.HashMap", "java.io.File", "java.io.IOException", "bad import!"])
    assert added == ["java.io.IOException"] and "import java.io.IOException;" in out
    out2, added2 = patcher.add_imports("class A {}", ["java.util.Map"])
    assert out2.startswith("import java.util.Map;") and added2 == ["java.util.Map"]


# ── build / validate / apply ────────────────────────────────────────────────────

def test_build_patch_valid_and_behaviour_equivalent():
    p = run(patcher.build_patch(CODE, OLD, NEW, [], hint_line=6))
    assert p["valid"] and (p["start_line"], p["end_line"]) == (6, 12)
    assert p["old_code"].startswith("        for (Integer a")            # exact text from the source
    assert p["new_code"].startswith("        int prefix = 0;")           # re-indented to the target
    out = run(patcher.apply_patch(CODE, OLD, NEW, [], 6))
    assert out["ok"] and "int prefix = 0;" in out["code"] and "for (Integer a" not in out["code"]


def test_patch_that_does_not_compile_is_rejected():
    p = run(patcher.build_patch(CODE, OLD, "total += undefinedVar;", [], 6))
    assert p["valid"] is False and "Не компилируется" in p["problems"][0]
    out = run(patcher.apply_patch(CODE, OLD, "total += undefinedVar;", [], 6))
    assert out["ok"] is False and out["code"] == CODE                      # nothing applied


def test_patch_with_syntax_error_is_rejected():
    p = run(patcher.build_patch(CODE, OLD, "for (((", [], 6))
    assert p["valid"] is False and "Синтаксическая" in p["problems"][0]


def test_missing_import_is_added_so_patch_compiles():
    new = "java.util.Map<Integer,Integer> m = new HashMap<>();\ntotal = m.size();"
    bad = run(patcher.build_patch(CODE, OLD, new, [], 6))
    good = run(patcher.build_patch(CODE, OLD, new, ["java.util.HashMap"], 6))
    assert not bad["valid"] and good["valid"] and good["imports"] == ["java.util.HashMap"]
    out = run(patcher.apply_patch(CODE, OLD, new, ["java.util.HashMap"], 6))
    assert out["ok"] and "import java.util.HashMap;" in out["code"]


def test_apply_after_user_edited_elsewhere_still_finds_fragment():
    edited = "// new comment\n// another\n" + CODE                          # lines shifted by 2
    out = run(patcher.apply_patch(edited, OLD, NEW, [], 6))
    assert out["ok"] and (out["start_line"], out["end_line"]) == (8, 14)


def test_apply_when_fragment_is_gone_fails_cleanly():
    out = run(patcher.apply_patch(CODE.replace("a * b", "a + b"), OLD, NEW, [], 6))
    assert out["ok"] is False and "изменился" in out["problems"][0]


def test_noop_patch_is_dropped():
    assert run(patcher.build_patch(CODE, OLD, OLD, [], 6)) is None


# ── through the API with a mocked LLM ───────────────────────────────────────────

def mock_llm(monkeypatch, payload):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    real = httpx.AsyncClient
    text = json.dumps(payload)
    resp = lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(resp), **kw))


def test_review_returns_applicable_patch_and_apply_endpoint_uses_it(monkeypatch):
    mock_llm(monkeypatch, {"summary": "ok", "suggestions": [
        {"line": 6, "title": "Один проход", "detail": "O(n²) → O(n)", "old_code": OLD, "new_code": NEW, "imports": []},
        {"line": 3, "title": "Совет без кода", "detail": "Добавьте javadoc", "old_code": "", "new_code": ""},
        {"line": 6, "title": "Битый патч", "detail": "x", "old_code": OLD, "new_code": "int x = ;"}]})
    c = TestClient(app)
    items = c.post("/api/ai/review", json={"code": CODE}).json()["suggestions"]
    assert items[0]["patch"]["valid"] and items[0]["line"] == 6
    assert items[1]["patch"] is None
    assert items[2]["patch"]["valid"] is False

    patch = items[0]["patch"]
    r = c.post("/api/ai/apply", json={"code": CODE, "patch": patch}).json()
    assert r["ok"] and "prefix" in r["code"]


def test_explain_returns_patch(monkeypatch):
    mock_llm(monkeypatch, {"explanation": "Лишний цикл", "old_code": OLD, "fixed_code": NEW, "imports": []})
    c = TestClient(app)
    c.post("/api/parse", json={"code": CODE})
    d = {"message": "Вложенные циклы", "lineStart": 6, "lineEnd": 12, "method": "Demo.sumPairs",
         "severity": "warning", "bigO": "O(n²)"}
    r = c.post("/api/ai/explain", json={"defect": d}).json()
    assert r["patch"]["valid"] and r["patch"]["startLine"] == 6 and r["source"] == "gemini"


def test_applied_patch_keeps_program_output():
    """The accepted rewrite must not change what the program prints (Quality-Gate style check)."""
    from core.comparator import compare_code

    out = run(patcher.apply_patch(CODE, OLD, NEW, [], 6))
    assert compare_code(CODE, out["code"], "Demo").behavior_preserved

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


# locate / reindent / imports

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


# build / validate / apply

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


# through the API with a mocked LLM

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
    assert [i["title"] for i in items] == ["Один проход"]
    assert items[0]["patch"]["valid"] and items[0]["line"] == 6

    patch = items[0]["patch"]
    r = c.post("/api/ai/apply", json={"code": CODE, "patch": patch}).json()
    assert r["ok"] and "prefix" in r["code"]


def mock_llm_seq(monkeypatch, payloads):
    """Each HTTP request gets the next payload (the last one repeats); returns the list of prompts seen."""
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    prompts = []
    real = httpx.AsyncClient

    def handler(request):
        prompts.append(json.loads(request.content)["contents"][0]["parts"][0]["text"])
        text = json.dumps(payloads[min(len(prompts), len(payloads)) - 1])
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return prompts


GOOD = {"line": 6, "title": "валидная", "detail": "d", "old_code": OLD, "new_code": NEW, "imports": []}
BAD = {"line": 6, "title": "битая", "detail": "d", "old_code": OLD, "new_code": "int x = ;", "imports": []}


def test_review_hides_invalid_and_adviceonly_items(monkeypatch):
    mock_llm(monkeypatch, {"summary": "ok", "suggestions": [
        BAD, GOOD, {"line": 3, "title": "совет", "detail": "javadoc", "old_code": "", "new_code": ""}]})
    r = TestClient(app).post("/api/ai/review", json={"code": CODE}).json()
    assert [s["title"] for s in r["suggestions"]] == ["валидная"]


def test_review_repairs_when_all_patches_invalid(monkeypatch):
    prompts = mock_llm_seq(monkeypatch, [{"summary": "s", "suggestions": [BAD]}, {"summary": "s", "suggestions": [GOOD]}])
    r = TestClient(app).post("/api/ai/review", json={"code": CODE}).json()
    assert len(prompts) == 2 and "не компилируются" in prompts[1] and "не компилируются" not in prompts[0]
    assert len(r["suggestions"]) == 1


def test_review_does_not_repair_advice_only_answer(monkeypatch):
    prompts = mock_llm_seq(monkeypatch, [{"summary": "s", "suggestions": [
        {"title": "совет", "detail": "x", "old_code": "", "new_code": ""}]}])
    r = TestClient(app).post("/api/ai/review", json={"code": CODE}).json()
    assert len(prompts) == 1 and r["suggestions"] == []


def test_explain_drops_invalid_patch(monkeypatch):
    prompts = mock_llm_seq(monkeypatch, [{"explanation": "Лишний цикл", "old_code": OLD, "fixed_code": "int x = ;",
                                          "imports": []}])
    c = TestClient(app)
    c.post("/api/parse", json={"code": CODE})
    d = {"message": "Вложенные циклы", "lineStart": 6, "lineEnd": 12, "method": "Demo.sumPairs",
         "severity": "warning", "bigO": "O(n²)"}
    r = c.post("/api/ai/explain", json={"defect": d}).json()
    assert len(prompts) == 3      # 1 + REPAIR_ROUNDS
    assert r["patch"] is None and r["fixedCode"] == "" and "безопасно применить" in r["note"]
    assert r["explanation"] == "Лишний цикл"


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


# unified validity rule

from pathlib import Path

CALC = (Path(__file__).resolve().parents[2] / "test_monoliths" / "Calculator.java").read_text(encoding="utf-8")
OLD_LOOP = "double left = evaluate(expression.substring(0, opIndex));"
NEW_LOOP = "double left = evaluate(expression.substring(0, opIndex).trim());"
BROKEN = CALC.replace("return left / right;", "return left / right", 1)   # one compile error


def test_patch_on_non_compiling_code_is_valid_if_it_adds_no_errors():
    p = asyncio.run(patcher.build_patch(BROKEN, OLD_LOOP, NEW_LOOP, []))
    assert p and p["valid"]


def test_patch_that_adds_error_to_non_compiling_code_is_rejected():
    p = asyncio.run(patcher.build_patch(BROKEN, OLD_LOOP, "int y = undefinedVar;", []))
    assert p and not p["valid"]


def test_fix_mode_requires_target_error_gone():
    line = BROKEN.split("\n").index(next(l for l in BROKEN.split("\n") if l.strip() == "return left / right")) + 1
    ok = asyncio.run(patcher.build_patch(BROKEN, "return left / right", "return left / right;", [], fix_line=line))
    noop = asyncio.run(patcher.build_patch(BROKEN, "return left / right", "return left /  right", [], fix_line=line))
    assert ok["valid"] and (noop is None or not noop["valid"])

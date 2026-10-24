import io
import zipfile
import re

import pytest
from fastapi.testclient import TestClient

from core.comparator import normalize
from core.runner import run_java
from main import app

client = TestClient(app)


def parse(code):
    r = client.post("/api/parse", json={"code": code})
    assert r.status_code == 200
    return r.json()


def test_graph_requires_parse_then_works(read_java):
    parse(read_java("Analyzer"))
    for t in ("cfg", "call", "class"):
        r = client.get("/api/graph", params={"type": t, "method": "mergeItems"})
        assert r.status_code == 200 and r.json()["nodes"]


def test_generate_edit_roundtrip(read_java):
    code = read_java("Calculator")
    parse(code)
    g = client.get("/api/graph", params={"type": "cfg", "method": "power"}).json()
    # unchanged graph -> semantically equal code
    same = client.post("/api/generate", json={"graph": {"method": "power", "nodes": g["nodes"]}})
    assert same.status_code == 200
    assert normalize(run_java(same.json()["code"]).stdout) == normalize(run_java(code).stdout)

    # edit one return node
    ret = next(n for n in g["nodes"] if n["type"] == "return")
    ret["label"] = "return 42"
    edited = client.post("/api/generate", json={"graph": {"method": "power", "nodes": g["nodes"]}})
    assert edited.status_code == 200
    assert "return 42;" in edited.json()["code"] and edited.json()["changedNodes"] == [ret["id"]]


def test_generate_rejects_broken_code(read_java):
    parse(read_java("Calculator"))
    g = client.get("/api/graph", params={"type": "cfg", "method": "power"}).json()
    ret = next(n for n in g["nodes"] if n["type"] == "return")
    ret["label"] = "return ((("
    r = client.post("/api/generate", json={"graph": {"method": "power", "nodes": g["nodes"]}})
    assert r.status_code == 422


@pytest.mark.parametrize("name", ["Analyzer", "Calculator", "Logger"])
def test_decompose_preserves_behavior(read_java, name):
    parse(read_java(name))
    d = client.post("/api/decompose").json()
    assert len(d["files"]) >= 2
    v = client.post("/api/decompose/verify").json()
    assert v["passed"], v["details"]


def test_quality_gate(read_java):
    code = read_java("Calculator")
    ok = client.post("/api/quality-gate", json={"original": code, "modified": code}).json()
    assert ok["passed"]
    bad = client.post("/api/quality-gate", json={"original": code, "modified": code.replace("Fibonacci sequence:", "Fib sequence:")}).json()
    assert not bad["passed"]


def test_analyze_reports_compile_errors(read_java):
    parse(read_java("Calculator").replace("return left / right;", "return left / right", 1))
    errs = client.post("/api/analyze").json()["compileErrors"]
    assert errs and errs[0]["line"] > 0


def test_analyze_compiles_clean_code(read_java):
    parse(read_java("Calculator"))
    assert client.post("/api/analyze").json()["compileErrors"] == []


def test_analyze_compile_errors_null_when_javac_did_not_run(read_java, monkeypatch):
    import api.analyze as analyze_mod
    monkeypatch.setattr(analyze_mod, "check_compiles", lambda code: None)
    parse(read_java("Calculator"))
    assert client.post("/api/analyze").json()["compileErrors"] is None


def test_zip_changed_files():
    r = client.post("/api/files/zip", json={"files": [{"path": "src/Demo.java", "code": "class Demo {}"},
                                                     {"path": "examples/Calc (2).java", "code": "class C {}"}]})
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert r.status_code == 200 and sorted(z.namelist()) == ["examples/Calc (2).java", "src/Demo.java"]
    assert 'filename="changed.zip"' in r.headers["content-disposition"]
    assert r.headers["content-type"] == "application/zip"


@pytest.mark.parametrize("bad", ["../evil.java", "/etc/passwd", "a\\b.java", ""])
def test_zip_rejects_unsafe_paths(bad):
    assert client.post("/api/files/zip", json={"files": [{"path": bad, "code": "x"}]}).status_code == 422


def test_zip_rejects_empty_list():
    assert client.post("/api/files/zip", json={"files": []}).status_code == 422

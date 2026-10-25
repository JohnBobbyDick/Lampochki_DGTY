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


@pytest.mark.parametrize("name", ["Analyzer", "Calculator", "Logger", "Store", "Warehouse"])
def test_decompose_preserves_behavior(read_java, name):
    parse(read_java(name))
    d = client.post("/api/decompose").json()
    assert len(d["files"]) >= 2
    v = client.post("/api/decompose/verify").json()
    assert v["passed"], v["details"]


# the first method sits right under the class header; private helpers are called from the facade
TIGHT = """public class Main {
    static int sum(int a, int b) { return a + b; }
    private static int mul(int a, int b) {
        return a * b;
    }
    // formats a value
    static String fmt(int x) { return "v=" + x; }

    public static void main(String[] args) {
        System.out.println(fmt(sum(1, 2)) + mul(2, 3));
    }
}
"""


def test_decompose_keeps_class_header_in_facade():
    parse(TIGHT)
    files = {f["name"]: f["code"] for f in client.post("/api/decompose").json()["files"]}
    assert files["Main.java"].lstrip().startswith("public class Main {")
    assert all("class Main" not in c for n, c in files.items() if n != "Main.java")
    assert "// formats a value" not in files["Main.java"]
    v = client.post("/api/decompose/verify").json()
    assert v["passed"], v["details"]


# names of moved methods also appear in strings, chars and comments: only real calls get qualified
LITERALS = """public class Main {
    static int lcm(int a, int b) { return a * b; }
    static char tag() { return 'l'; }

    public static void main(String[] args) {
        // lcm(1, 2) in a comment
        System.out.println("lcm(2, 3) = " + lcm(2, 3) + tag() + "\\"lcm(4, 5)\\"");
    }
}
"""


def test_decompose_does_not_rewrite_literals():
    parse(LITERALS)
    files = {f["name"]: f["code"] for f in client.post("/api/decompose").json()["files"]}
    main = files["Main.java"]
    assert re.search(r'"lcm\(2, 3\) = " \+ \w+\.lcm\(2, 3\)', main), main
    assert '"\\"lcm(4, 5)\\""' in main and "// lcm(1, 2) in a comment" in main
    v = client.post("/api/decompose/verify").json()
    assert v["passed"], v["details"]


def test_decompose_extracts_instance_state_into_component(read_java):
    parse(read_java("Store"))
    files = {f["name"]: f["code"] for f in client.post("/api/decompose").json()["files"]}
    log = files["TransactionLog.java"]
    assert "private List<String> transactionLog = new ArrayList<>();" in log
    assert "void logTransaction(String message)" in log and "private void" not in log
    facade = files["Store.java"]
    assert "private final TransactionLog transactionLog = new TransactionLog();" in facade
    assert "transactionLog = new ArrayList<>();" not in facade
    # the public API stays: delegates with the original signatures
    assert "public void printTransactionLog() {\n        transactionLog.printTransactionLog();" in facade
    assert "private void logTransaction(String message) {\n        transactionLog.logTransaction(message);" in facade


STATEFUL = """public class Main {
    private int hits;
    private final StringBuilder out = new StringBuilder();

    public void hit() { hits++; note("hit"); }
    public int hits() { return hits; }
    private void note(String s) { out.append(s).append(';'); }
    public String notes() { return out.toString(); }
    public String both() { return notes() + hits; }

    public static void main(String[] args) {
        Main m = new Main();
        m.hit();
        m.hit();
        System.out.println(m.hits() + " " + m.notes() + " " + m.both());
    }
}
"""


def test_extract_class_only_for_closed_groups():
    parse(STATEFUL)
    files = {f["name"]: f["code"] for f in client.post("/api/decompose").json()["files"]}
    # `out` + note/notes is closed; `hits` is touched by hit(), which calls note() — that is fine,
    # hit() reaches note() through the delegate. both() touches `hits` and calls notes(): it stays.
    assert set(files) == {"Main.java", "Out.java"}
    assert "out.append(s)" in files["Out.java"] and "hits" not in files["Out.java"]
    v = client.post("/api/decompose/verify").json()
    assert v["passed"], v["details"]


def test_warehouse_monolith_end_to_end(read_java):
    """The ~1000-line demo monolith: every method has a CFG that regenerates to the same code,
    javac is clean, the O(n²) pair search is diagnosed, and decomposition keeps the behaviour."""
    code = read_java("Warehouse")
    assert len(code.splitlines()) >= 1000
    methods = parse(code)["methods"]
    assert len(methods) > 70
    for m in methods:
        g = client.get("/api/graph", params={"type": "cfg", "method": m}).json()
        same = client.post("/api/generate", json={"graph": {"method": m, "nodes": g["nodes"]}})
        assert same.status_code == 200 and same.json()["code"] == code, m
    a = client.post("/api/analyze", json={"code": code}).json()
    assert a["compileErrors"] == []
    assert any(d.get("method") == "Warehouse.findDuplicateNames" for d in a["defects"])
    assert a["bigo"]["Warehouse.findDuplicateNames"] == "O(n²)"
    files = {f["name"] for f in client.post("/api/decompose").json()["files"]}
    assert {"Warehouse.java", "Parser.java", "Printer.java", "AuditLog.java"} <= files


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
    monkeypatch.setattr(analyze_mod, "check_compiles", lambda code, language=None: None)
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


STREAM_CODE = """import java.util.*;
import java.util.stream.*;

public class S {
    static List<Integer> s(List<Integer> xs) {
        List<Integer> r = xs.stream().filter(x -> x > 0).map(x -> x * 2).collect(Collectors.toList());
        return r;
    }

    public static void main(String[] args) {
        System.out.println(s(Arrays.asList(-1, 0, 1, 2)));
    }
}
"""


def test_generate_edits_stream_step():
    from core.runner import check_compiles

    parse(STREAM_CODE)
    g = client.get("/api/graph", params={"type": "cfg", "method": "s"}).json()
    types = [n["type"] for n in g["nodes"]]
    assert types.count("stream-op") == 2 and "stream-source" in types and "stream-terminal" in types

    same = client.post("/api/generate", json={"graph": {"method": "s", "nodes": g["nodes"]}})
    assert same.status_code == 200 and same.json()["changedNodes"] == []
    assert run_java(same.json()["code"]).stdout.strip() == "[2, 4]"

    op = next(n for n in g["nodes"] if n["type"] == "stream-op" and n["label"].startswith("filter"))
    op["label"] = "filter(x -> x >= 0)"
    r = client.post("/api/generate", json={"graph": {"method": "s", "nodes": g["nodes"]}})
    assert r.status_code == 200 and r.json()["changedNodes"] == [op["id"]]
    code = r.json()["code"]
    assert ".filter(x -> x >= 0).map((x) -> x * 2).collect(Collectors.toList());" in code
    assert check_compiles(code) == []
    assert run_java(code).stdout.strip() == "[0, 2, 4]"


def test_generate_renames_stream_variable():
    from core.runner import check_compiles

    parse(STREAM_CODE)
    g = client.get("/api/graph", params={"type": "cfg", "method": "s"}).json()
    src = next(n for n in g["nodes"] if n["type"] == "stream-source")
    ret = next(n for n in g["nodes"] if n["label"] == "return r")
    src["label"] = "List<Integer> q = xs.stream()"
    ret["label"] = "return q"
    r = client.post("/api/generate", json={"graph": {"method": "s", "nodes": g["nodes"]}})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert "List<Integer> q = xs.stream().filter((x) -> x > 0)" in code and "= List" not in code
    assert check_compiles(code) == []
    assert run_java(code).stdout.strip() == "[2, 4]"

"""Java 9–17 syntax: records, sealed types, arrow switch / switch expressions, yield,
instanceof patterns, text blocks, `var` — parsing, CFG, span-preserving graph edits, run."""
import pytest
from fastapi.testclient import TestClient

from core.comparator import normalize
from core.parser import parse_java
from core.runner import jdk_major, run_java
from main import app
from pathlib import Path

client = TestClient(app)
MODERN = (Path(__file__).resolve().parents[2] / "test_monoliths" / "Modern.java").read_text(encoding="utf-8")
needs_jdk17 = pytest.mark.skipif(jdk_major() < 17, reason="records / sealed types need JDK 17+")


def _parse(code):
    r = client.post("/api/parse", json={"code": code})
    assert r.status_code == 200 and r.json()["errors"] == [], r.json()["errors"]
    return r.json()


def _cfg(method):
    r = client.get("/api/graph", params={"type": "cfg", "method": method})
    assert r.status_code == 200, r.text
    return r.json()


def _edit(method, find, new):
    """Send the CFG of *method* with the node whose label starts with *find* relabelled *new*."""
    g = _cfg(method)
    node = next(n for n in g["nodes"] if n["label"].startswith(find))
    nodes = [{"id": n["id"], "label": new if n is node else n["label"]} for n in g["nodes"]]
    r = client.post("/api/generate", json={"graph": {"method": method, "nodes": nodes}})
    assert r.status_code == 200, r.text
    return r.json()


def _changed_lines(a: str, b: str) -> list[tuple[str, str]]:
    la, lb = a.split("\n"), b.split("\n")
    assert len(la) == len(lb)
    return [(x, y) for x, y in zip(la, lb) if x != y]


def test_parses_types_and_members():
    r = _parse(MODERN)
    kinds = {c["name"]: c["kind"] for c in r["ast"]["classes"]}
    assert kinds["Circle"] == kinds["Square"] == kinds["Pair"] == "record" and kinds["Op"] == "enum"
    circle = next(c for c in r["ast"]["classes"] if c["name"] == "Circle")
    assert [f["name"] for f in circle["fields"]] == ["r"] and circle["constructors"]
    assert next(c for c in r["ast"]["classes"] if c["name"] == "Op")["constants"] == ["ADD", "SUB"]
    assert {"Circle.area", "Modern.day", "Modern.apply"} <= set(r["methods"])
    assert "sealed" in r["ast"]["interfaces"][0]["modifiers"]


def test_enum_and_interface_methods_get_a_cfg():
    code = """interface Greeter {
    default String greet(String n) {
        if (n.isEmpty()) {
            return "hi";
        }
        return "hi " + n;
    }
}
enum Level {
    LOW, HIGH;
    Level flip() {
        return this == LOW ? HIGH : LOW;
    }
}
public class Main implements Greeter {
    public static void main(String[] args) {
        System.out.println(new Main().greet("x") + Level.LOW.flip());
    }
}
"""
    r = _parse(code)
    assert {"Greeter.greet", "Level.flip"} <= set(r["methods"])
    assert any(n["type"] == "condition" for n in _cfg("Greeter.greet")["nodes"])
    assert any(n["type"] == "return" for n in _cfg("Level.flip")["nodes"])
    labels = {n["label"] for n in client.get("/api/graph", params={"type": "class"}).json()["nodes"]}
    assert "«enum» Level" in labels and "«interface» Greeter" in labels


def test_class_diagram_marks_records():
    _parse(MODERN)
    nodes = client.get("/api/graph", params={"type": "class"}).json()["nodes"]
    circle = next(n for n in nodes if n["id"] == "Circle")
    assert circle["label"] == "«record» Circle" and "- r: double" in circle["data"]["fields"]


def test_arrow_switch_has_no_fall_through():
    _parse(MODERN)
    g = _cfg("Modern.day")
    cases = [n for n in g["nodes"] if n["type"] == "case"]
    assert [c["label"] for c in cases] == ["case 1", "case 2", "case default"]
    ids = {c["id"] for c in cases}
    # no edge from a case body into another case
    assert not any(e["target"] in ids and e["source"] not in {n["id"] for n in g["nodes"] if n["type"] == "switch"}
                   for e in g["edges"])
    # the switch expression is one node labelled with its real source
    assert any(n["label"].startswith('String kind = switch (d) { case 1, 7 -> "weekend";') for n in g["nodes"])


def test_unedited_graph_returns_identical_code():
    _parse(MODERN)
    for method in ("Modern.describe", "Modern.apply", "Modern.day", "Modern.main", "Circle.area"):
        g = _cfg(method)
        r = client.post("/api/generate", json={"graph": {"method": method, "nodes": [
            {"id": n["id"], "label": n["label"]} for n in g["nodes"]]}})
        assert r.status_code == 200 and r.json()["code"] == MODERN, method


def test_edit_changes_only_the_edited_node():
    _parse(MODERN)
    out = _edit("Modern.day", "return kind + old", 'return kind + "!" + old')
    assert _changed_lines(MODERN, out["code"]) == [
        ("        return kind + old;", '        return kind + "!" + old;')]

    _parse(MODERN)
    out = _edit("Modern.describe", "if (", "if (o instanceof Circle c && c.r() > 3)")
    assert _changed_lines(MODERN, out["code"]) == [
        ("        if (o instanceof Circle c && c.r() > 1) {", "        if (o instanceof Circle c && c.r() > 3) {")]


def test_edit_switch_expression_statement_keeps_the_rest():
    _parse(MODERN)
    out = _edit("Modern.day", "int old = switch",
                "int old = switch (d) { case 1: yield 20; default: yield 0; }")
    assert _changed_lines(MODERN, out["code"]) == [
        ("        int old = switch (d) { case 1: yield 10; default: yield 0; };",
         "        int old = switch (d) { case 1: yield 20; default: yield 0; };")]


def test_edit_keeps_anonymous_classes_and_old_formatting():
    code = """public class Main {
    static int twice(int x) { return x * 2; }

    public static void main(String[] args) {
        Runnable r = new Runnable() {
            public void run() { System.out.println("anon"); }
        };
        r.run();
        int v = twice(21);
        System.out.println(v);
    }
}
"""
    _parse(code)
    out = _edit("Main.main", "int v = twice", "int v = twice(4)")
    assert _changed_lines(code, out["code"]) == [("        int v = twice(21);", "        int v = twice(4);")]
    assert normalize(run_java(out["code"]).stdout) == "anon\n8"


@needs_jdk17
def test_modern_program_runs_and_quality_gate_passes():
    run = run_java(MODERN)
    assert run.exit_code == 0, run.stderr
    assert "weekend10 workday0" in run.stdout and "big circle 2.0" in run.stdout
    gate = client.post("/api/quality-gate", json={"original": MODERN, "modified": MODERN}).json()
    assert gate["passed"], gate["details"]


@needs_jdk17
def test_graph_edit_of_modern_code_compiles_and_changes_behaviour():
    _parse(MODERN)
    out = _edit("Modern.day", "return kind + old", 'return kind + "!" + old')
    run = run_java(out["code"])
    assert run.exit_code == 0 and "weekend!10 workday!0" in run.stdout


def test_text_block_and_lines_are_kept():
    r = parse_java(MODERN)
    main = next(m for c in r["ast"]["classes"] if c["name"] == "Modern" for m in c["methods"] if m["name"] == "main")
    first = main["body"][0]
    assert first["src"].startswith('var text = """') and first["src"].endswith('""";')
    # the line numbers after the text block are right
    assert main["body"][1]["line"] == MODERN.split("\n").index("        var list = new ArrayList<String>();") + 1


def test_coverage_instruments_arrow_cases_and_skips_pattern_conditions():
    from core.coverage.instrument import instrument_java
    inst = instrument_java(MODERN)
    branches = {p.label for p in inst.probes if p.kind == "branch"}
    assert {"case 1", "case 2"} <= branches
    # `o instanceof Circle c && …` keeps `c` in scope: no probe call around that condition
    assert not any(lbl.startswith("if (o instanceof Circle c") for lbl in branches)
    assert 'case 1 -> { __Cov.h(' in inst.code


@needs_jdk17
def test_coverage_build_of_modern_code(tmp_path):
    from core.coverage import build
    proc, plan = build.compile_local(tmp_path, "Modern.java", MODERN)
    assert proc is None and plan.error is None

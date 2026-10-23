from core.parser import parse_java


def test_analyzer_structure(read_java):
    r = parse_java(read_java("Analyzer"))
    assert r["errors"] == []
    names = {c["name"]: c for c in r["ast"]["classes"]}
    assert set(names) == {"Analyzer", "Item"}
    assert {m["name"] for m in names["Analyzer"]["methods"]} >= {"mergeItems", "main"}
    assert len(names["Item"]["fields"]) == 3
    assert r["line_map"]


def test_expressions_keep_method_chains(read_java):
    r = parse_java(read_java("Analyzer"))
    m = next(m for c in r["ast"]["classes"] for m in c["methods"] if m["name"] == "mergeItems")
    def conditions(o):
        if isinstance(o, dict):
            if o.get("type") == "IfStatement":
                yield o["condition"]
            for v in o.values():
                yield from conditions(v)
        elif isinstance(o, list):
            for i in o:
                yield from conditions(i)

    assert any("a.getId().equals(b.getId())" in c for c in conditions(m["body"]))


def test_syntax_error_is_reported():
    r = parse_java("public class X { void f( { }")
    assert r["errors"]


def test_spans_cover_whole_method(read_java):
    code = read_java("Logger")
    r = parse_java(code)
    m = next(m for c in r["ast"]["classes"] for m in c["methods"] if m["name"] == "parseLine")
    lines = code.splitlines()
    assert lines[m["span"]["end"] - 1].strip() == "}"
    assert "parseLine" in "\n".join(lines[m["span"]["start"] - 1: m["body_open"]["line"]])

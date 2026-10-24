import json

from core.parser import parse_java
from core.streams import STREAM_OPS, SOURCE_CALLS, TERMINALS, compose


def _stmts(body: str) -> list[dict]:
    code = "class A {\n void m() {\n" + body + "\n }\n}\n"
    r = parse_java(code)
    assert r["errors"] == []
    return r["ast"]["classes"][0]["methods"][0]["body"]


def _text(s: dict) -> str:
    """Statement text as the parser / code_generator render it (without `;`)."""
    t = s["type"]
    if t == "LocalVariableDeclaration":
        mods = " ".join(s.get("modifiers", []))
        d = s["declarators"][0]
        return f"{mods + ' ' if mods else ''}{s['var_type']} {d['name']} = {d['initializer']}"
    if t == "StatementExpression":
        return s["expression"]
    if t == "ReturnStatement":
        return f"return {s['expression']}"
    raise AssertionError(t)


def _one(body: str) -> dict:
    s = _stmts(body)[0]
    assert "stream" in s, s
    assert compose(s["stream"]) == _text(s)
    json.dumps(s["stream"])
    return s["stream"]


def test_constants():
    assert "filter" in STREAM_OPS and "boxed" in STREAM_OPS
    assert "collect" in TERMINALS and "toArray" in TERMINALS
    assert "stream" in SOURCE_CALLS and "parallelStream" in SOURCE_CALLS


def test_local_var_collect():
    st = _one("List<String> r = list.stream().filter(x -> x > 0).map(String::valueOf)"
              ".collect(Collectors.toList());")
    assert st["prefix"] == "List<String> r = "
    assert st["source"] == {"type": "StreamSource", "text": "list.stream()", "line": 3}
    assert [o["name"] for o in st["ops"]] == ["filter", "map"]
    assert st["ops"][0]["type"] == "StreamOp"
    assert st["ops"][0]["args"] == "(x) -> x > 0"
    assert st["ops"][0]["text"] == "filter((x) -> x > 0)"
    assert st["ops"][1]["text"] == "map(String::valueOf)"
    t = st["terminal"]
    assert t["type"] == "StreamTerminal"
    assert t["name"] == "collect"
    assert t["args"] == "Collectors.toList()"
    assert t["tail"] == ""
    assert t["text"] == "collect(Collectors.toList())"
    assert t["line"] == 3


def test_return_any_match():
    st = _one("return items.stream().anyMatch(i -> i.price > 10);")
    assert st["prefix"] == "return "
    assert st["ops"] == []
    assert st["terminal"]["name"] == "anyMatch"


def test_arrays_stream_count():
    st = _one("long c = Arrays.stream(arr).filter(v -> v % 2 == 0).count();")
    assert st["prefix"] == "long c = "
    assert st["source"]["text"] == "Arrays.stream(arr)"
    assert [o["name"] for o in st["ops"]] == ["filter"]
    assert st["terminal"]["name"] == "count"


def test_intstream_range_sum():
    st = _one("IntStream.range(0, n).map(i -> i * i).sum();")
    assert st["prefix"] == ""
    assert st["source"]["text"] == "IntStream.range(0, n)"
    assert [o["name"] for o in st["ops"]] == ["map"]
    assert st["terminal"]["name"] == "sum"


def test_this_field_stream_with_tail():
    st = _one("this.items.stream().sorted().findFirst().get();")
    assert st["source"]["text"] == "this.items.stream()"
    assert st["source"]["line"] == 3
    assert [o["name"] for o in st["ops"]] == ["sorted"]
    assert st["terminal"]["name"] == "findFirst"
    assert st["terminal"]["tail"] == ".get()"
    assert st["terminal"]["text"] == "findFirst().get()"


def test_assignment():
    st = _one("r = xs.stream().distinct().collect(Collectors.toSet());")
    assert st["prefix"] == "r = "
    assert [o["name"] for o in st["ops"]] == ["distinct"]
    assert st["terminal"]["name"] == "collect"


def test_prefix_operator_goes_to_prefix():
    st = _one("boolean e = !xs.stream().filter(x -> x > 0).collect(Collectors.toList()).isEmpty();")
    assert st["prefix"] == "boolean e = !"
    assert st["terminal"]["tail"] == ".isEmpty()"


def test_ops_without_terminal():
    st = _one("Stream<String> s = Stream.of(a, b).map(String::trim);")
    assert st["source"]["text"] == "Stream.of(a, b)"
    assert st["terminal"] is None
    assert [o["name"] for o in st["ops"]] == ["map"]


def test_multiline_lines():
    st = _one("long c = list.stream()\n"
              "    .filter(v -> v > 0)\n"
              "    .count();")
    assert st["source"]["line"] == 3
    assert st["ops"][0]["line"] == 4
    assert st["terminal"]["line"] == 5


def test_not_decomposed():
    for body in (
        "foo(list.stream().count());",
        "list.stream().weird().count();",
        "int n = list.size();",
        "Stream<String> s = list.stream();",
        "int a = 1, b = xs.stream().count();",
        "if (xs.stream().anyMatch(x -> x > 0)) { }",
    ):
        s = _stmts(body)[0]
        assert "stream" not in s, body

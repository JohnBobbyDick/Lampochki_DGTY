import copy
import json

from core.cfg_builder import build_cfg, build_cfg_with_map
from core.code_generator import regenerate_method, render_stmts
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


# ---------------------------------------------------------------------------
# Task 2: pipeline nodes in the CFG and editing single steps
# ---------------------------------------------------------------------------

_CHAIN = ("List<Integer> r = xs.stream().filter(x -> x > 0).map(x -> x * 2)"
          ".collect(Collectors.toList());\n System.out.println(r);")
_CHAIN_LINE = ("List<Integer> r = xs.stream().filter((x) -> x > 0).map((x) -> x * 2)"
               ".collect(Collectors.toList());")


def _method(body: str) -> dict:
    code = ("import java.util.*;\nimport java.util.stream.*;\nclass A {\n"
            " void s(List<Integer> xs, List<Integer> ys) {\n" + body + "\n }\n}\n")
    r = parse_java(code)
    assert r["errors"] == []
    return r["ast"]["classes"][0]["methods"][0]


def _no_stream(body: list[dict]) -> list[dict]:
    """Deep copy of statements with every `stream` field removed."""
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k != "stream"}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x
    return strip(copy.deepcopy(body))


def _node(nodes, ntype, label=None):
    return next(n for n in nodes if n.type == ntype and (label is None or n.label == label))


def test_cfg_pipeline_nodes():
    m = _method(_CHAIN)
    nodes, edges = build_cfg(m)
    assert [n.type for n in nodes] == ["start", "end", "stream-source", "stream-op", "stream-op",
                                       "stream-terminal", "statement"]
    assert [n.label for n in nodes[2:6]] == [
        "List<Integer> r = xs.stream()", "filter((x) -> x > 0)", "map((x) -> x * 2)",
        "collect(Collectors.toList())"]
    pairs = {(e.source, e.target, e.type) for e in edges}
    chain = [n.id for n in nodes]
    for a, b in [(chain[0], chain[2]), (chain[2], chain[3]), (chain[3], chain[4]),
                 (chain[4], chain[5]), (chain[5], chain[6]), (chain[6], chain[1])]:
        assert (a, b, "normal") in pairs
    assert len(edges) == 6
    src = nodes[2]
    assert src.data["code_snippet"] == src.label
    assert nodes[3].data["code_snippet"] == "filter((x) -> x > 0)"
    assert src.data["line_start"] == 5
    # deterministic ids on rebuild
    nodes2, edges2 = build_cfg(_method(_CHAIN))
    assert [(n.id, n.type, n.label) for n in nodes2] == [(n.id, n.type, n.label) for n in nodes]
    _, _, stmt_of = build_cfg_with_map(m)
    assert stmt_of[nodes[3].id]["type"] == "StreamOp"
    assert stmt_of[nodes[2].id]["type"] == "StreamSource"
    assert stmt_of[nodes[5].id]["type"] == "StreamTerminal"


def test_cfg_long_label_not_truncated():
    body = ("List<Integer> r = xs.stream().filter(x -> x > 0 && x < 1000 && x % 2 == 0 && x % 3 == 0"
            " && x % 5 == 0).collect(Collectors.toList());")
    nodes, _ = build_cfg(_method(body))
    op = _node(nodes, "stream-op")
    assert len(op.label) > 60 and op.label.endswith("((x % 5) == 0))")


def test_cfg_return_chain_goes_to_end():
    code = ("import java.util.*;\nclass A {\n long c(List<Integer> xs) {\n"
            "  return xs.stream().filter(x -> x > 0).count();\n }\n}\n")
    m = parse_java(code)["ast"]["classes"][0]["methods"][0]
    nodes, edges = build_cfg(m)
    assert [n.type for n in nodes] == ["start", "end", "stream-source", "stream-op", "stream-terminal"]
    assert nodes[2].label == "return xs.stream()"
    assert any(e.source == nodes[4].id and e.target == nodes[1].id for e in edges)
    body, changed = regenerate_method(m, {})
    assert body == ["return xs.stream().filter((x) -> x > 0).count();"] and changed == []


def test_regenerate_without_edits_equals_plain_rendering():
    m = _method(_CHAIN)
    body, changed = regenerate_method(m, {})
    assert changed == []
    assert body == render_stmts(_no_stream(m["body"]), 0)
    assert body[0] == _CHAIN_LINE


def _ids(m):
    nodes, _ = build_cfg(m)
    return {n.type + ":" + n.label: n.id for n in nodes}


def test_edit_one_op():
    m = _method(_CHAIN)
    nid = _ids(m)["stream-op:filter((x) -> x > 0)"]
    plain = render_stmts(_no_stream(m["body"]), 0)
    for label in ("filter(x -> x >= 0)", ".filter(x -> x >= 0)", "  .filter(x -> x >= 0)  "):
        body, changed = regenerate_method(m, {nid: label})
        assert changed == [nid]
        assert body[0] == ("List<Integer> r = xs.stream().filter(x -> x >= 0).map((x) -> x * 2)"
                           ".collect(Collectors.toList());")
        assert body[1:] == plain[1:]
    # the original method dict is untouched
    assert regenerate_method(m, {})[0] == plain


def test_edit_source_keeps_prefix():
    m = _method(_CHAIN)
    nid = _ids(m)["stream-source:List<Integer> r = xs.stream()"]
    for label in ("List<Integer> r = ys.stream()", "ys.stream()", "List<Integer>  r =  ys.stream()"):
        body, _ = regenerate_method(m, {nid: label})
        assert body[0] == ("List<Integer> r = ys.stream().filter((x) -> x > 0).map((x) -> x * 2)"
                           ".collect(Collectors.toList());"), label


def test_edit_terminal():
    m = _method(_CHAIN)
    nid = _ids(m)["stream-terminal:collect(Collectors.toList())"]
    body, _ = regenerate_method(m, {nid: ".collect(Collectors.toCollection(ArrayList::new));"})
    assert body[0].endswith(".map((x) -> x * 2).collect(Collectors.toCollection(ArrayList::new));")


def test_edit_multiline_chain_with_block_lambda_and_method_ref():
    body_src = ("List<String> r = xs.stream()\n"
                "    .map(x -> { return x + 1; })\n"
                "    .filter(x -> x > 2)\n"
                "    .map(String::valueOf)\n"
                "    .collect(Collectors.toList());")
    m = _method(body_src)
    nodes, _ = build_cfg(m)
    ops = [n for n in nodes if n.type == "stream-op"]
    assert [n.data["line_start"] for n in ops] == [6, 7, 8]
    before = regenerate_method(m, {})[0][0]
    filt = next(n for n in ops if n.label.startswith("filter"))
    after = regenerate_method(m, {filt.id: "filter(x -> x > 3)"})[0][0]
    assert after == before.replace(filt.label, "filter(x -> x > 3)")
    assert ".map(String::valueOf)" in after and "return x + 1;" in after
    ref = next(n for n in ops if n.label == "map(String::valueOf)")
    after2 = regenerate_method(m, {ref.id: "map(Object::toString)"})[0][0]
    assert after2 == before.replace("map(String::valueOf)", "map(Object::toString)")


def test_edit_source_with_full_chain_does_not_duplicate():
    """The node editor may send the whole statement as the source label."""
    m = _method(_CHAIN)
    nid = _ids(m)["stream-source:List<Integer> r = xs.stream()"]
    plain = regenerate_method(m, {})[0]
    full = compose(m["body"][0]["stream"])
    for label in (full, full + ";", "xs.stream().filter((x) -> x > 0) .map((x) -> x * 2)\n"
                  "   .collect(Collectors.toList())"):
        assert regenerate_method(m, {nid: label})[0] == plain, label
    body, _ = regenerate_method(m, {nid: full.replace("xs.stream()", "ys.stream()")})
    assert body[0] == _CHAIN_LINE.replace("xs.stream()", "ys.stream()")


def test_edit_source_with_full_old_chain_and_edited_op():
    m = _method(_CHAIN)
    ids = _ids(m)
    full = compose(m["body"][0]["stream"])
    body, _ = regenerate_method(m, {ids["stream-source:List<Integer> r = xs.stream()"]: full,
                                    ids["stream-op:filter((x) -> x > 0)"]: "filter(x -> x >= 0)"})
    assert body[0] == _CHAIN_LINE.replace("filter((x) -> x > 0)", "filter(x -> x >= 0)")


def test_empty_op_label_deletes_step():
    m = _method(_CHAIN)
    nid = _ids(m)["stream-op:filter((x) -> x > 0)"]
    for label in ("", "   ", " . "):
        body, changed = regenerate_method(m, {nid: label})
        assert body[0] == _CHAIN_LINE.replace(".filter((x) -> x > 0)", ""), repr(label)
        assert changed == [nid]


def test_empty_source_or_terminal_label_keeps_text():
    m = _method(_CHAIN)
    ids = _ids(m)
    for key in ("stream-source:List<Integer> r = xs.stream()",
                "stream-terminal:collect(Collectors.toList())"):
        assert regenerate_method(m, {ids[key]: "  "})[0][0] == _CHAIN_LINE

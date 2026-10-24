"""CFG labels and flow for Python methods; Java output stays byte-identical (snapshot)."""

import json
from pathlib import Path

from core.cfg_builder import build_cfg, build_cfg_with_map
from core.parser import parse_java
from core.py_parser import parse_python

SNAPSHOT = Path(__file__).parent / "data" / "java_cfg_snapshot.json"
MONOLITHS = Path(__file__).resolve().parents[2] / "test_monoliths"

CODE = '''def f(x, y, xs, n, p, c):
    if x > 0:
        a = 1
    elif y:
        a = 2
    else:
        a = 3
    for x in xs:
        if x:
            break
        a += x
    else:
        a = -1
    while n:
        n -= 1
    with open(p) as f:
        f.read()
    match c:
        case 1 | 2 if n > 0:
            a = 4
        case 3:
            a = 5
    try:
        a = int(p)
    except ValueError as e:
        a = 0
    except:
        raise
    else:
        a += 1
    finally:
        print(a)
    return a
'''


def _method(code: str, name: str = "f") -> dict:
    mod = next(c for c in parse_python(code)["ast"]["classes"] if c["name"] == "Module")
    return next(m for m in mod["methods"] if m["name"] == name)


def _graph():
    nodes, edges = build_cfg(_method(CODE))
    by_label = {n.label: n for n in nodes}
    return nodes, edges, by_label


def _out(edges, src):
    return [e for e in edges if e.source == src]


def test_python_labels():
    nodes, _, by_label = _graph()
    for label, ntype in [
        ("if x > 0", "condition"), ("elif y", "condition"), ("for x in xs", "loop"),
        ("while n", "loop"), ("with open(p) as f", "statement"), ("match c", "switch"),
        ("case 1 | 2 if n > 0", "case"), ("case 3", "case"), ("try", "try"),
        ("except ValueError as e", "catch"), ("except", "catch"), ("finally", "finally"),
        ("raise", "throw"), ("return a", "return"), ("break", "statement"), ("a += x", "statement"),
    ]:
        assert label in by_label, (label, [n.label for n in nodes])
        assert by_label[label].type == ntype, label
    assert not any("(" in n.label and n.label.startswith(("if", "for", "while", "except")) for n in nodes)


def test_with_body_follows_header():
    _, edges, by_label = _graph()
    w = by_label["with open(p) as f"]
    assert [e.target for e in _out(edges, w.id)] == [by_label["f.read()"].id]


def test_for_else_and_break():
    _, edges, by_label = _graph()
    loop = by_label["for x in xs"]
    else_first = by_label["a = -1"]
    false_edges = [e for e in _out(edges, loop.id) if e.type == "false"]
    assert [(e.target, e.label) for e in false_edges] == [(else_first.id, "else")]
    brk = by_label["break"]
    targets = {e.target for e in _out(edges, brk.id)}
    assert else_first.id not in targets
    assert targets == {by_label["while n"].id}
    # the else body flows on to the next statement
    assert {e.target for e in _out(edges, else_first.id)} == {by_label["while n"].id}


def test_loop_without_else_keeps_false_label():
    nodes, edges = build_cfg(_method("def g(n):\n    while n:\n        n -= 1\n    return n\n", "g"))
    loop = next(n for n in nodes if n.type == "loop")
    assert [(e.type, e.label) for e in _out(edges, loop.id) if e.type == "false"] == [("false", "false")]


def test_try_else_finally():
    _, edges, by_label = _graph()
    body_last = by_label["a = int(p)"]
    else_first = by_label["a += 1"]
    fin = by_label["finally"]
    assert {e.target for e in _out(edges, body_last.id)} == {else_first.id}
    assert {e.target for e in _out(edges, else_first.id)} == {fin.id}
    # handlers bypass the else body
    assert {e.target for e in _out(edges, by_label["a = 0"].id)} == {fin.id}
    try_node = by_label["try"]
    assert {e.target for e in _out(edges, try_node.id) if e.type == "exception"} == {
        by_label["except ValueError as e"].id, by_label["except"].id,
    }


def test_match_no_fallthrough():
    _, edges, by_label = _graph()
    sw = by_label["match c"]
    first_end = by_label["a = 4"]
    second = by_label["case 3"]
    assert second.id not in {e.target for e in _out(edges, first_end.id)}
    assert {e.target for e in _out(edges, first_end.id)} == {by_label["try"].id}
    assert any(e.label == "no match" and e.target == by_label["try"].id for e in _out(edges, sw.id))
    assert {(e.target, e.label) for e in _out(edges, sw.id) if e.target != by_label["try"].id} == {
        (by_label["case 1 | 2 if n > 0"].id, "1 | 2 if n > 0"), (second.id, "3"),
    }


def test_match_wildcard_has_no_no_match_edge():
    code = "def g(c):\n    match c:\n        case 1:\n            return 1\n        case _:\n            return 0\n"
    nodes, edges = build_cfg(_method(code, "g"))
    assert not any(e.label == "no match" for e in edges)
    assert any(n.label == "case _" for n in nodes)


def _match_cfg(pattern: str):
    code = f"def g(c):\n    match c:\n        case {pattern}:\n            return 1\n    return 0\n"
    return build_cfg(_method(code, "g"))


def test_literal_constant_cases_are_refutable():
    for pattern in ["True", "False", "None", "Color.RED", "1 | 2", "(1, _)", "[x]", "'a|_'", "True as t"]:
        nodes, edges = _match_cfg(pattern)
        assert any(e.label == "no match" for e in edges), pattern
        assert any(n.label == "return 0" for n in nodes), pattern


def test_irrefutable_case_forms():
    for pattern in ["_", "x", "1 | _", "_ as z", "x as y", "(_)", "((y) as z)", "Color.RED | other"]:
        nodes, edges = _match_cfg(pattern)
        assert not any(e.label == "no match" for e in edges), pattern
        assert not any(n.label == "return 0" for n in nodes), pattern


def test_python_ids_deterministic():
    a_nodes, a_edges, a_map = build_cfg_with_map(_method(CODE))
    b_nodes, b_edges, b_map = build_cfg_with_map(_method(CODE))
    assert [(n.id, n.label) for n in a_nodes] == [(n.id, n.label) for n in b_nodes]
    assert [(e.source, e.target, e.label) for e in a_edges] == [(e.source, e.target, e.label) for e in b_edges]
    assert sorted(a_map) == sorted(b_map)
    assert [n.id for n in a_nodes] == [f"n{i}" for i in range(len(a_nodes))]


def test_java_cfg_unchanged():
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = {}
    for f in ["Calculator", "Analyzer", "Logger", "Store", "Streams"]:
        res = parse_java((MONOLITHS / f"{f}.java").read_text(encoding="utf-8"))
        for c in res["ast"]["classes"]:
            for m in c["methods"]:
                nodes, edges, so = build_cfg_with_map(m)
                actual[f"{f}:{c['name']}.{m['name']}:{m.get('line_start')}"] = {
                    "nodes": [[n.id, n.type, n.label, n.data] for n in nodes],
                    "edges": [[e.id, e.source, e.target, e.type, e.label] for e in edges],
                    "stmt_of": sorted(so),
                }
    assert any(k.startswith("Calculator:") for k in expected)
    assert actual == expected

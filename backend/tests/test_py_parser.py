"""Python parser: full statement set, source text, spans (stage 7, task 3)."""

from pathlib import Path

import pytest

import state
from core.py_parser import parse_python

MONOLITHS = Path(__file__).resolve().parents[2] / "test_monoliths"


def _module(res: dict) -> dict:
    return next(c for c in res["ast"]["classes"] if c["name"] == "Module")


def _method(res: dict, name: str, cls: str = "Module") -> dict:
    c = next(c for c in res["ast"]["classes"] if c["name"] == cls)
    return next(m for m in c["methods"] if m["name"] == name)


def _body(code: str, name: str = "f") -> list[dict]:
    res = parse_python(code)
    assert res["errors"] == []
    return _method(res, name)["body"]


def _segment(code: str, rng: dict) -> str:
    lines = code.splitlines()
    if rng["line"] == rng["end_line"]:
        return lines[rng["line"] - 1][rng["col"]:rng["end_col"]]
    parts = [lines[rng["line"] - 1][rng["col"]:]]
    parts += lines[rng["line"]:rng["end_line"] - 1]
    parts.append(lines[rng["end_line"] - 1][:rng["end_col"]])
    return "\n".join(parts)


def test_statement_text_is_taken_from_source():
    body = _body('def f():\n    s = "a"; print("x", 1.50)\n')
    assert body[0]["expression"] == 's = "a"'
    assert body[1]["expression"] == 'print("x", 1.50)'


def test_if_elif_else():
    code = "def f(a, b):\n    if a:\n        x = 1\n    elif b:\n        x = 2\n    else:\n        x = 3\n"
    s = _body(code)[0]
    assert s["type"] == "IfStatement"
    assert s["then"] and s["then"][0]["expression"] == "x = 1"
    assert not s.get("elif")
    elif_ = s["else"][0]
    assert elif_["type"] == "IfStatement"
    assert elif_["elif"] is True
    assert elif_["condition"] == "b"
    assert _segment(code, elif_["header"]) == "elif b"
    assert elif_["else"][0]["expression"] == "x = 3"


def test_for_else():
    code = "def f(xs):\n    for x in xs:\n        print(x)\n    else:\n        print('done')\n"
    s = _body(code)[0]
    assert s["type"] == "ForStatement"
    assert s["control"] == "x in xs"
    assert s["else"] and s["else"][0]["expression"] == "print('done')"


def test_while_else():
    code = "def f(c):\n    while c:\n        c -= 1\n    else:\n        print(c)\n"
    s = _body(code)[0]
    assert s["type"] == "WhileStatement"
    assert s["else"] and s["else"][0]["expression"] == "print(c)"


def test_try_except_else_finally():
    code = (
        "def f():\n    try:\n        x = 1\n    except ValueError as e:\n        x = 2\n"
        "    else:\n        x = 3\n    finally:\n        x = 4\n"
    )
    s = _body(code)[0]
    assert s["type"] == "TryStatement"
    assert s["catches"][0]["types"] == ["ValueError"]
    assert s["catches"][0]["name"] == "e"
    assert _segment(code, s["catches"][0]["header"]) == "except ValueError as e"
    assert s["else"][0]["expression"] == "x = 3"
    assert s["finally"][0]["expression"] == "x = 4"
    assert _segment(code, s["header"]) == "try"


def test_bare_except_has_no_types():
    code = "def f():\n    try:\n        x = 1\n    except:\n        pass\n"
    catch = _body(code)[0]["catches"][0]
    assert catch["types"] == []
    assert _segment(code, catch["header"]) == "except"


def test_with_statement():
    code = "def f(p):\n    with open(p) as f:\n        data = f.read()\n"
    s = _body(code)[0]
    assert s["type"] == "WithStatement"
    assert s["items"] == "open(p) as f"
    assert s["body"][0]["expression"] == "data = f.read()"
    assert _segment(code, s["header"]) == "with open(p) as f"


def test_match_case_labels_and_guard():
    code = "def f(c, n):\n    match c:\n        case 1 | 2 if n > 0:\n            x = 1\n        case _:\n            x = 2\n"
    s = _body(code)[0]
    assert s["type"] == "SwitchStatement"
    assert s["no_fallthrough"] is True
    assert s["expression"] == "c"
    case = s["cases"][0]
    assert case["labels"] == ["1 | 2"]
    assert case["guard"] == "n > 0"
    assert _segment(code, case["header"]) == "case 1 | 2 if n > 0"
    assert s["cases"][1]["guard"] is None
    assert _segment(code, s["header"]) == "match c"


def test_nested_def_becomes_statement_and_method():
    code = "def outer(x):\n    def inner(a, b):\n        return a + b\n    return inner(x, 1)\n"
    res = parse_python(code)
    outer = _method(res, "outer")
    nested = outer["body"][0]
    assert nested["type"] == "StatementExpression"
    assert nested["expression"] == "def inner(a, b)"
    assert nested["nested_def"] is True
    inner = _method(res, "outer.inner")
    assert inner["body"][0]["type"] == "ReturnStatement"
    assert inner["body"][0]["expression"] == "a + b"
    found = state.find_method(res["ast"], "Module.outer.inner")
    assert found is not None and found[1]["name"] == "outer.inner"
    assert state.find_method(res["ast"], "Module.outer")[1]["name"] == "outer"


def test_find_method_on_class_still_works():
    code = "class A:\n    def m(self):\n        return 1\n"
    res = parse_python(code)
    assert state.find_method(res["ast"], "A.m")[1]["name"] == "m"


def test_methods_have_language_and_synthetic_flag():
    res = parse_python("def g():\n    return 1\n\nprint(g())\n")
    mod = _module(res)
    g = next(m for m in mod["methods"] if m["name"] == "g")
    main = next(m for m in mod["methods"] if m["name"] == "main")
    assert g["language"] == "python"
    assert not g.get("synthetic")
    assert main["language"] == "python"
    assert main["synthetic"] is True


def test_header_excludes_colon_and_comment():
    code = "def f(x):\n    if x > 0:  # c\n        pass\n"
    s = _body(code)[0]
    assert s["header"] == {"line": 2, "col": 4, "end_line": 2, "end_col": 12}
    assert _segment(code, s["header"]) == "if x > 0"


def test_header_skips_lambda_colon():
    code = "def f(x):\n    if f(lambda y: y):\n        pass\n"
    s = _body(code)[0]
    assert _segment(code, s["header"]) == "if f(lambda y: y)"


def test_span_of_multiline_call():
    code = "def f():\n    print(\n        1,\n        2,\n    )\n"
    s = _body(code)[0]
    span = s["span"]
    assert span["end_line"] > span["line"]
    assert (span["line"], span["col"]) == (2, 4)
    assert (span["end_line"], span["end_col"]) == (5, 5)


def test_span_col_counts_characters():
    code = 'def f():\n    x = "й"; y = 1\n'
    s = _body(code)[1]
    assert s["span"]["col"] == 13
    assert _segment(code, s["span"]) == "y = 1"


def test_syntax_error_reports_line():
    res = parse_python("def f():\n    x = (\n\ny = 2\n")
    assert res["errors"]
    assert any(ch.isdigit() for ch in res["errors"][0])


@pytest.mark.parametrize("name", ["calculator", "store", "analyzer", "logger"])
def test_monolith_fixtures_parse(name):
    res = parse_python((MONOLITHS / f"{name}.py").read_text(encoding="utf-8"))
    assert res["errors"] == []
    for cls in res["ast"]["classes"]:
        for m in cls["methods"]:
            assert m["language"] == "python"


def test_with_body_still_reaches_cfg():
    from core.cfg_builder import build_cfg

    res = parse_python("def f(p):\n    with open(p) as f:\n        data = f.read()\n    return data\n")
    nodes, _ = build_cfg(_method(res, "f"))
    assert any(n.label == "data = f.read()" for n in nodes)

"""Python graph edits: in-place replacement of statement / header spans."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.cfg_builder import build_cfg_with_map
from core.py_codegen import apply_edits
from core.py_parser import parse_python
from main import app

client = TestClient(app)
MONOLITHS = sorted((Path(__file__).resolve().parents[2] / "test_monoliths").glob("*.py"))


def _methods(code: str) -> list[dict]:
    res = parse_python(code)
    assert not res["errors"], res["errors"]
    return [m for c in res["ast"]["classes"] for m in c["methods"]]


def _method(code: str, name: str) -> dict:
    if name == "<top>":
        return next(m for m in _methods(code) if m.get("synthetic"))
    return next(m for m in _methods(code) if m["name"] == name)


def _node(method: dict, label: str) -> str:
    nodes, _, _ = build_cfg_with_map(method)
    return next(n.id for n in nodes if n.label == label)


def _edit(code: str, name: str, label: str, new: str) -> tuple[str, list[str]]:
    m = _method(code, name)
    return apply_edits(code, m, {_node(m, label): new})


def _diff(a: str, b: str) -> list[tuple[str, str]]:
    la, lb = a.split("\n"), b.split("\n")
    assert len(la) == len(lb)
    return [(x, y) for x, y in zip(la, lb) if x != y]


@pytest.mark.parametrize("path", MONOLITHS, ids=lambda p: p.name)
def test_roundtrip_without_edits(path):
    code = path.read_text(encoding="utf-8")
    for m in _methods(code):
        assert apply_edits(code, m, {}) == (code, [])
        nodes, _, _ = build_cfg_with_map(m)
        # labels equal to the original ones are not edits
        assert apply_edits(code, m, {n.id: n.label for n in nodes if not n.label.startswith(("START", "END"))}) \
            == (code, [])


@pytest.mark.parametrize("path", MONOLITHS, ids=lambda p: p.name)
def test_roundtrip_through_api(path):
    code = path.read_text(encoding="utf-8")
    assert client.post("/api/parse", json={"code": code, "language": "python"}).status_code == 200
    refs = [f"{c['name']}.{m['name']}" for c in parse_python(code)["ast"]["classes"] for m in c["methods"]]
    for ref in refs:
        g = client.get("/api/graph", params={"type": "cfg", "method": ref})
        assert g.status_code == 200, (ref, g.text)
        r = client.post("/api/generate", json={"graph": {"method": ref, "nodes": g.json()["nodes"]},
                                               "language": "python"})
        assert r.status_code == 200, (ref, r.text)
        assert r.json()["code"] == code
        assert r.json()["changedNodes"] == []


CODE = '''def show(name, n):
    # приветствие
    msg = f"Привет, {name}!"  # f-строка
    if n > 10:  # большое
        print('много')
    elif n > 5:
        print("средне")
    for i in range(n):  # цикл
        print(i)
    while n > 0:  # пока
        n -= 1
    try:
        x = int(name)
    except ValueError as e:
        x = 0
    except:
        x = -1
    return msg  # итог


if __name__ == "__main__":
    show("мир", 3)
    print("готово")
'''


def test_return_edit_changes_one_line():
    new, changed = _edit(CODE, "show", "return msg", "return msg.upper()")
    assert _diff(CODE, new) == [("    return msg  # итог", "    return msg.upper()  # итог")]
    assert len(changed) == 1


def test_elif_keeps_keyword():
    new, _ = _edit(CODE, "show", "elif n > 5", "if n > 6")
    assert _diff(CODE, new) == [("    elif n > 5:", "    elif n > 6:")]
    new, _ = _edit(CODE, "show", "elif n > 5", "n >= 7:")
    assert _diff(CODE, new) == [("    elif n > 5:", "    elif n >= 7:")]
    new, _ = _edit(CODE, "show", "if n > 10", "elif n > 11")
    assert _diff(CODE, new) == [("    if n > 10:  # большое", "    if n > 11:  # большое")]


def test_loop_headers_keep_body_and_comment():
    new, _ = _edit(CODE, "show", "for i in range(n)", "for j in range(2)")
    assert _diff(CODE, new) == [("    for i in range(n):  # цикл", "    for j in range(2):  # цикл")]
    new, _ = _edit(CODE, "show", "while n > 0", "while n > 1")
    assert _diff(CODE, new) == [("    while n > 0:  # пока", "    while n > 1:  # пока")]


def test_synthetic_top_level_statement():
    new, changed = _edit(CODE, "<top>", 'print("готово")', 'print("конец")')
    assert _diff(CODE, new) == [('    print("готово")', '    print("конец")')]
    assert changed


def test_multiline_label_gets_statement_indent():
    code = "def f():\n    x = 1\n    return x\n"
    new, _ = _edit(code, "f", "x = 1", "x = g(\n    1)")
    assert new == "def f():\n    x = g(\n        1)\n    return x\n"


def test_empty_simple_label_becomes_pass_and_empty_header_is_ignored():
    new, _ = _edit(CODE, "show", "n -= 1", "  ")
    assert _diff(CODE, new) == [("        n -= 1", "        pass")]
    new, changed = _edit(CODE, "show", "while n > 0", "")
    assert new == CODE and changed == []


def test_except_edits():
    new, _ = _edit(CODE, "show", "except ValueError as e", "except KeyError as e")
    assert _diff(CODE, new) == [("    except ValueError as e:", "    except KeyError as e:")]
    new, _ = _edit(CODE, "show", "except", "except Exception")
    assert _diff(CODE, new) == [("    except:", "    except Exception:")]


def test_with_and_case_headers():
    code = ("def f(p, c):\n    with open(p) as fh:  # файл\n        data = fh.read()\n"
            "    match c:\n        case 1 | 2 if data:\n            pass\n        case _:\n            pass\n")
    new, _ = _edit(code, "f", "with open(p) as fh", "with open(p, encoding='utf-8') as fh")
    assert _diff(code, new) == [("    with open(p) as fh:  # файл", "    with open(p, encoding='utf-8') as fh:  # файл")]
    new, _ = _edit(code, "f", "case 1 | 2 if data", "case 3")
    assert _diff(code, new) == [("        case 1 | 2 if data:", "        case 3:")]
    new, _ = _edit(code, "f", "match c", "match c + 1")
    assert _diff(code, new) == [("    match c:", "    match c + 1:")]


def test_try_and_finally_are_not_editable():
    code = "def f():\n    try:\n        x = 1\n    finally:\n        x = 2\n"
    m = _method(code, "f")
    nodes, _, _ = build_cfg_with_map(m)
    edits = {n.id: "x = 3" for n in nodes if n.label in ("try", "finally")}
    assert edits and apply_edits(code, m, edits) == (code, [])


def test_several_edits_on_one_line_bottom_up():
    code = "def f():\n    a = 1; b = 2\n    return a + b\n"
    m = _method(code, "f")
    new, changed = apply_edits(code, m, {_node(m, "a = 1"): "a = 10", _node(m, "b = 2"): "b = 20"})
    assert new == "def f():\n    a = 10; b = 20\n    return a + b\n" and len(changed) == 2


def test_crlf_and_docstring_kept():
    code = 'def f():\r\n    """Док."""\r\n    x = 1\r\n    return x\r\n'
    new, _ = _edit(code, "f", "x = 1", "x = 2")
    assert new == code.replace("x = 1", "x = 2")


def test_api_generate_python_edit_and_syntax_error():
    assert client.post("/api/parse", json={"code": CODE, "language": "python"}).status_code == 200
    g = client.get("/api/graph", params={"type": "cfg", "method": "Module.show"}).json()
    ret = next(n for n in g["nodes"] if n["label"] == "return msg")
    ret["label"] = "return msg * 2"
    r = client.post("/api/generate", json={"graph": {"method": "Module.show", "nodes": g["nodes"]},
                                           "language": "python"})
    assert r.status_code == 200
    assert _diff(CODE, r.json()["code"]) == [("    return msg  # итог", "    return msg * 2  # итог")]
    assert r.json()["changedNodes"] == [ret["id"]]

    ret["label"] = "return (((("
    r = client.post("/api/generate", json={"graph": {"method": "Module.show", "nodes": g["nodes"]},
                                           "language": "python"})
    assert r.status_code == 422
    assert "некорректный Python-код" in r.json()["detail"]

"""Unit tests for modern Python language support in Java & Python Blueprints."""

import pytest
from core.py_parser import parse_python
from core.cfg_builder import build_cfg
from core.call_graph import build_call_graph
from core.class_diagram import build_class_diagram
from core.bigo_analyzer import analyze_ast
from core.defect_detector import detect_defects
from core.runner import run_code, check_compiles, is_python_code
from core.comparator import compare_code
from core.code_generator import regenerate_method, splice_method
from core.decomposer import decompose


def test_is_python_code():
    assert is_python_code("def foo():\n    pass") is True
    assert is_python_code("import math\nprint(math.pi)") is True
    assert is_python_code("class Foo:\n    pass") is True
    assert is_python_code("public class Demo { public static void main(String[] args) {} }") is False
    assert is_python_code("import java.util.*;") is False


def test_parse_python_basic():
    code = """import math

class Calculator:
    def __init__(self):
        self.history = []

    def add(self, a: float, b: float) -> float:
        res = a + b
        self.history.append(res)
        return res

def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)
"""
    res = parse_python(code)
    assert not res["errors"]
    ast_dict = res["ast"]
    assert ast_dict["language"] == "python"
    cls_names = [c["name"] for c in ast_dict["classes"]]
    assert "Calculator" in cls_names
    assert "Module" in cls_names

    calc = next(c for c in ast_dict["classes"] if c["name"] == "Calculator")
    assert any(m["name"] == "add" for m in calc["methods"])
    assert any(f["name"] == "history" for f in calc["fields"])

    mod = next(c for c in ast_dict["classes"] if c["name"] == "Module")
    assert any(m["name"] == "factorial" for m in mod["methods"])


def test_python_cfg():
    code = """def calc(items):
    total = 0
    for x in items:
        if x > 0:
            total += x
    return total
"""
    res = parse_python(code)
    method = res["ast"]["classes"][0]["methods"][0]
    nodes, edges = build_cfg(method)
    assert any(n.type == "start" for n in nodes)
    assert any(n.type == "end" for n in nodes)
    assert any(n.type == "loop" for n in nodes)
    assert any(n.type == "condition" for n in nodes)
    assert any(n.type == "return" for n in nodes)
    assert any(e.type == "back" for e in edges)


def test_python_call_graph():
    code = """class Engine:
    def step(self):
        self.tick()

    def tick(self):
        pass
"""
    res = parse_python(code)
    nodes, edges = build_call_graph(res["ast"])
    assert any(n.id == "Engine.step" for n in nodes)
    assert any(n.id == "Engine.tick" for n in nodes)
    assert any(e.source == "Engine.step" and e.target == "Engine.tick" for e in edges)


def test_python_class_diagram():
    code = """class Animal:
    pass

class Dog(Animal):
    def bark(self):
        pass
"""
    res = parse_python(code)
    nodes, edges = build_class_diagram(res["ast"])
    node_ids = {n.id for n in nodes}
    assert "Animal" in node_ids
    assert "Dog" in node_ids
    assert any(e.source == "Dog" and e.target == "Animal" and e.type == "extends" for e in edges)


def test_python_bigo_and_defects():
    code = """def pairs(items):
    total = 0
    for a in items:
        for b in items:
            if a < b:
                total += a * b
    return total
"""
    res = parse_python(code)
    bigo = analyze_ast(res["ast"])
    assert "O(n²)" in bigo.values() or any("n²" in v for v in bigo.values())
    defects = detect_defects(res["ast"], code, bigo)
    assert len(defects) >= 1
    assert any("глубина 2" in d.message or "O(n²)" in d.big_o for d in defects)


def test_run_python():
    code = """name = input()
print(f'Hello {name}!')
"""
    resp = run_code(code, stdin_input="World\n", language="python")
    assert resp.exit_code == 0
    assert "Hello World!" in resp.stdout


def test_run_python_syntax_error():
    code = "def bad_syntax(:\n    pass"
    resp = run_code(code, language="python")
    assert resp.exit_code != 0
    assert len(resp.compile_errors) > 0


def test_compare_python():
    original = "def solve():\n    print('ans =', 42)\nsolve()\n"
    modified = "def solve():\n    print('ans =', 40 + 2)\nsolve()\n"
    res = compare_code(original, modified, language="python")
    assert res.behavior_preserved is True
    assert not res.diff


def test_decompose_python():
    code = """def parse_items(raw):
    return [int(x) for x in raw.split(',')]

def parse_lines(text):
    return text.splitlines()

def calc_sum(items):
    return sum(items)

def calc_avg(items):
    return sum(items) / len(items) if items else 0

def main():
    xs = parse_items('1,2,3')
    print('Sum:', calc_sum(xs))

if __name__ == '__main__':
    main()
"""
    res = parse_python(code)
    decomp = decompose(code, res["ast"])
    assert len(decomp.files) >= 2
    fnames = [f.name for f in decomp.files]
    assert "main.py" in fnames
    assert any(fn.endswith(".py") for fn in fnames)


def test_python_code_generator_edit():
    code = """def foo(x):
    total = 0
    return total
"""
    res = parse_python(code)
    method = res["ast"]["classes"][0]["methods"][0]
    edits = {"n2": "total = 100"}  # edit first statement
    body, changed = regenerate_method(method, edits, language="python")
    assert "total = 100" in "\n".join(body)
    new_code = splice_method(code, method, body, language="python")
    assert "total = 100" in new_code

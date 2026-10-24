"""Big O for Python: comprehensions, builtins, membership by known collection type, qualified keys only."""

import textwrap

import pytest

from core.bigo_analyzer import analyze_ast, find_loops, loop_depth
from core.py_parser import parse_python


def bigo(code: str) -> dict[str, str]:
    res = parse_python(textwrap.dedent(code))
    assert not res["errors"], res["errors"]
    return analyze_ast(res["ast"])


def f_of(body: str, params: str = "xs, ys") -> str:
    code = f"def f({params}):\n" + textwrap.indent(textwrap.dedent(body), "    ")
    return bigo(code)["Module.f"]


@pytest.mark.parametrize("body, expected", [
    ("return sorted(xs)\n", "O(n log n)"),
    ("return [x * 2 for x in xs]\n", "O(n)"),
    ("return sum(xs)\n", "O(n)"),
    ("return len(xs)\n", "O(1)"),
    ("return [y for x in xs for y in xs]\n", "O(n²)"),
    ("return {x: 1 for x in xs}\n", "O(n)"),
    ("return any(x > 0 for x in xs)\n", "O(n)"),
    ("return max(xs)\n", "O(n)"),
    ("return max(1, 2)\n", "O(1)"),
    ("return list(range(10))\n", "O(1)"),
    ("return ', '.join(xs)\n", "O(n)"),
    ("return [sorted(xs) for x in xs]\n", "O(n² log n)"),
    ("for x in xs:\n    xs.sort()\n", "O(n² log n)"),
    ("for x in sorted(xs):\n    pass\n", "O(n log n)"),
    ("for i in range(10):\n    pass\n", "O(1)"),
    ("total = 0\nfor x in xs:\n    total += x\nreturn total\n", "O(n)"),
    ("n = len(xs)\nwhile n > 1:\n    n //= 2\n", "O(log n)"),
])
def test_builtins_and_comprehensions(body, expected):
    assert f_of(body) == expected


def test_membership_depends_on_known_type():
    loop = "for x in xs:\n    if x in ys:\n        pass\n"
    assert f_of(loop, "xs: list, ys: list") == "O(n²)"
    assert f_of(loop, "xs: list, ys: set") == "O(n)"
    assert f_of(loop, "xs, ys") == "O(n)"                     # unknown type: O(1) lookup
    assert f_of(loop, "xs, ys: List[int]") == "O(n²)"
    assert f_of(loop, "xs, ys: Dict[str, int]") == "O(n)"
    assert f_of(loop, "xs, ys: Optional[list] = None") == "O(n²)"
    assert f_of("ys = [1, 2, 3]\n" + loop) == "O(n²)"
    assert f_of("ys = set(xs)\n" + loop) == "O(n)"
    assert f_of("ys = {}\n" + loop) == "O(n)"
    assert f_of("ys: list = []\n" + loop) == "O(n²)"
    assert f_of("for x in xs:\n    if x not in 'abc':\n        pass\n") == "O(n)"   # literal of fixed size... still a str
    assert f_of("for x in xs:\n    if x not in [a for a in xs]:\n        pass\n") == "O(n²)"


def test_for_target_is_not_membership():
    # `for x in ys` with ys a list is a loop, not an `in` test inside one
    assert f_of("for x in ys:\n    pass\n", "xs, ys: list") == "O(n)"


def test_loop_else_is_sequential():
    body = "for x in xs:\n    pass\nelse:\n    for y in xs:\n        pass\n"
    assert f_of(body) == "O(n)"
    res = parse_python("def f(xs):\n" + textwrap.indent(body, "    "))
    method = res["ast"]["classes"][0]["methods"][0]
    assert loop_depth(method["body"]) == 1
    assert [d for _, d in find_loops(method["body"])] == [1, 1]
    assert f_of("while xs:\n    xs.pop()\nelse:\n    for y in ys:\n        pass\n") == "O(n)"


def test_with_match_try_are_not_loops():
    assert f_of("with open(p) as fh:\n    for x in xs:\n        pass\n", "xs, p") == "O(n)"
    assert f_of("match xs:\n    case [a, *rest]:\n        for x in rest:\n            pass\n    case _:\n        pass\n") == "O(n)"
    assert f_of("try:\n    for x in xs:\n        pass\nexcept ValueError:\n    pass\nelse:\n    for y in ys:\n        pass\nfinally:\n    pass\n") == "O(n)"


def test_nested_def_body_does_not_count_in_outer():
    code = """\
    def outer(xs):
        def inner(a):
            return sorted(a)
        return len(xs)
    """
    b = bigo(code)
    assert b["Module.outer"] == "O(1)"
    assert b["Module.outer.inner"] == "O(n log n)"


def test_nested_def_call_resolves_to_inner():
    code = """\
    def outer(xs):
        def inner(a):
            return sorted(a)
        return inner(xs)
    """
    assert bigo(code)["Module.outer"] == "O(n log n)"


def test_calls_between_functions_and_methods():
    code = """\
    def helper(xs):
        return [x for x in xs if x in xs]

    class Box:
        def __init__(self, items):
            self.items = sorted(items)

        def scan(self, xs):
            for x in xs:
                self.check(x)

        def check(self, x):
            return helper(self.items)

    def make(xs):
        return Box(xs)

    print(make([1, 2]))
    """
    b = bigo(code)
    assert b["Module.helper"] == "O(n)"                # membership in an unknown name: O(1)
    assert b["Box.check"] == "O(n)"
    assert b["Box.scan"] == "O(n²)"
    assert b["Module.make"] == "O(n log n)"


def test_recursion():
    code = """\
    def fact(n):
        if n <= 1:
            return 1
        return n * fact(n - 1)

    def fib(n):
        if n < 2:
            return n
        return fib(n - 1) + fib(n - 2)

    def search(xs, lo, hi, t):
        if lo > hi:
            return -1
        mid = (lo + hi) // 2
        if xs[mid] < t:
            lo = mid + 1
        else:
            hi = mid - 1
        return search(xs, lo, hi, t)

    class T:
        def walk(self, n):
            if n == 0:
                return 0
            return self.walk(n - 1)
    """
    b = bigo(code)
    assert b["Module.fact"] == "O(n)"
    assert b["Module.fib"] == "O(2^n)"
    assert b["Module.search"] == "O(log n)"
    assert b["T.walk"] == "O(n)"


def test_only_qualified_keys():
    code = """\
    def f(xs):
        return sorted(xs)

    class A:
        def g(self):
            return 1

    f([1])
    """
    b = bigo(code)
    assert b and all(k.startswith(("Module.", "A.")) for k in b), b
    assert "f" not in b and "g" not in b


def test_module_globals_known_to_functions():
    code = """\
    WORDS = ["a", "b"]

    def f(xs):
        for x in xs:
            if x in WORDS:
                pass

    f(["a"])
    """
    assert bigo(code)["Module.f"] == "O(n²)"


def test_unparsable_text_falls_back_to_regex():
    # a statement text the parser could not hand over as Python still gets the regex estimate
    from core.bigo_analyzer import _Analyzer
    cls = {"name": "Module", "methods": [], "fields": []}
    method = {"name": "f", "parameters": [], "language": "python", "body": [
        {"type": "StatementExpression", "expression": "xs.sort( ??"},
    ]}
    cls["methods"].append(method)
    assert _Analyzer({"classes": [cls]}).cost(cls, method) == (1, 1)

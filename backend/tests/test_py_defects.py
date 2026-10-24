"""Python defect rules (stage 7, task 7) and their static tips."""

import os
import textwrap

import pytest

from ai.static_tips import DEFAULT, tip_for
from core.bigo_analyzer import analyze_ast
from core.defect_detector import detect_defects
from core.py_parser import parse_python

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "test_monoliths")


def _defects(code: str):
    code = textwrap.dedent(code)
    ast = parse_python(code)["ast"]
    return detect_defects(ast, code, analyze_ast(ast))


def _with(defects, key: str):
    return [d for d in defects if key in d.message.lower()]


def _monolith(name: str):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        code = f.read()
    ast = parse_python(code)["ast"]
    return detect_defects(ast, code, analyze_ast(ast))


# 1. string concatenation in a loop ---------------------------------------------------------------

def test_string_concat_augassign():
    ds = _with(_defects("""
        def f(xs):
            s = ""
            for x in xs:
                s += str(x)
            return s
    """), "конкатенация строки")
    assert len(ds) == 1
    d = ds[0]
    assert d.severity == "warning" and d.big_o == "O(n²)" and d.line_start == 5
    assert d.method == "Module.f"
    assert "join" in d.recommendation
    assert d.node_id


def test_string_concat_plain_assign():
    ds = _with(_defects("""
        def f(xs):
            s = str()
            for x in xs:
                s = s + x
            return s
    """), "конкатенация строки")
    assert len(ds) == 1


def test_number_augassign_is_not_concat():
    assert not _with(_defects("""
        def f(xs):
            s = 0
            for x in xs:
                s += 1
            return s
    """), "конкатенация строки")


def test_concat_outside_loop_is_fine():
    assert not _with(_defects("""
        def f(a):
            s = ""
            s += a
            return s
    """), "конкатенация строки")


# 2. membership in a list inside a loop -------------------------------------------------------------

def test_membership_in_list_in_loop():
    ds = _with(_defects("""
        def f(xs):
            seen = []
            for x in xs:
                if x not in seen:
                    seen.append(x)
            return seen
    """), "поиск в списке")
    assert len(ds) == 1
    assert ds[0].big_o == "O(n²)" and ds[0].severity == "warning" and "set" in ds[0].recommendation
    assert ds[0].line_start == 5


def test_membership_in_set_in_loop_is_fine():
    assert not _with(_defects("""
        def f(xs):
            st = set(xs)
            out = 0
            for x in xs:
                if x in st:
                    out += 1
            return out
    """), "поиск в списке")


def test_membership_outside_loop_is_fine():
    assert not _with(_defects("""
        def f(x, xs: list):
            return x in xs
    """), "поиск в списке")


def test_membership_in_comprehension():
    ds = _with(_defects("""
        def f(xs, ys: list):
            return [x for x in xs if x in ys]
    """), "поиск в списке")
    assert len(ds) == 1


# 3. nested loop over the same collection -----------------------------------------------------------

def test_nested_same_collection_python_text():
    ds = _with(_defects("""
        def f(items):
            n = 0
            for a in items:
                for b in items:
                    n += 1
            return n
    """), "повторная обработка пар")
    assert len(ds) == 1
    rec = ds[0].recommendation
    assert "HashMap" not in rec and ("dict" in rec or "set" in rec) and "itertools.combinations" in rec


def test_loop_else_is_not_nested():
    ds = _defects("""
        def f(xs):
            for x in xs:
                pass
            else:
                for y in xs:
                    print(y)
    """)
    assert not _with(ds, "вложенн") and not _with(ds, "повторная обработка")


# 4. swallowed / general except ---------------------------------------------------------------------

@pytest.mark.parametrize("head", ["except:", "except Exception:", "except BaseException:", "except Exception as e:"])
def test_swallowed_exception(head):
    ds = _with(_defects(f"""
        def f(p):
            try:
                return int(p)
            {head}
                pass
            return 0
    """), "проглатывается")
    assert len(ds) == 1 and ds[0].severity == "error"


def test_ellipsis_body_is_swallowed():
    assert _with(_defects("""
        def f(p):
            try:
                return int(p)
            except Exception:
                ...
    """), "проглатывается")


def test_specific_except_with_handling_is_fine():
    ds = _defects("""
        def f(p):
            try:
                return int(p)
            except ValueError as e:
                log(e)
            return 0
    """)
    assert not _with(ds, "проглатывается") and not _with(ds, "общий except")


def test_bare_except_warning():
    ds = _with(_defects("""
        def f(p):
            try:
                return int(p)
            except:
                return 0
    """), "общий except")
    assert len(ds) == 1 and ds[0].severity == "warning" and ds[0].line_start == 5


# 5. mutable default argument -----------------------------------------------------------------------

@pytest.mark.parametrize("default", ["[]", "{}", "set()", "list()", "dict()"])
def test_mutable_default(default):
    ds = _with(_defects(f"""
        def f(a={default}):
            return a
    """), "изменяемое значение по умолчанию")
    assert len(ds) == 1 and ds[0].severity == "warning" and "None" in ds[0].recommendation
    assert ds[0].method == "Module.f"


def test_none_default_is_fine():
    assert not _with(_defects("""
        def f(a=None, b=0, c=()):
            return a
    """), "изменяемое значение по умолчанию")


def test_mutable_default_in_method_and_nested_def():
    ds = _with(_defects("""
        class C:
            def m(self, h=[]):
                def inner(x={}):
                    return x
                return inner()
    """), "изменяемое значение по умолчанию")
    assert sorted(d.method for d in ds) == ["C.m", "C.m.inner"]


# 6. range(len(x)) ----------------------------------------------------------------------------------

def test_range_len():
    ds = _with(_defects("""
        def f(xs):
            for i in range(len(xs)):
                print(xs[i])
    """), "перебор индексов")
    assert len(ds) == 1 and ds[0].severity == "hint" and "enumerate" in ds[0].recommendation


def test_enumerate_is_fine():
    assert not _with(_defects("""
        def f(xs):
            for i, x in enumerate(xs):
                print(i, x)
    """), "перебор индексов")


# unused imports ------------------------------------------------------------------------------------

def test_unused_from_import():
    ds = _with(_defects("""
        from os import path
        import numpy as np
        import sys

        print(np.zeros(3), sys.argv)
    """), "неиспользуемый импорт")
    assert len(ds) == 1 and "path" in ds[0].message and ds[0].line_start == 2


def test_unused_alias_import():
    ds = _with(_defects("""
        import numpy as np
        print(numpy)
    """), "неиспользуемый импорт")
    assert len(ds) == 1


# nested defs ---------------------------------------------------------------------------------------

def test_nested_def_not_reported_twice():
    ds = _with(_defects("""
        def outer(xs):
            def inner():
                for i in range(len(xs)):
                    print(i)
            inner()
    """), "перебор индексов")
    assert [d.method for d in ds] == ["Module.outer.inner"]


# examples ------------------------------------------------------------------------------------------

def test_logger_example():
    ds = _monolith("logger.py")
    assert _with(ds, "конкатенация строки")
    assert _with(ds, "проглатывается")
    assert _with(ds, "общий except")
    assert _with(ds, "неиспользуемый импорт")


def test_store_example():
    ds = _monolith("store.py")
    assert _with(ds, "изменяемое значение по умолчанию")
    assert _with(ds, "поиск в списке")
    assert _with(ds, "повторная обработка пар")


def test_exponential_hint_only_for_the_recursive_function():
    ds = _with(_monolith("calculator.py"), "вызывает себя дважды")
    assert [d.method for d in ds] == ["Module.fib"]


def test_analyzer_example():
    ds = _monolith("analyzer.py")
    assert _with(ds, "перебор индексов")
    assert _with(ds, "повторная обработка пар")
    assert _with(ds, "поиск в списке")


@pytest.mark.parametrize("name", ["logger.py", "store.py", "analyzer.py", "calculator.py"])
def test_python_texts_are_pythonic(name):
    for d in _monolith(name):
        text = d.message + " " + d.recommendation
        for word in ("HashMap", "IOException", "catch"):
            assert word not in text, (word, text)


@pytest.mark.parametrize("name", ["logger.py", "store.py", "analyzer.py", "calculator.py"])
def test_every_python_defect_has_a_python_tip(name):
    for d in _monolith(name):
        text, _ = tip_for(d.message, d.recommendation, language="python")
        assert text != DEFAULT[0] and text != d.recommendation, d.message
        assert "catch" not in text and "HashMap" not in text



# fix round -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("lit", ["(1, 2, 3)", '["a", "b"]', "{1, 2}"])
def test_membership_in_constant_literal_is_fine(lit):
    code = f"""
        def f(xs):
            n = 0
            for x in xs:
                if x in {lit}:
                    n += 1
            return n
    """
    assert not _with(_defects(code), "поиск в списке")
    ast = parse_python(textwrap.dedent(code))["ast"]
    assert analyze_ast(ast)["Module.f"] == "O(n)"


def test_membership_in_literal_of_names_is_still_seq():
    code = """
        def f(xs, a, b):
            n = 0
            for x in xs:
                if x in [a, b, *xs]:
                    n += 1
            return n
    """
    assert _with(_defects(code), "поиск в списке")


def test_mutable_default_points_to_method_node():
    d = _with(_defects("""
        def f(a=[]):
            return a
    """), "изменяемое значение по умолчанию")[0]
    assert d.node_id


def test_python_duplicates_reported():
    ds = _with(_defects("""
        def f(xs):
            total = 0
            for x in xs:
                total += x
            return total

        def g(xs):
            total = 0
            for x in xs:
                total += x
            return total
    """), "дублирование")
    assert len(ds) == 1 and ds[0].method == "Module.g"


def test_tuple_except_with_generic_type_is_swallowed():
    assert _with(_defects("""
        def f(p):
            try:
                return int(p)
            except (ValueError, Exception):
                pass
            return 0
    """), "проглатывается")


def test_tuple_except_specific_is_fine():
    assert not _with(_defects("""
        def f(p):
            try:
                return int(p)
            except (ValueError, KeyError):
                pass
            return 0
    """), "проглатывается")


def test_import_listed_in_all_is_used():
    assert not _with(_defects("""
        from os import path
        __all__ = ["path"]
    """), "неиспользуемый импорт")

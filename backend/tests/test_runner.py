import pytest

from core.comparator import compare_code
from core.runner import detect_main_class, run_java

HELLO = 'public class Hello { public static void main(String[] a){ System.out.println("hi " + (1+2)); } }'


def test_run_ok():
    r = run_java(HELLO)
    assert r.exit_code == 0 and r.stdout.strip() == "hi 3"


def test_compile_error_has_line():
    r = run_java("public class B { void f(){ int a = ; } public static void main(String[] x){} }")
    assert r.exit_code != 0 and r.compile_errors and r.compile_errors[0]["line"] == 1


def test_timeout():
    r = run_java("public class T { public static void main(String[] a){ while(true){} } }", timeout_sec=1)
    assert r.exit_code == 124


def test_detect_main_class(read_java):
    assert detect_main_class(read_java("Logger")) == "Logger"


def test_compare_same_and_different():
    changed = HELLO.replace('"hi "', '"yo "')
    assert compare_code(HELLO, HELLO).behavior_preserved
    cmp = compare_code(HELLO, changed)
    assert not cmp.behavior_preserved and "-hi 3" in cmp.diff


@pytest.mark.parametrize("name", ["Analyzer", "Calculator", "Logger", "Store"])
def test_monoliths_run(read_java, name):
    assert run_java(read_java(name)).exit_code == 0


@pytest.mark.parametrize("bad", ["../Evil", "A;rm -rf /", "a b"])
def test_rejects_bad_main_class(bad):
    r = run_java(HELLO, main_class=bad)
    assert r.exit_code == 2 and "Недопустимое" in r.stderr

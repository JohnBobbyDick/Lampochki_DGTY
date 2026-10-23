from core.bigo_analyzer import analyze_ast
from core.defect_detector import detect_defects
from core.parser import parse_java


def analyze(code):
    ast = parse_java(code)["ast"]
    return ast, analyze_ast(ast)


def test_constant_linear_quadratic_cubic():
    code = """class A {
      void c(){ int x = 1; }
      void l(int[] a){ for (int v : a) { x(v); } }
      void q(int[] a){ for (int v : a) { for (int w : a) { x(v+w); } } }
      void k(int[] a){ for (int v : a) { for (int w : a) { for (int z : a) { x(z); } } } }
      void x(int i){}
    }"""
    _, b = analyze(code)
    assert b["A.c"] == "O(1)"
    assert b["A.l"] == "O(n)"
    assert b["A.q"] == "O(n²)"
    assert b["A.k"] == "O(n³)"


def test_recursion_is_flagged(read_java):
    _, b = analyze(read_java("Calculator"))
    assert "рекурсия" in b["Calculator.factorial"]


def test_log_loop():
    _, b = analyze("class A { void f(int n){ while (n > 1) { n /= 2; } } }")
    assert b["A.f"] == "O(log n)"


def test_analyzer_monolith_has_quadratic_defect(read_java):
    code = read_java("Analyzer")
    ast, b = analyze(code)
    defects = detect_defects(ast, code, b)
    pair = [d for d in defects if d.big_o == "O(n²)" and d.method == "Analyzer.mergeItems"]
    assert pair and "items" in pair[0].message
    assert any("Пустой catch" in d.message for d in defects)


def test_generic_catch_and_unused_var():
    code = "import java.util.List; class A { void f(){ int unused = 1; try { g(); } catch (Exception e) { g(); } } void g(){} }"
    ast, b = analyze(code)
    msgs = " | ".join(d.message for d in detect_defects(ast, code, b))
    assert "Общий catch" in msgs and "unused" in msgs and "Неиспользуемый импорт" in msgs

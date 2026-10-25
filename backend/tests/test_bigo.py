import pytest

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


def test_recursion_is_estimated(read_java):
    _, b = analyze(read_java("Calculator"))
    assert b["Calculator.factorial"] == "O(n)"          # f(n - 1): one call per level
    assert b["Calculator.fibonacci"] == "O(2^n)"        # f(n - 1) + f(n - 2)
    assert b["Calculator.gcd"] == "O(log n)"            # Euclid: b = a % b
    assert "рекурсия" in b["Calculator.evaluate"]       # recursive descent: not classified, stays honest
    assert b["Calculator.main"] == "O(?)"               # depends on evaluate, but is not recursive itself


def test_exponential_recursion_is_a_defect(read_java):
    code = read_java("Calculator")
    ast, b = analyze(code)
    exp = [d for d in detect_defects(ast, code, b) if d.method == "Calculator.fibonacci"]
    assert exp and exp[0].big_o == "O(2^n)" and exp[0].severity == "warning"


@pytest.mark.parametrize("name, code, expected", [
    ("constant-bound loop", "class A { void f(){ for (int i = 0; i < 10; i++) { g(); } } void g(){} }", "O(1)"),
    ("List.contains in a loop", "import java.util.*; class A { int f(List<Integer> a, List<Integer> b){ int c=0; "
     "for (Integer x : a) { if (b.contains(x)) c++; } return c; } }", "O(n²)"),
    ("HashSet.contains in a loop", "import java.util.*; class A { int f(List<Integer> a, Set<Integer> b){ int c=0; "
     "for (Integer x : a) { if (b.contains(x)) c++; } return c; } }", "O(n)"),
    ("calls a quadratic method", "import java.util.*; class A { int q(List<Integer> a){ int t=0; for (Integer x : a) "
     "for (Integer y : a) t+=x*y; return t; } int f(List<Integer> a){ return q(a); } }", "O(n²)"),
    ("loop calls a linear method", "class A { int l(int[] a){ int s=0; for (int v : a) s+=v; return s; } "
     "int f(int[] a){ int t=0; for (int v : a) t += l(a); return t; } }", "O(n²)"),
    ("iterative binary search", "class A { int f(int[] a, int k){ int lo=0, hi=a.length-1; while (lo <= hi) { "
     "int mid = (lo + hi) / 2; if (a[mid] < k) lo = mid + 1; else if (a[mid] > k) hi = mid - 1; else return mid; } "
     "return -1; } }", "O(log n)"),
    ("linear outer, halving inner", "class A { void f(int n){ for (int i = 0; i < n; i++) { int j = n; "
     "while (j > 1) { j /= 2; } } } }", "O(n log n)"),
    ("doubling for loop", "class A { void f(int n){ for (int i = 1; i < n; i *= 2) { g(); } } void g(){} }", "O(log n)"),
    ("sort inside a loop", "import java.util.*; class A { void f(List<List<Integer>> xs){ for (List<Integer> x : xs) "
     "{ Collections.sort(x); } } }", "O(n² log n)"),
    ("sort once", "import java.util.*; class A { void f(List<Integer> xs){ Collections.sort(xs); } }", "O(n log n)"),
    ("merge sort", "class A { void s(int[] a, int l, int r){ if (l >= r) return; int m = (l + r) / 2; s(a, l, m); "
     "s(a, m + 1, r); int[] t = new int[r - l + 1]; for (int i = l; i <= r; i++) { t[i - l] = a[i]; } } }", "O(n log n)"),
    ("heap sort", "class A { static void f(int[] arr){ int n = arr.length; for (int i = n / 2 - 1; i >= 0; i--) "
     "{ h(arr, n, i); } for (int i = n - 1; i > 0; i--) { int t = arr[0]; arr[0] = arr[i]; arr[i] = t; h(arr, i, 0); } } "
     "static void h(int[] arr, int n, int i){ int largest = i; int left = 2 * i + 1; int right = 2 * i + 2; "
     "if (left < n && arr[left] > arr[largest]) { largest = left; } if (right < n && arr[right] > arr[largest]) "
     "{ largest = right; } if (largest != i) { int t = arr[i]; arr[i] = arr[largest]; arr[largest] = t; "
     "h(arr, n, largest); } } }", "O(n log n)"),
    ("overload is not recursion", "class A { int f(int x){ return f(x, 1); } int f(int x, int y){ return x + y; } }", "O(1)"),
    ("stream pipeline with a lambda", "import java.util.*; class A { long f(List<Integer> a){ "
     "return a.stream().filter(x -> x > 0).count(); } }", "O(n)"),
    ("call through a field of a project class", "import java.util.*; class B { int q(List<Integer> a){ int t=0; "
     "for (Integer x : a) for (Integer y : a) t++; return t; } } class A { B b = new B(); "
     "int f(List<Integer> a){ return b.q(a); } }", "O(n²)"),
])
def test_complexity_cases(name, code, expected):
    _, b = analyze(code)
    method = "A.s" if "A.s" in b else "A.f"
    assert b[method] == expected, name


def test_unparenthesised_lambda_parameter_parses():
    ast, _ = analyze("import java.util.*; class A { void f(List<Integer> a){ a.forEach(x -> System.out.println(x)); } }")
    assert ast["classes"][0]["methods"][0]["name"] == "f"


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


# stream chains: structural Big O from the steps

def _stream_cost(body, params="List<Integer> xs, List<Integer> ys, List<List<Integer>> ls, int n"):
    code = f"import java.util.*; import java.util.stream.*; class A {{ Object f({params}){{ {body} }} }}"
    ast, b = analyze(code)
    return b["A.f"]


@pytest.mark.parametrize("name, body, expected", [
    ("map + collect", "List<Integer> r = xs.stream().map(x -> x * 2).collect(Collectors.toList()); return r;", "O(n)"),
    ("sorted", "List<Integer> r = xs.stream().sorted().collect(Collectors.toList()); return r;", "O(n log n)"),
    ("filter with List.contains", "return xs.stream().filter(x -> ys.contains(x)).collect(Collectors.toList());", "O(n²)"),
    ("flatMap", "return ls.stream().flatMap(l -> l.stream()).collect(Collectors.toList());", "O(n²)"),
    ("chain inside a loop", "long c = 0; for (Integer a : xs) { c += xs.stream().filter(x -> x > a).count(); } "
     "return c;", "O(n²)"),
    ("limit does not lower", "return xs.stream().limit(5).collect(Collectors.toList());", "O(n)"),
    ("IntStream.range", "int s = IntStream.range(0, n).sum(); return s;", "O(n)"),
    ("assignment target", "List<Integer> r; r = xs.stream().map(x -> x + 1).collect(Collectors.toList()); "
     "return r;", "O(n)"),
    ("sorted with comparator", "return xs.stream().sorted((a, b) -> a - b).findFirst();", "O(n log n)"),
    ("distinct / toSet", "return xs.stream().distinct().collect(Collectors.toSet());", "O(n)"),
    ("anyMatch with contains", "return xs.stream().anyMatch(x -> ys.contains(x));", "O(n²)"),
    ("unrecognised chain keeps the regex estimate", "return xs.stream().weird().count();", "O(n)"),
])
def test_stream_chain_cost(name, body, expected):
    assert _stream_cost(body) == expected, name


def test_stream_step_calls_a_project_method():
    code = ("import java.util.*; import java.util.stream.*; class A { "
            "int q(List<Integer> a){ int t=0; for (Integer x : a) t += x; return t; } "
            "Object f(List<Integer> xs){ return xs.stream().map(x -> q(xs)).collect(Collectors.toList()); } }")
    _, b = analyze(code)
    assert b["A.f"] == "O(n²)"


def test_stream_source_and_tail_costs_still_count():
    code = ("import java.util.*; import java.util.stream.*; class A { "
            "List<Integer> g(List<Integer> a){ for (Integer x : a) for (Integer y : a) {} return a; } "
            "Object f(List<Integer> xs){ return g(xs).stream().map(x -> x).count(); } }")
    _, b = analyze(code)
    assert b["A.f"] == "O(n²)"


def test_monolith_and_demo_estimates_unchanged(read_java):
    import json
    import re
    from pathlib import Path
    baseline = json.loads((Path(__file__).parent / "data" / "bigo_baseline.json").read_text(encoding="utf-8"))
    for name in ("Analyzer", "Calculator", "Logger", "Store"):
        assert analyze(read_java(name))[1] == baseline[name], name
    ts = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "project" / "examples.ts").read_text(encoding="utf-8")
    demo = re.search(r"export const DEMO = `(.*?)`", ts, re.S).group(1)
    assert analyze(demo)[1] == baseline["DEMO"]


def test_defects_carry_expected_effect(read_java):
    """The rule behind a defect tells what the fragment costs once its recommendation is applied."""
    for name, method, before in (("Analyzer", "Analyzer.mergeItems", "O(n²)"),
                                 ("Calculator", "Calculator.fibonacci", "O(2^n)")):
        code = read_java(name)
        ast, b = analyze(code)
        d = next(d for d in detect_defects(ast, code, b) if d.method == method)
        assert (d.big_o, d.big_o_after) == (before, "O(n)")


EXP_CALLER = """public class M {
    static long fib(int n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
    static long sumFib(int k) {
        long s = 0;
        for (int i = 0; i < k; i++) s += fib(i);
        return s;
    }
    public static void main(String[] a) { System.out.println(sumFib(20)); }
}"""


def test_exponential_recursion_reported_only_where_it_recurses():
    ast, bigo = analyze(EXP_CALLER)
    assert bigo["M.main"] == "O(2^n)"           # inherited from fib
    rec = [d.method for d in detect_defects(ast, EXP_CALLER, bigo) if "вызывает себя дважды" in d.message]
    assert rec == ["M.fib"]


TRIPLE = """public class T {
    static int triples(int[] a) {
        int c = 0;
        for (int i = 0; i < a.length; i++)
            for (int j = i + 1; j < a.length; j++)
                for (int k = j + 1; k < a.length; k++)
                    if (a[i] + a[j] + a[k] == 0) c++;
        return c;
    }
}"""


def test_loop_nest_reported_once_at_its_depth():
    ast, bigo = analyze(TRIPLE)
    nested = [d for d in detect_defects(ast, TRIPLE, bigo) if "Вложенн" in d.message]
    assert [(d.big_o, d.big_o_after, d.line_start) for d in nested] == [("O(n³)", "O(n²)", 6)]

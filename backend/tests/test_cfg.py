from core.cfg_builder import build_cfg
from core.parser import parse_java


def cfg_for(code, name):
    ast = parse_java(code)["ast"]
    m = next(m for c in ast["classes"] for m in c["methods"] if m["name"] == name)
    return build_cfg(m)


def types(edges):
    return {e.type for e in edges}


def test_if_else_edges():
    nodes, edges = cfg_for("class A { int f(int x){ if (x>0) { x=1; } else { x=2; } return x; } }", "f")
    assert {"true", "false"} <= types(edges)
    assert any(n.type == "condition" for n in nodes)
    assert all(e.source in {n.id for n in nodes} and e.target in {n.id for n in nodes} for e in edges)


def test_loop_back_edge():
    nodes, edges = cfg_for("class A { void f(){ for (int i=0;i<3;i++){ System.out.println(i);} } }", "f")
    loop = next(n for n in nodes if n.type == "loop")
    assert any(e.type == "back" and e.target == loop.id for e in edges)
    assert any(e.type == "false" and e.source == loop.id for e in edges)


def test_try_catch_exception_edge():
    nodes, edges = cfg_for(
        "class A { void f(){ try { g(); } catch (Exception e) { h(); } finally { k(); } } void g(){} void h(){} void k(){} }",
        "f",
    )
    assert "exception" in types(edges)
    assert {"try", "catch", "finally"} <= {n.type for n in nodes}


def test_switch_cases_and_break():
    nodes, edges = cfg_for(
        "class A { int f(int x){ switch(x){ case 1: return 1; case 2: x++; break; default: x--; } return x; } }", "f"
    )
    assert sum(1 for n in nodes if n.type == "case") == 3
    assert any(n.label == "break" for n in nodes)


def test_deterministic_ids():
    code = "class A { void f(){ if (true) { g(); } } void g(){} }"
    a, _ = cfg_for(code, "f")
    b, _ = cfg_for(code, "f")
    assert [n.id for n in a] == [n.id for n in b]

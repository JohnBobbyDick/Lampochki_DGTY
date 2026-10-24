from core.coverage.conditions import (
    has_logic, leaves, parse_condition, split_relation, ternary_conditions,
)
from core.source_map import tokenize


def toks(s):
    # javalang crashes on a numeric literal at the very end of input
    return tokenize(s + " ")


def text(toks_, c):
    return " ".join(t.value for t in toks_[c.a:c.b])


def parse(s):
    t = toks(s)
    return t, parse_condition(t, 0, len(t))


def test_or_and_not_tree():
    t, c = parse("i > 2 && !(n < 3) || i == 1")
    assert c.kind == "or" and len(c.children) == 2
    left, right = c.children
    assert left.kind == "and"
    assert left.children[0].kind == "leaf"
    n = left.children[1]
    assert n.kind == "not"
    assert n.children[0].kind == "paren"
    assert n.children[0].children[0].kind == "leaf"
    assert right.kind == "leaf"
    assert has_logic(c)
    assert [text(t, l) for l in leaves(c)] == ["i > 2", "n < 3", "i == 1"]


def test_simple_leaf_and_not():
    t, c = parse("list.isEmpty()")
    assert c.kind == "leaf" and not has_logic(c)
    t, c = parse("!list.isEmpty()")
    assert c.kind == "not" and c.children[0].kind == "leaf"
    t, c = parse("!a == b")
    assert c.kind == "leaf"


def test_paren_with_ternary_is_leaf():
    t, c = parse("(a ? b : c) && d")
    assert c.kind == "and"
    assert c.children[0].kind == "leaf"
    assert text(t, c.children[0]) == "( a ? b : c )"
    assert c.children[1].kind == "leaf"


def rel(s):
    t = toks(s)
    r = split_relation(t, 0, len(t))
    return None if r is None else (r[1], r[2] == len(t))


def test_split_relation():
    assert rel("a + b > c") == (">", True)
    assert rel("(int) x < y") == ("<", True)
    assert rel("Foo.<T>bar(x) > 0") is None
    assert rel("x instanceof Foo") is None
    assert rel("(y = f()) > 0") == (">", True)
    assert rel("a < b == c") is None
    assert rel("new ArrayList<String>()") is None


def cond_texts(s):
    t = toks(s)
    return [" ".join(x.value for x in t[a:b]) for a, b in ternary_conditions(t, 0, len(t))]


def test_ternary_conditions():
    assert cond_texts("int y = x > 0 ? 1 : 2;") == ["x > 0"]
    assert cond_texts("f(a, b ? 1 : c ? 2 : 3)") == ["b", "c"]
    assert cond_texts("List<? extends T> l = null;") == []
    assert cond_texts("r = v -> v ? 1 : 2;") == ["v"]


def test_loose_operators_make_single_leaf():
    for s in ("a ? b || c : d", "p || q ? r : s", "x = a || b"):
        t, c = parse(s)
        assert c.kind == "leaf" and not has_logic(c), s

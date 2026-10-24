import glob
import json
import os

from ai.static_tips import DEFAULT, tip_for
from core.defect_detector import detect_defects
from core.parser import parse_java

HEAD = "import java.util.*;\nimport java.util.stream.*;\nclass A {\n"


def _defects(body: str, params: str = "List<Integer> xs, List<Integer> out"):
    code = HEAD + f" int m({params}) {{\n" + body + "\n return 0;\n }\n}\n"
    r = parse_java(code)
    assert r["errors"] == []
    return detect_defects(r["ast"], code)


def _by(ds, key):
    return [d for d in ds if key in d.message]


# 1. stream over the same collection inside a loop over it -----------------
def test_stream_in_loop_same_collection():
    ds = _defects("for (Integer x : xs) {\n long c = xs.stream().filter(v -> v > x).count();\n}")
    r = _by(ds, "Повторный стрим")
    assert len(r) == 1
    d = r[0]
    assert d.severity == "warning" and d.big_o == "O(n²)" and d.line_start == 6
    assert "A.m" in d.message and d.node_id


def test_stream_in_index_loop_same_collection():
    ds = _defects("for (int i = 0; i < xs.size(); i++) {\n long c = xs.stream().count();\n}")
    assert len(_by(ds, "Повторный стрим")) == 1


def test_stream_in_loop_other_collection_ok():
    ds = _defects("for (Integer x : xs) {\n long c = out.stream().count();\n}")
    assert _by(ds, "Повторный стрим") == []


# 2. collect(...).size() -------------------------------------------------------
def test_collect_size():
    ds = _defects("int k = xs.stream().filter(v -> v > 0).collect(Collectors.toList()).size();")
    r = _by(ds, "count()")
    assert len(r) == 1 and r[0].severity == "hint" and r[0].line_start == 5 and "A.m" in r[0].message


def test_collect_without_size_ok():
    ds = _defects("List<Integer> k = xs.stream().collect(Collectors.toList());")
    assert _by(ds, "count()") == []


# 3. filter().findFirst().isPresent() -----------------------------------------
def test_find_first_is_present():
    ds = _defects("boolean b = xs.stream().filter(v -> v > 0).findFirst().isPresent();")
    r = _by(ds, "anyMatch")
    assert len(r) == 1 and r[0].severity == "hint" and r[0].line_start == 5 and "A.m" in r[0].message


def test_find_any_is_present():
    ds = _defects("boolean b = xs.stream().filter(v -> v > 0).findAny().isPresent();")
    assert len(_by(ds, "anyMatch")) == 1


def test_any_match_ok():
    ds = _defects("boolean b = xs.stream().anyMatch(v -> v > 0);")
    assert _by(ds, "anyMatch") == []


# 4. sorted().findFirst() -----------------------------------------------------
def test_sorted_find_first():
    ds = _defects("Optional<Integer> o = xs.stream().sorted().findFirst();")
    r = _by(ds, "min(")
    assert len(r) == 1 and r[0].severity == "warning" and r[0].big_o == "O(n log n)"
    assert r[0].line_start == 5 and "A.m" in r[0].message


def test_min_ok():
    ds = _defects("Optional<Integer> o = xs.stream().min(Comparator.naturalOrder());")
    assert _by(ds, "min(") == []


# 5. forEach mutating an outer collection -------------------------------------
def test_foreach_add_outer():
    ds = _defects("xs.stream().filter(v -> v > 0).forEach(v -> out.add(v));")
    r = _by(ds, "collect(")
    assert len(r) == 1 and r[0].severity == "hint" and r[0].line_start == 5 and "A.m" in r[0].message


def test_foreach_println_ok():
    ds = _defects("xs.stream().forEach(System.out::println);")
    assert _by(ds, "collect(") == []


def test_foreach_param_method_ok():
    ds = _defects("Stream.of(new ArrayList<Integer>()).forEach(l -> l.add(1));")
    assert _by(ds, "collect(") == []


# 6. loop -> stream ------------------------------------------------------------
def test_loop_if_add():
    ds = _defects("for (Integer x : xs) {\n if (x > 0) {\n out.add(x);\n }\n}")
    r = _by(ds, "Цикл можно заменить")
    assert len(r) == 1 and r[0].severity == "hint" and r[0].line_start == 5 and "A.m" in r[0].message
    assert r[0].node_id


def test_loop_plain_add():
    ds = _defects("for (Integer x : xs) out.add(x * 2);")
    assert len(_by(ds, "Цикл можно заменить")) == 1


def test_loop_two_statements_ok():
    ds = _defects("for (Integer x : xs) {\n out.add(x);\n out.add(x + 1);\n}")
    assert _by(ds, "Цикл можно заменить") == []


# tips ---------------------------------------------------------------------------
def test_tips_for_all_messages():
    ds = _defects(
        "for (Integer x : xs) {\n long c = xs.stream().count();\n}\n"
        "int k = xs.stream().collect(Collectors.toSet()).size();\n"
        "boolean b = xs.stream().filter(v -> v > 0).findFirst().isPresent();\n"
        "Optional<Integer> o = xs.stream().sorted().findFirst();\n"
        "xs.stream().forEach(v -> out.add(v));\n"
        "for (Integer x : xs) out.add(x);")
    keys = ["Повторный стрим", "count()", "anyMatch", "min(", "изменяет внешнюю", "Цикл можно заменить"]
    seen = set()
    for key in keys:
        r = _by(ds, key)
        assert r, key
        text, _ = tip_for(r[0].message, r[0].recommendation)
        assert text and text != DEFAULT[0], key
        seen.add(text)
    assert len(seen) == len(keys)


# existing defects unchanged ------------------------------------------------------
def test_monolith_defects_unchanged():
    base = json.load(open(os.path.join(os.path.dirname(__file__), "data", "monolith_defects.json")))
    root = os.path.join(os.path.dirname(__file__), "..", "..", "test_monoliths")
    for f in sorted(glob.glob(os.path.join(root, "*.java"))):
        code = open(f).read()
        got = [d.model_dump() for d in detect_defects(parse_java(code)["ast"], code)]
        got = json.loads(json.dumps(got, ensure_ascii=False))
        old = base[os.path.basename(f)]
        # every pre-existing defect is unchanged; the only additions are the new "loop -> stream" hints
        assert [d for d in got if d in old] == old, f
        assert all(d["message"].startswith("Цикл можно заменить") for d in got if d not in old), f

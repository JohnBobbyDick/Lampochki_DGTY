import asyncio

from ai import patcher

OLD_MERGE = """List<Item> result = new ArrayList<>();
for (Item a : items) {
    for (Item b : items) {
        if (a.getId().equals(b.getId()) && a != b) {
            a.setValue(a.getValue() + b.getValue());
        }
    }
    result.add(a);
}
return result;"""

NEW_MERGE = """List<Item> result = new ArrayList<>();
Map<String, Item> seen = new HashMap<>();
for (Item a : items) {
    Item first = seen.get(a.getId());
    if (first != null) {
        first.setValue(first.getValue() + a.getValue());
    } else {
        seen.put(a.getId(), a);
    }
    result.add(a);
}
return result;"""


def run(coro):
    return asyncio.run(coro)


def _merge_patch(read_java):
    code = read_java("Analyzer")
    return run(patcher.build_patch(code, OLD_MERGE, NEW_MERGE, ["java.util.HashMap"], 45))


def test_merge_items_quadratic_to_linear(read_java):
    p = _merge_patch(read_java)
    assert p["valid"], p["problems"]
    assert p["bigo_before"]["Analyzer.mergeItems"] == "O(n²)"
    assert p["bigo_after"]["Analyzer.mergeItems"] == "O(n)"
    # main also calls the bubble sort sortByValue, so its worst case stays O(n²):
    # unchanged label and span outside the patch -> not reported.
    assert "Analyzer.main" not in p["bigo_before"]
    assert "Analyzer.main" not in p["bigo_after"]


def test_untouched_methods_absent(read_java):
    p = _merge_patch(read_java)
    assert "Analyzer.parseValue" not in p["bigo_before"]
    assert "Analyzer.parseValue" not in p["bigo_after"]


def test_invalid_patch_has_no_bigo(read_java):
    code = read_java("Analyzer")
    p = run(patcher.build_patch(code, OLD_MERGE, "total += undefinedVar;", [], 45))
    assert not p["valid"]
    assert p["bigo_before"] == {} and p["bigo_after"] == {}


def test_same_complexity_kept(read_java):
    code = read_java("Analyzer")
    new_body = OLD_MERGE.replace("result", "res")
    p = run(patcher.build_patch(code, OLD_MERGE, new_body, [], 45))
    assert p["valid"], p["problems"]
    assert p["bigo_before"]["Analyzer.mergeItems"] == p["bigo_after"]["Analyzer.mergeItems"] == "O(n²)"


# combined application of several patches

from ai.bigo_diff import combined_bigo  # noqa: E402

OLD_SORT = """for (int i = 0; i < items.size(); i++) {
    for (int j = 0; j < items.size() - 1; j++) {
        if (items.get(j).getValue() > items.get(j + 1).getValue()) {
            Item temp = items.get(j);
            items.set(j, items.get(j + 1));
            items.set(j + 1, temp);
        }
    }
}"""
NEW_SORT = "items.sort(Comparator.comparingInt(Item::getValue));"


def _p(old, new, line, imports=()):
    return {"old_code": old, "new_code": new, "imports": list(imports), "start_line": line}


def test_combined_two_methods(read_java):
    code = read_java("Analyzer")
    out = combined_bigo(code, [_p(OLD_MERGE, NEW_MERGE, 45, ["java.util.HashMap"]), _p(OLD_SORT, NEW_SORT, 69)])
    assert out["Analyzer.mergeItems"] == "O(n)"
    assert out["Analyzer.sortByValue"] == "O(n log n)"
    assert out["Analyzer.main"] == "O(n log n)"  # max of its callees once both are fixed


def test_overlapping_takes_best(read_java):
    code = read_java("Analyzer")
    same = OLD_MERGE.replace("result", "res")
    out = combined_bigo(code, [_p(OLD_MERGE, same, 45), _p(OLD_MERGE, NEW_MERGE, 45, ["java.util.HashMap"])])
    assert out["Analyzer.mergeItems"] == "O(n)"
    out2 = combined_bigo(code, [_p(OLD_MERGE, NEW_MERGE, 45, ["java.util.HashMap"]), _p(OLD_MERGE, same, 45)])
    assert out2["Analyzer.mergeItems"] == "O(n)"


def test_imports_do_not_shift_lower_patch(read_java):
    code = read_java("Analyzer").replace(
        "import java.util.*;", "import java.util.List;\nimport java.util.ArrayList;\nimport java.util.Comparator;")
    out = combined_bigo(code, [
        _p(OLD_MERGE, NEW_MERGE, 47, ["java.util.HashMap", "java.util.Map"]),
        _p(OLD_SORT, NEW_SORT, 71),
    ])
    assert out["Analyzer.mergeItems"] == "O(n)"
    assert out["Analyzer.sortByValue"] == "O(n log n)"


def test_stale_patch_ignored(read_java):
    code = read_java("Analyzer")
    assert combined_bigo(code, [_p("int nothing = 42;", "int x = 1;", 10)]) == {}
    assert combined_bigo(code, []) == {}
    out = combined_bigo(code, [_p("int nothing = 42;", "int x = 1;", 10), _p(OLD_MERGE, NEW_MERGE, 45)])
    assert out["Analyzer.mergeItems"] == "O(n)"


def test_endpoint(read_java):
    from fastapi.testclient import TestClient
    from main import app
    body = {"code": read_java("Analyzer"), "patches": [
        {"oldCode": OLD_MERGE, "newCode": NEW_MERGE, "imports": ["java.util.HashMap"], "startLine": 45}]}
    r = TestClient(app).post("/api/ai/bigo-combined", json=body)
    assert r.status_code == 200
    assert r.json()["bigo"]["Analyzer.mergeItems"] == "O(n)"


import pytest  # noqa: E402

from ai.bigo_diff import _rank  # noqa: E402
from core.bigo_analyzer import complexity_label  # noqa: E402


@pytest.mark.parametrize("pl", [(0, 0), (0, 1), (0, 2), (0, 6), (1, 0), (1, 1), (2, 0), (2, 1),
                                (3, 0), (4, 0), (5, 0), (6, 0), (7, 0), (2, 3)])
def test_rank_parses_every_analyzer_label(pl):
    assert _rank(complexity_label(pl)) == pl


def test_rank_exp_and_unknown():
    assert _rank("O(2^n)") > _rank(complexity_label((7, 0)))
    assert _rank("O(?)") is None and _rank("O(?) рекурсия") is None


def test_import_bigo_diff_standalone_has_no_cycle():
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, "-c", "import ai.bigo_diff"], cwd=backend, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

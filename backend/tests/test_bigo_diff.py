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

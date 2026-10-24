"""Per-language prompts: every prompt exists for Java and Python; Python ones ask for Python code."""

import asyncio

import pytest

from ai import ai_analyzer, patcher

NAMES = {
    "defect_explain": dict(message="m", method="f", bigo="O(n)", severity="warning", recommendation="r",
                           line_start=1, line_end=2, code="x"),
    "optimization": dict(code="x", context="c"),
    "decompose_hint": dict(class_name="C", plan="p", calls="c"),
    "review": dict(code="x", known="k", max_items=5),
    "repair": dict(errors="e"),
    "syntax_fix": dict(message="m", line=1, code="x"),
}


@pytest.mark.parametrize("name", NAMES)
def test_prompt_exists_for_both_languages(name):
    java = ai_analyzer._prompt(name, language="java", **NAMES[name])
    py = ai_analyzer._prompt(name, language="python", **NAMES[name])
    assert java and py
    if "```" in java:
        assert "```java" in java and "```python" in py


def test_unknown_language_falls_back_to_java():
    assert ai_analyzer._prompt("syntax_fix", language="kotlin", **NAMES["syntax_fix"]) == \
        ai_analyzer._prompt("syntax_fix", language="java", **NAMES["syntax_fix"])


def test_python_patch_is_validated_by_python_rules():
    code = "def f(xs):\n    total = 0\n    for x in xs:\n        total += x\n    return total\n\nprint(f([1, 2]))\n"
    good = asyncio.run(patcher.build_patch(code, "    total = 0\n    for x in xs:\n        total += x\n    return total",
                                     "return sum(xs)", []))
    assert good and good["valid"]
    bad = asyncio.run(patcher.build_patch(code, "return total", "return (total", []))
    assert bad and not bad["valid"] and "Синтаксическая ошибка" in bad["problems"][0]

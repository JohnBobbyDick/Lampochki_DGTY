from pathlib import Path

import pytest

from core import runner
from core.lang import get

ROOT = Path(__file__).resolve().parents[2]
NAMES = ["calculator", "store", "analyzer", "logger"]


def _src(name: str) -> str:
    return (ROOT / "test_monoliths" / f"{name}.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", NAMES)
def test_example_parses_and_has_size(name):
    code = _src(name)
    assert get("python").check(code) == []
    assert get("python").parse(code)
    n = len(code.splitlines())
    assert 80 <= n <= 200, n
    assert code.rstrip().endswith('if __name__ == "__main__":\n    main()')


@pytest.mark.parametrize("name", NAMES)
def test_example_runs_deterministically(name):
    code = _src(name)
    r1 = runner.run_code(code, language="python")
    r2 = runner.run_code(code, language="python")
    assert r1.exit_code == 0, r1.stderr
    assert r1.stdout.strip()
    assert r1.stdout == r2.stdout


@pytest.mark.parametrize("name", NAMES)
def test_frontend_copy_identical(name):
    a = (ROOT / "test_monoliths" / f"{name}.py").read_bytes()
    b = (ROOT / "frontend" / "src" / "examples" / f"{name}.py").read_bytes()
    assert a == b


def test_required_constructs():
    import ast
    t = {n: ast.parse(_src(n)) for n in NAMES}
    def has(name, cls):
        return any(isinstance(x, cls) for x in ast.walk(t[name]))
    assert has("calculator", ast.Match) and has("calculator", ast.Try)
    assert any(isinstance(x, ast.While) and x.orelse for x in ast.walk(t["calculator"]))
    assert any(isinstance(x, ast.For) and x.orelse for x in ast.walk(t["analyzer"]))
    assert has("analyzer", ast.ListComp) and has("analyzer", ast.GeneratorExp)
    assert has("store", ast.With) and has("store", ast.ClassDef)
    assert any(isinstance(x, ast.ExceptHandler) and x.type is None for x in ast.walk(t["logger"]))
    assert has("logger", ast.JoinedStr)

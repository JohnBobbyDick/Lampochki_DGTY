"""Python decomposition: top-level functions / whole classes → modules, Quality Gate passes."""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]
NAMES = ["calculator", "store", "analyzer", "logger"]


def _src(name: str) -> str:
    return (ROOT / "test_monoliths" / f"{name}.py").read_text(encoding="utf-8")


def _parse(code: str) -> None:
    r = client.post("/api/parse", json={"code": code, "language": "python"})
    assert r.status_code == 200 and not r.json()["errors"], r.text


def _decompose(code: str) -> dict:
    _parse(code)
    return client.post("/api/decompose").json()


def _verify() -> dict:
    return client.post("/api/decompose/verify").json()


def _file(d: dict, name: str) -> str:
    return next(f["code"] for f in d["files"] if f["name"] == name)


@pytest.mark.parametrize("name", NAMES)
def test_examples_pass_quality_gate(name):
    d = _decompose(_src(name))
    assert len(d["files"]) >= 2, d
    assert d["files"][0]["name"] == "main.py"
    v = _verify()
    assert v["passed"], v["details"]


@pytest.mark.parametrize("name", NAMES)
def test_main_and_entry_block_stay_in_facade(name):
    d = _decompose(_src(name))
    main = _file(d, "main.py")
    assert "def main():" in main
    assert 'if __name__ == "__main__":\n    main()' in main
    for f in d["files"][1:]:
        assert "def main(" not in f["code"]
        assert "__main__" not in f["code"]


def test_store_class_moves_whole():
    d = _decompose(_src("store"))
    names = [f["name"] for f in d["files"]]
    assert "store.py" in names and "product.py" in names
    store = _file(d, "store.py")
    assert "class Store:" in store
    for m in ("add_product", "has_product", "find_duplicates", "cheaper_pairs", "total_value", "find_missing"):
        assert f"def {m}(" in store
        assert all(f"def {m}(" not in f["code"] for f in d["files"] if f["name"] != "store.py")
    assert "from product import Product" in store
    # class methods are not separate units anywhere
    assert "@staticmethod\n    def validate_price" in _file(d, "product.py")


SHARED_CONST = '''LIMIT = 3


def check_limit(x):
    return x > LIMIT


def parse_a(s):
    return int(s)


def parse_b(s):
    return float(s)


def main():
    print(LIMIT, check_limit(5), parse_a("4"), parse_b("2.5"))


if __name__ == "__main__":
    main()
'''


def test_function_using_module_constant_stays_with_warning():
    d = _decompose(SHARED_CONST)
    main = _file(d, "main.py")
    assert "def check_limit(x):" in main and "LIMIT = 3" in main
    assert all("check_limit" not in f["methods"] for f in d["files"][1:])
    assert any("check_limit" in w and "LIMIT" in w and "main.py" in w for w in d["warnings"]), d["warnings"]
    assert _verify()["passed"]


OWN_CONST = '''import math

RATE = 2


def calc_a(x):
    return x * RATE


def calc_b(x):
    return math.floor(x / RATE)


def main():
    print(calc_a(3), calc_b(7))


if __name__ == "__main__":
    main()
'''


def test_constant_used_only_by_one_module_moves_with_it():
    d = _decompose(OWN_CONST)
    mod = _file(d, "analyzer.py")
    assert "RATE = 2" in mod and "import math" in mod
    assert "RATE" not in _file(d, "main.py")
    assert "from analyzer import calc_a, calc_b" in _file(d, "main.py")
    assert _verify()["passed"]


CROSS = '''"""Doc."""
from __future__ import annotations

import os


def parse_x(s):
    return s.strip()


def parse_y(s):
    return s.split(",")


def print_x(s):
    print(parse_x(s))


def print_y(s):
    print(parse_y(s), os.sep != "")


def main():
    print_x("  a ")
    print_y("a,b")


if __name__ == "__main__":
    main()
'''


def test_module_imports_function_of_other_module():
    d = _decompose(CROSS)
    printer = _file(d, "printer.py")
    assert printer.startswith("from __future__ import annotations\n")
    assert "from parser import parse_x, parse_y" in printer
    assert "import os" in printer and "import os" not in _file(d, "parser.py")
    main = _file(d, "main.py")
    assert main.startswith('"""Doc."""\nfrom __future__ import annotations\n\nimport os\nfrom printer import print_x, print_y\n')
    assert _verify()["passed"]


CYCLE = '''def parse_a(s):
    return print_a(s)


def parse_b(s):
    return s + "b"


def print_a(s):
    return s + "a"


def print_b(s):
    return parse_b(s)


def main():
    print(parse_a("x"), print_b("y"))


if __name__ == "__main__":
    main()
'''


def test_cyclic_modules_keep_units_in_facade():
    d = _decompose(CYCLE)
    main = _file(d, "main.py")
    assert "def parse_a(" in main and "def print_b(" in main
    assert any("цикл" in w for w in d["warnings"]), d["warnings"]
    assert _verify()["passed"]


def test_nothing_to_extract_is_a_warning():
    d = _decompose('def main():\n    print(1)\n\n\nif __name__ == "__main__":\n    main()\n')
    assert d["files"] == []
    assert "Нечего выделять" in d["warnings"]
    v = _verify()
    assert not v["passed"] and v["details"]["reason"] == "нечего выделять"


def test_zip_contains_all_files():
    d = _decompose(_src("calculator"))
    r = client.post("/api/decompose/zip")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == sorted(f["name"] for f in d["files"])
    for f in d["files"]:
        assert z.read(f["name"]).decode("utf-8") == f["code"]

from fastapi.testclient import TestClient

from core import lang
from main import app


def test_registry_lookup():
    assert lang.get("python").name == "python"
    assert lang.get(None).name == lang.get("cobol").name == "java"
    assert lang.by_filename("a/b.py").name == "python"
    assert lang.by_filename("Main.java").name == "java"
    assert lang.get("python").entry_file == "main.py" and lang.get("java").entry_file == "Main.java"


def test_python_check_reports_syntax_error():
    errs = lang.get("python").check("x = (\n")
    assert len(errs) == 1 and errs[0]["line"] == 1


def test_apply_uses_request_language():
    code = 'a = "System.out."\nb = 2\n'    # autodetect would call this Java
    patch = {"oldCode": "b = 2", "newCode": "b = 3", "imports": [], "startLine": 2}
    r = TestClient(app).post("/api/ai/apply", json={"code": code, "patch": patch, "language": "python"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and "b = 3" in r.json()["code"]


def test_bigo_combined_accepts_language():
    r = TestClient(app).post("/api/ai/bigo-combined", json={"code": "a = 1\n", "patches": [], "language": "python"})
    assert r.status_code == 200 and r.json()["bigo"] == {}


def test_apply_rejects_python_syntax_error_by_language():
    code = 'a = "System.out."\nb = 2\n'    # autodetect would call this Java (where it fails either way)
    patch = {"oldCode": "b = 2", "newCode": "b = (", "imports": [], "startLine": 2}
    r = TestClient(app).post("/api/ai/apply", json={"code": code, "patch": patch, "language": "python"})
    assert r.status_code == 200 and r.json()["ok"] is False


_TRICKY = 'a = "System.out."\nb = 2\n'    # autodetect would call this Java


def test_apply_adds_python_import_by_language():
    patch = {"oldCode": "b = 2", "newCode": "b = math.pi", "imports": ["math"], "startLine": 2}
    r = TestClient(app).post("/api/ai/apply", json={"code": _TRICKY, "patch": patch, "language": "python"})
    out = r.json()
    assert r.status_code == 200 and out["ok"] is True, out
    assert "import math" in out["code"] and "import math;" not in out["code"]


def test_bigo_combined_adds_python_import_by_language(monkeypatch):
    from ai import bigo_diff, patcher
    seen = {}
    real = patcher.add_imports

    def spy(code, imports, language=None):
        out = real(code, imports, language)
        seen["code"] = out[0]
        return out

    monkeypatch.setattr(patcher, "add_imports", spy)
    patch = {"oldCode": "b = 2", "newCode": "b = math.pi", "imports": ["math"], "startLine": 2}
    r = TestClient(app).post("/api/ai/bigo-combined", json={"code": _TRICKY, "patches": [patch], "language": "python"})
    assert r.status_code == 200
    assert "import math" in seen["code"] and "import math;" not in seen["code"]

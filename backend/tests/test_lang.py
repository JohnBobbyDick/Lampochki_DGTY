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

"""Full demo path: upload → graph → edit node → generate → run → compare → quality gate."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def edit_return(code, method, new_label):
    client.post("/api/parse", json={"code": code})
    g = client.get("/api/graph", params={"type": "cfg", "method": method}).json()
    ret = [n for n in g["nodes"] if n["type"] == "return"][-1]
    ret["label"] = new_label(ret["label"])
    r = client.post("/api/generate", json={"graph": {"method": method, "nodes": g["nodes"]}})
    assert r.status_code == 200, r.text
    return r.json()["code"]


def test_behavior_preserving_edit_passes_quality_gate(read_java):
    original = read_java("Calculator")
    modified = edit_return(original, "factorial", lambda l: l.replace("return ", "return (", 1) + ")")
    assert modified != original
    cmp = client.post("/api/run/compare", json={"original": original, "modified": modified}).json()
    assert cmp["behaviorPreserved"] is True
    gate = client.post("/api/quality-gate", json={"original": original, "modified": modified}).json()
    assert gate["passed"] is True


def test_behavior_changing_edit_fails_quality_gate(read_java):
    original = read_java("Calculator")
    modified = edit_return(original, "factorial", lambda l: "return 0")
    gate = client.post("/api/quality-gate", json={"original": original, "modified": modified}).json()
    assert gate["passed"] is False and gate["details"]["diff"]


def test_edit_that_breaks_compilation_is_caught(read_java):
    original = read_java("Calculator")
    modified = edit_return(original, "factorial", lambda l: "return undefinedVar")
    gate = client.post("/api/quality-gate", json={"original": original, "modified": modified}).json()
    assert gate["passed"] is False and gate["details"]["compileErrors"]

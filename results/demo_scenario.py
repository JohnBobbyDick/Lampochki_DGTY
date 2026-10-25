"""Демо-сценарий кейса на монолите Warehouse.java через HTTP API собранного стека.

Монолит → граф → диагноз → улучшение (правка узла графа, декомпозиция) → тесты поведения.
Запуск: docker compose up -d && python3 results/demo_scenario.py [http://localhost]
Результаты пишутся в results/demo-warehouse/ (summary.md + JSON каждого шага + файлы декомпозиции).
Только стандартная библиотека Python; ИИ не вызывается.
"""
import json
import pathlib
import sys
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost").rstrip("/")
ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "demo-warehouse"
CODE = (ROOT.parent / "test_monoliths" / "Warehouse.java").read_text(encoding="utf-8")
SID = str(uuid.uuid4())
NEW_LOOP = "for (int i = 0; i < count && i < width; i++)"


def call(method, path, body=None):
    req = urllib.request.Request(BASE + "/api" + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Session-Id": SID})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def edit_node(method, find, new_label):
    """Правка одного узла CFG, как двойной клик в UI: остальные метки уходят без изменений."""
    call("POST", "/parse", {"code": CODE, "language": "java"})
    g = call("GET", f"/graph?type=cfg&method={method}")
    node = next(n for n in g["nodes"] if find in n["label"])
    nodes = [{"id": n["id"], "label": new_label if n is node else n["label"]} for n in g["nodes"]]
    res = call("POST", "/generate", {"graph": {"method": method, "nodes": nodes}})
    return node["label"], res


def main():
    OUT.mkdir(exist_ok=True)
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))
        print(("OK  " if ok else "FAIL"), name, detail)

    # 1. монолит → разбор
    p = call("POST", "/parse", {"code": CODE, "language": "java"})
    check("Разбор Warehouse.java", p["methods"], f"{len(CODE.splitlines())} строк, методов: {len(p['methods'])}")

    # 2. граф
    sizes = {}
    for t in ("cfg", "call", "class"):
        g = call("GET", f"/graph?type={t}" + ("&method=Warehouse.findDuplicateNames" if t == "cfg" else ""))
        sizes[t] = (len(g["nodes"]), len(g["edges"]))
        save(f"graph-{t}.json", g)
    check("Графы CFG / Call Graph / Class Diagram", all(n for n, _ in sizes.values()),
          ", ".join(f"{t}: {n} узлов, {e} рёбер" for t, (n, e) in sizes.items()))

    # 3. диагноз
    a = call("POST", "/analyze", {"code": CODE, "language": "java"})
    save("analyze.json", a)
    dup = next((d for d in a["defects"] if d.get("method") == "Warehouse.findDuplicateNames"), None)
    check("javac без ошибок", a["compileErrors"] == [])
    check("Дефект O(n²) в findDuplicateNames: строка, узел, рекомендация, эффект",
          dup and dup["nodeId"] and dup["recommendation"] and dup.get("bigOAfter"),
          dup and f"стр. {dup['lineStart']}, узел {dup['nodeId']}, {dup['bigO']} → {dup['bigOAfter']}")

    # 4. запуск исходника
    run = call("POST", "/run", {"code": CODE, "language": "java"})
    (OUT / "run-original.txt").write_text(run["stdout"] + ("\n--- stderr ---\n" + run["stderr"] if run["stderr"] else ""),
                                          encoding="utf-8")
    check("Запуск монолита", run["exitCode"] == 0, f"exit {run['exitCode']}, {run['durationMs']} мс")

    # 5. граф → Java: правка без смены поведения и правка, меняющая поведение
    old, res = edit_node("Warehouse.formatBar", "Math.min", NEW_LOOP)
    cmp = call("POST", "/run/compare", {"original": CODE, "modified": res["code"], "language": "java"})
    save("edit-preserving.json", {"node": old, "newLabel": NEW_LOOP, "changedNodes": res["changedNodes"],
                                  "behaviorPreserved": cmp["behaviorPreserved"], "diff": cmp.get("diff")})
    check("Правка узла без смены поведения → поведение совпадает", cmp["behaviorPreserved"],
          f"«{old}» → «{NEW_LOOP}»")

    old, res = edit_node("Warehouse.formatBar", '"#"', 'bar += "="')
    cmp = call("POST", "/run/compare", {"original": CODE, "modified": res["code"], "language": "java"})
    save("edit-changing.json", {"node": old, "newLabel": 'bar += "="', "changedNodes": res["changedNodes"],
                                "behaviorPreserved": cmp["behaviorPreserved"], "diff": cmp.get("diff")})
    check("Правка узла, меняющая вывод → расхождение поймано", not cmp["behaviorPreserved"], f"«{old}» → «bar += \"=\"»")

    # 6. декомпозиция + Quality Gate
    call("POST", "/parse", {"code": CODE, "language": "java"})
    d = call("POST", "/decompose")
    files_dir = OUT / "decomposed"
    files_dir.mkdir(exist_ok=True)
    for f in files_dir.glob("*.java"):
        f.unlink()
    for f in d["files"]:
        (files_dir / f["name"]).write_text(f["code"], encoding="utf-8")
    save("decompose.json", {"files": [{"name": f["name"], "lines": len(f["code"].splitlines())} for f in d["files"]],
                            "warnings": d.get("warnings")})
    v = call("POST", "/decompose/verify")
    save("quality-gate.json", v)
    check("Декомпозиция на файлы", len(d["files"]) >= 4, ", ".join(f["name"] for f in d["files"]))
    check("Quality Gate: сборка + поведение сохранено", v["passed"], json.dumps(v.get("details"), ensure_ascii=False))

    passed = sum(ok for _, ok, _ in checks)
    lines = [f"# Демо-сценарий на Warehouse.java ({BASE})", "",
             f"Итого: **{passed} из {len(checks)}** проверок пройдено.", "",
             "| Шаг | Результат | Детали |", "|---|---|---|"]
    lines += [f"| {n} | {'✅' if ok else '❌'} | {det.replace('|', '/')} |" for n, ok, det in checks]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.exit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()

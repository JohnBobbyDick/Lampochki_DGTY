from fastapi.testclient import TestClient

import api.run as run_api
from main import app

PAIRS = """import java.util.*;
public class Demo {
    static int sumPairs(List<Integer> items) {
        int total = 0;
        for (Integer a : items) {
            for (Integer b : items) {
                total += a * b;
            }
        }
        return total;
    }
    public static void main(String[] args) {
        System.out.println(sumPairs(Arrays.asList(1, 2, 3, 4, 5, 6, 7)));
    }
}"""

PY_PAIRS = """def sum_pairs(xs):
    t = 0
    for a in xs:
        for b in xs:
            t += a * b
    return t

print(sum_pairs(list(range(9))))
"""


def hits_of(body, method, line):
    """Executions of the line probe at *line* and calls of *method*."""
    probes, hits = body["probes"], body["hits"]
    line_hits = [hits[p["slot"]] for p in probes if p["kind"] == "line" and p["line"] == line]
    calls = [hits[p["slot"]] for p in probes if p["kind"] == "method" and p["method"] == method]
    return max(line_hits), sum(calls)


def test_measure_counts_java_lines():
    r = TestClient(app).post("/api/run/measure", json={"code": PAIRS, "language": "java"})
    body = r.json()
    assert r.status_code == 200 and "error" not in body, body
    assert hits_of(body, "Demo.sumPairs", 7) == (49, 1)


def test_measure_counts_python_lines():
    body = TestClient(app).post("/api/run/measure", json={"code": PY_PAIRS, "language": "python"}).json()
    assert "error" not in body, body
    assert hits_of(body, "Module.sum_pairs", 5) == (81, 1)


def test_measure_reports_compile_error():
    body = TestClient(app).post("/api/run/measure", json={"code": "public class X { void f( }", "language": "java"}).json()
    assert body == {"error": "Программа не запустилась"}


def test_measure_without_input_does_not_hang():
    code = """import java.util.Scanner;
public class In { public static void main(String[] a) { System.out.println(new Scanner(System.in).nextLine()); } }"""
    body = TestClient(app).post("/api/run/measure", json={"code": code, "language": "java"}).json()
    assert "probes" in body or "error" in body


def test_measure_refuses_when_busy(monkeypatch):
    import asyncio
    sem = asyncio.Semaphore(0)
    monkeypatch.setattr(run_api, "MEASURE_SLOTS", sem)
    body = TestClient(app).post("/api/run/measure", json={"code": PAIRS, "language": "java"}).json()
    assert body == {"error": run_api.MEASURE_BUSY}

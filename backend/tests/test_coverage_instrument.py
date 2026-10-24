import dataclasses
import subprocess

import pytest

from core.comparator import normalize
from core.coverage import instrument
from core.coverage.build import compile_local, read_hits
from core.coverage.instrument import CoverageUnavailable, cov_java, instrument_java
from core.runner import _public_class, detect_main_class, parse_compile_errors, run_java

MONOLITH_NAMES = ["Analyzer", "Calculator", "Logger", "Store", "Streams"]


def _names(code):
    main = detect_main_class(code) or _public_class(code)
    return f"{_public_class(code) or main}.java", main


def run_cov(tmp_path, code, stdin=""):
    fname, main = _names(code)
    proc, plan = compile_local(tmp_path, fname, code)
    assert proc is None, proc and proc.stderr
    cov = [f"-Djb.cov={plan.data_file}"] if plan.data_file else []
    out = subprocess.run(
        ["java", "-Xmx256m", "-Dfile.encoding=UTF-8", *cov, "-cp", str(tmp_path / "out"), main],
        cwd=tmp_path, input=stdin, capture_output=True, text=True, timeout=30,
    )
    return out, plan


def line_hits(plan, hits, line):
    return [hits[p.slot] for p in plan.probes if p.kind == "line" and p.line == line]


def line_of(code, needle):
    return next(i for i, s in enumerate(code.split("\n"), 1) if needle in s)


@pytest.mark.parametrize("name", MONOLITH_NAMES)
def test_line_numbers_preserved(read_java, name):
    code = read_java(name)
    inst = instrument_java(code)
    assert inst.code.count("\n") == code.count("\n")
    lines = inst.code.split("\n")
    assert any(p.kind == "line" for p in inst.probes)
    for p in inst.probes:
        if p.kind in ("line", "method"):
            assert f"__Cov.h({p.slot})" in lines[p.line - 1], (p, lines[p.line - 1])
    assert [p.id for p in inst.probes] == list(range(len(inst.probes)))
    slot = 0
    for p in inst.probes:
        assert p.slot == slot
        slot += len(p.outcomes)
    assert inst.slots == slot
    assert "class __Cov" in inst.cov_source


def test_probe_json_and_method_labels():
    code = "public class Demo {\n  public static void main(String[] a) {\n    int x = 1;\n  }\n}\n"
    inst = instrument_java(code)
    m = next(p for p in inst.probes if p.kind == "method")
    assert m.to_json() == {"id": m.id, "kind": "method", "line": 2, "method": "Demo.main",
                           "label": "Demo.main", "outcomes": ["выполнено"], "slot": m.slot}
    ln = next(p for p in inst.probes if p.kind == "line")
    assert (ln.line, ln.method, ln.label, ln.outcomes) == (3, "Demo.main", "", ["выполнено"])


def test_package_in_cov_source():
    code = "package a.b;\npublic class P { void f() { int x = 1; } }\n"
    inst = instrument_java(code)
    assert inst.cov_source.startswith("package a.b;")


def test_field_initializers_untouched():
    code = ("public class F {\n  Runnable r = () -> { System.out.println(1); };\n"
            "  void f() { Runnable q = () -> { System.out.println(2); }; }\n}\n")
    inst = instrument_java(code)
    lines = inst.code.split("\n")
    assert "__Cov" not in lines[1]
    assert lines[2].count("__Cov.h(") == 3  # method + local decl + statement inside the lambda block


@pytest.mark.parametrize("name", MONOLITH_NAMES)
def test_monoliths_same_output(tmp_path, read_java, name):
    code = read_java(name)
    out, plan = run_cov(tmp_path, code)
    assert plan.error is None
    assert out.returncode == 0, out.stderr
    assert normalize(out.stdout) == normalize(run_java(code).stdout)
    hits = read_hits(plan)
    assert hits is not None and len(hits) == plan.slots
    assert any(hits[p.slot] == 1 for p in plan.probes if p.kind == "method" and p.method.endswith(".main"))


TRICKY = """public class Tricky {
    final int v;
    Tricky() { this(1); System.out.println("ctor0"); }
    Tricky(int v) { super(); this.v = v; }
    static void p(String s) { System.out.println(s); }
    static void early(boolean x) {
        if (x) return;
        p("not early");
    }
    static void dangle(boolean a, boolean b) {
        if (a)
            if (b) p("ab");
            else
                p("a!b");
    }
    static int loop() {
        int n = 0;
        while (true) {
            n++;
            if (n > 3) return n;
        }
    }
    public static void main(String[] args) {
        final int k = 1;
        @SuppressWarnings("unused") final int unused = 2;
        early(true); early(false);
        dangle(true, true); dangle(false, false); dangle(false, true); dangle(true, false);
        outer:
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                if (j == k) continue outer;
                p(i + "," + j);
            }
        }
        System.out.println(loop());
        System.out.println(new Tricky().v);
        for (int i = 0; i < 2; i++) p("u" + i);
        do p("d"); while (false);
        Runnable r = new Runnable() { public void run() { p("anon"); } };
        r.run();
    }
}
"""


def test_unbraced_and_labels(tmp_path):
    out, plan = run_cov(tmp_path, TRICKY)
    assert plan.error is None and out.returncode == 0, out.stderr
    assert out.stdout == run_java(TRICKY).stdout
    hits = read_hits(plan)
    assert line_hits(plan, hits, line_of(TRICKY, 'p("a!b")')) == [1]
    assert line_hits(plan, hits, line_of(TRICKY, 'p("ab")')) == [2, 1]  # inner if, p("ab")
    assert line_hits(plan, hits, line_of(TRICKY, "outer:")) == [1]
    assert line_hits(plan, hits, line_of(TRICKY, 'p(i + "," + j)')) == [3]
    # constructor: method + this(...) probes go after "this(1);"
    ctor = line_of(TRICKY, "this(1)")
    inst_line = instrument_java(TRICKY).code.split("\n")[ctor - 1]
    assert inst_line.index("this(1);") < inst_line.index("__Cov.h(")
    methods = {p.method for p in plan.probes if p.kind == "method"}
    assert {"Tricky.Tricky", "Tricky.main", "Tricky.dangle"} <= methods
    assert "Tricky.run" not in methods  # anonymous class methods: line probes only
    anon = [p for p in plan.probes if p.kind == "line" and p.line == line_of(TRICKY, 'p("anon")')]
    assert anon and all(p.method == "Tricky.main" for p in anon)


def test_counts(tmp_path):
    code = """public class Cnt {
    public static void main(String[] a) {
        int s = 0;
        for (int i = 0; i < 5; i++)
            s += i;
        System.out.println(s);
    }
}
"""
    out, plan = run_cov(tmp_path, code)
    assert out.stdout.strip() == "10"
    assert line_hits(plan, read_hits(plan), 5) == [5]


DEG = """public class Deg {
    public static void main(String[] args) {
        int a = 1;
        System.out.println(a + 1);
    }
}
"""


def _garbage_on_line_3(real, max_level):
    def fake(code, *, strip=None):
        res = real(code, strip=strip)
        if (strip or {}).get(3, 0) < max_level:
            lines = res.code.split("\n")
            lines[2] = "undefinedThing(); " + lines[2]
            res = dataclasses.replace(res, code="\n".join(lines))
        return res
    return fake


def test_degrade(tmp_path, monkeypatch):
    monkeypatch.setattr(instrument, "instrument_java", _garbage_on_line_3(instrument.instrument_java, 2))
    out, plan = run_cov(tmp_path, DEG)
    assert plan.error is None and plan.data_file is not None
    assert out.stdout.strip() == "2"
    assert plan.probes and not [p for p in plan.probes if p.line == 3]
    assert read_hits(plan) is not None


def test_degrade_to_original(tmp_path, monkeypatch):
    monkeypatch.setattr(instrument, "instrument_java", _garbage_on_line_3(instrument.instrument_java, 99))
    out, plan = run_cov(tmp_path, DEG)
    assert plan.error == "инструментированный код не скомпилировался"
    assert plan.data_file is None and read_hits(plan) is None
    assert out.returncode == 0 and out.stdout.strip() == "2"


def test_user_compile_error(tmp_path):
    code = "public class Bad {\n    public static void main(String[] a) {\n        int x = ;\n    }\n}\n"
    proc, plan = compile_local(tmp_path, "Bad.java", code)
    assert proc is not None and proc.returncode != 0
    errs = parse_compile_errors(proc.stderr)
    assert errs and {e["line"] for e in errs} == {3} and all(e["file"] == "Bad.java" for e in errs)


# Java 9 try-with-resources on an effectively final variable: javac 11 accepts it, javalang 0.13 does not.
UNPARSEABLE = """import java.io.StringReader;

public class Un {
    public static void main(String[] args) throws Exception {
        StringReader r = new StringReader("ok");
        try (r) {
            System.out.println((char) r.read());
        }
    }
}
"""


def test_unparseable_runs_without_coverage(tmp_path):
    with pytest.raises(CoverageUnavailable):
        instrument_java(UNPARSEABLE)
    out, plan = run_cov(tmp_path, UNPARSEABLE)
    assert plan.error.startswith("Не удалось разобрать код для покрытия")
    assert plan.data_file is None and plan.probes == []
    assert out.stdout.strip() == "o"


def test_cov_runtime_api(tmp_path):
    """__Cov.c / r / lp / h write the documented slots (file mapped through -Djb.cov)."""
    (tmp_path / "__Cov.java").write_text(cov_java(16), encoding="utf-8")
    (tmp_path / "H.java").write_text("""public class H {
    public static void main(String[] a) {
        Object o = new Object();
        System.out.println("" + __Cov.c(0, true) + __Cov.c(0, false)
            + __Cov.r(2, 0, 1L, 2L) + __Cov.r(2, 0, 2, 2) + __Cov.r(2, 0, 3, 2)
            + __Cov.r(5, 4, 1.0, 1.0) + __Cov.r(5, 5, 1.0, 2.0) + __Cov.r(5, 0, Double.NaN, 1.0)
            + __Cov.r(7, 5, o, o) + __Cov.r(7, 4, true, false)
            + __Cov.lp(9, false, false) + __Cov.lp(9, true, false) + __Cov.lp(9, false, true));
        __Cov.h(11); __Cov.h(11);
    }
}
""", encoding="utf-8")
    subprocess.run(["javac", "-d", "out", "H.java", "__Cov.java"], cwd=tmp_path, check=True)
    data = tmp_path / "cov.bin"
    data.write_bytes(bytes(64))
    out = subprocess.run(["java", f"-Djb.cov={data}", "-cp", "out", "H"], cwd=tmp_path,
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "truefalsetruefalsefalsetruetruefalsefalsefalsefalsefalsetrue"
    raw = data.read_bytes()
    hits = [int.from_bytes(raw[i:i + 4], "little") for i in range(0, 64, 4)]
    assert hits == [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 2, 0, 0, 0, 0]
    # without the property the counters live in memory and the program still works
    out = subprocess.run(["java", "-cp", "out", "H"], cwd=tmp_path, capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.startswith("truefalse")


def _strip_probes(text):
    """Undo line/method probe insertions (no unbraced bodies in the inputs)."""
    import re
    return re.sub(r" __Cov\.h\(\d+\);", "", re.sub(r"__Cov\.h\(\d+\); ", "", text))


ESCAPES = (
    "public class Esc {\n"
    "    public static void main(String[] args) {\n"
    '        String s = "\\u00e9 hello world"; System.out.println(s); char a = \'\\u0041\'; System.out.println(a);\n'
    "        char z = '\\u0000'; String bs = \"\\\\u0041\"; System.out.println((int) z + bs);\n"
    "        \\u0069nt q = 7; System.out.println(q);\n"
    "    }\n"
    "}\n"
)


def test_unicode_escapes(tmp_path):
    inst = instrument_java(ESCAPES)
    lines = inst.code.split("\n")
    assert '"\\u00e9 hello world"; __Cov.h(' in lines[2]
    assert "'\\u0041'; __Cov.h(" in lines[2]
    assert "__Cov.h(" in lines[4] and lines[4].index("__Cov.h(") < lines[4].index("\\u0069nt")
    assert _strip_probes(inst.code) == ESCAPES
    out, plan = run_cov(tmp_path, ESCAPES)
    assert plan.error is None and out.returncode == 0, out.stderr
    assert out.stdout == run_java(ESCAPES).stdout
    assert "__Cov" not in out.stdout


def test_tabs_and_crlf(tmp_path):
    code = ("public class Crlf {\r\n\tpublic static void main(String[] a) {\r\n"
            "\t\tint x = 1;\tint y = 2;\r\n\t\tif (x < y)\tSystem.out.println(\"t\\tab\");\r\n\t}\r\n}\r\n")
    inst = instrument_java(code)
    assert inst.code.count("\r\n") == code.count("\r\n")
    assert "\t\t__Cov.h(" in inst.code and "int x = 1;\t__Cov.h(" in inst.code
    inst = instrument_java(code, strip={4: 1})   # round-trip on line probes only (Task 3 adds branch/rel on line 4)
    import re
    unwrapped = re.sub(r"\{ __Cov\.h\(\d+\); ([^\r\n]*?) \}", r"\1", inst.code)
    assert _strip_probes(unwrapped) == code
    assert "{ __Cov.h(" in inst.code.split("\r\n")[3] and inst.code.split("\r\n")[3].endswith('System.out.println("t\\tab"); }')
    out, plan = run_cov(tmp_path, code)
    assert plan.error is None and out.stdout == run_java(code).stdout


def test_read_hits_rejects_symlink(tmp_path):
    code = "public class S {\n    public static void main(String[] a) {\n        int x = 1;\n    }\n}\n"
    _, plan = compile_local(tmp_path, "S.java", code)
    assert read_hits(plan) is not None
    secret = tmp_path / "secret.bin"
    secret.write_bytes(bytes(plan.slots * 4))
    plan.data_file.unlink()
    try:
        plan.data_file.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks not available")
    assert read_hits(plan) is None
    assert (plan.data_file.parent.stat().st_mode & 0o777) == 0o755


def test_read_hits_binary_safe(tmp_path):
    """0x1A and CRLF bytes in a counter must survive (Windows text mode would truncate them)."""
    import struct
    from core.coverage.build import CovPlan

    data = tmp_path / "cov.bin"
    values = [26, 0x0A0D, 0, 3]
    data.write_bytes(struct.pack("<4i", *values))
    assert read_hits(CovPlan(data_file=data, slots=4)) == values


def test_counter_saturates(tmp_path):
    (tmp_path / "__Cov.java").write_text(cov_java(2), encoding="utf-8")
    (tmp_path / "H.java").write_text(
        "public class H { public static void main(String[] a) { __Cov.h(0); __Cov.c(0, true); __Cov.h(1); } }",
        encoding="utf-8")
    subprocess.run(["javac", "-d", "out", "H.java", "__Cov.java"], cwd=tmp_path, check=True)
    data = tmp_path / "cov.bin"
    data.write_bytes((0x7FFFFFFF).to_bytes(4, "little") + bytes(4))
    subprocess.run(["java", f"-Djb.cov={data}", "-cp", "out", "H"], cwd=tmp_path, check=True)
    raw = data.read_bytes()
    assert int.from_bytes(raw[:4], "little") == 0x7FFFFFFF and int.from_bytes(raw[4:], "little") == 1

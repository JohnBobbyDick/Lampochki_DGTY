import re
import subprocess
import time

from core.coverage.build import compile_local, read_hits
from core.coverage.instrument import instrument_java
from core.runner import _public_class, detect_main_class, run_java


def run_cov(tmp_path, code, timeout=30):
    main = detect_main_class(code) or _public_class(code)
    proc, plan = compile_local(tmp_path, f"{_public_class(code) or main}.java", code)
    assert proc is None, proc and proc.stderr
    cov = [f"-Djb.cov={plan.data_file}"] if plan.data_file else []
    out = subprocess.run(
        ["java", "-Xmx256m", "-Dfile.encoding=UTF-8", *cov, "-cp", str(tmp_path / "out"), main],
        cwd=tmp_path, capture_output=True, text=True, timeout=timeout,
    )
    return out, plan


def find(plan, kind, label):
    found = [p for p in plan.probes if p.kind == kind and p.label == label]
    assert len(found) == 1, (kind, label, [(p.kind, p.label) for p in plan.probes if p.kind != "line"])
    return found[0]


def counts(plan, hits, kind, label):
    p = find(plan, kind, label)
    return dict(zip(p.outcomes, hits[p.slot:p.slot + len(p.outcomes)]))


def line_of(code, needle):
    return next(i for i, s in enumerate(code.split("\n"), 1) if needle in s)


SAMPLE = """public class Sample {
    static int sign(int x) {
        if (x > 0) {
            return 1;
        }
        return 0;
    }

    static String kind(int c) {
        switch (c) {
            case 1:
            case 2:
                return "small";
            case 3:
                return "three";
            default:
                return "other";
        }
    }

    public static void main(String[] args) {
        System.out.println(sign(5));
        int n = 1;
        int hits = 0;
        for (int i = 0; i <= 5; i++) {
            if (i < 3) {
                hits++;
            }
            if (i > 2 && n < 3) {
                n++;
            }
            if (i == 1 || !(hits > 1)) {
                System.out.println("or " + i);
            }
        }
        System.out.println(n + " " + hits);
        int k = 0;
        while (k < 2) k++;
        while (k < 0) k--;
        int[] empty = {};
        int[] three = {1, 2, 3};
        int sum = 0;
        for (int v : empty) sum += v;
        for (int v : three) sum += v;
        System.out.println(sum);
        for (int c = 1; c <= 4; c++) System.out.println(kind(c));
        int zero = 0;
        try {
            System.out.println(n / zero);
        } catch (ArithmeticException e) {
            System.out.println("caught");
        }
        String size = n > 2 ? "big" : "small";
        System.out.println(size);
        int d = 0;
        do {
            d++;
        } while (d < 3);
        System.out.println(d);
    }
}
"""

T, F = "истина", "ложь"
RAN, NEVER = "тело выполнялось", "тело ни разу не выполнялось"


def test_sample_counts(tmp_path):
    out, plan = run_cov(tmp_path, SAMPLE)
    assert plan.error is None and out.returncode == 0, out.stderr
    assert out.stdout == run_java(SAMPLE).stdout
    assert out.stdout.split("\n")[:4] == ["1", "or 0", "or 1", "3 3"]
    assert len(plan.probes) == len(instrument_java(SAMPLE).probes)   # nothing degraded
    h = read_hits(plan)

    assert counts(plan, h, "branch", "if (x > 0)") == {T: 1, F: 0}
    assert counts(plan, h, "rel", "x > 0") == {"<": 0, "==": 0, ">": 1}
    # no logic: no cond probe, but the comparison still gets a rel probe
    assert not [p for p in plan.probes if p.kind == "cond" and p.label in ("x > 0", "i < 3")]
    assert counts(plan, h, "branch", "if (i < 3)") == {T: 3, F: 3}
    assert counts(plan, h, "rel", "i < 3") == {"<": 3, "==": 1, ">": 2}

    # short-circuit: n < 3 is evaluated only when i > 2
    assert counts(plan, h, "branch", "if (i > 2 && n < 3)") == {T: 2, F: 4}
    assert counts(plan, h, "cond", "i > 2") == {T: 3, F: 3}
    assert counts(plan, h, "cond", "n < 3") == {T: 2, F: 1}
    assert counts(plan, h, "rel", "i > 2") == {"<": 2, "==": 1, ">": 3}
    assert counts(plan, h, "rel", "n < 3") == {"<": 2, "==": 1, ">": 0}

    assert counts(plan, h, "branch", "if (i == 1 || !(hits > 1))") == {T: 2, F: 4}
    assert counts(plan, h, "cond", "i == 1") == {T: 1, F: 5}
    assert counts(plan, h, "cond", "hits > 1") == {T: 4, F: 1}
    assert counts(plan, h, "rel", "i == 1") == {"==": 1, "!=": 5}
    assert counts(plan, h, "rel", "hits > 1") == {"<": 0, "==": 1, ">": 4}

    assert counts(plan, h, "branch", "for (int i = 0; i <= 5; i++)") == {RAN: 1, NEVER: 0}
    assert counts(plan, h, "rel", "i <= 5") == {"<": 5, "==": 1, ">": 1}
    assert counts(plan, h, "branch", "while (k < 2)") == {RAN: 1, NEVER: 0}
    assert counts(plan, h, "rel", "k < 2") == {"<": 2, "==": 1, ">": 0}
    assert counts(plan, h, "branch", "while (k < 0)") == {RAN: 0, NEVER: 1}
    assert counts(plan, h, "branch", "for (int v : empty)") == {RAN: 0, NEVER: 1}
    assert counts(plan, h, "branch", "for (int v : three)") == {RAN: 1, NEVER: 0}

    assert counts(plan, h, "branch", "case 1, 2") == {"выполнен": 2}
    assert counts(plan, h, "branch", "case 3") == {"выполнен": 1}
    assert counts(plan, h, "branch", "default") == {"выполнен": 1}
    assert counts(plan, h, "branch", "catch (ArithmeticException)") == {"выполнен": 1}
    assert counts(plan, h, "branch", "?: (n > 2)") == {T: 1, F: 0}
    assert counts(plan, h, "branch", "do…while (d < 3)") == {T: 2, F: 1}
    assert counts(plan, h, "rel", "d < 3") == {"<": 2, "==": 1, ">": 0}

    case12 = find(plan, "branch", "case 1, 2")
    assert case12.line == line_of(SAMPLE, "case 2:") and case12.method == "Sample.kind"
    assert find(plan, "branch", "if (x > 0)").line == line_of(SAMPLE, "if (x > 0)")


def _undo_line_probes(text):
    text = re.sub(r"\{ __Cov\.h\(\d+\); ([^\n]*?) \}", r"\1", text)
    return re.sub(r" __Cov\.h\(\d+\);", "", re.sub(r"__Cov\.h\(\d+\); ", "", text))


def test_strip_level1_removes_exactly_decision_probes():
    every = {i: 1 for i in range(1, SAMPLE.count("\n") + 2)}
    inst = instrument_java(SAMPLE, strip=every)
    assert {p.kind for p in inst.probes} == {"line", "method"}
    for needle in ("__Cov.c(", "__Cov.r(", "__Cov.lp(", "__c"):
        assert needle.replace("__c", "boolean __c") not in inst.code
    assert _undo_line_probes(inst.code) == SAMPLE
    # one line only: just that line's decision probes go
    line = line_of(SAMPLE, "while (k < 2)")
    full = instrument_java(SAMPLE)
    part = instrument_java(SAMPLE, strip={line: 1})
    gone = [(p.kind, p.label) for p in full.probes if p.line == line and p.kind in ("branch", "rel")]
    assert gone == [("branch", "while (k < 2)"), ("rel", "k < 2")]
    assert len(part.probes) == len(full.probes) - 2
    assert "boolean __c" not in part.code.split("\n")[line - 1]
    assert "__Cov.lp(" in part.code      # other loops keep theirs


MIXED = """public class Mixed {
    public static void main(String[] args) {
        Integer boxed = 5; int p = 5; String s = null; char ch = 'a'; long L = 3; boolean f = true;
        Integer q = 6;
        if (boxed == p) System.out.println("bp");
        if (s == null) System.out.println("null");
        if (ch < 'z') System.out.println("ch");
        if (L < p) System.out.println("L");
        if (f == true) System.out.println("f");
        if (boxed < q) System.out.println("boxed<q");
        float fl = 16777217;
        if (16777217 == fl) System.out.println("float");
    }
}
"""


def test_mixed_types(tmp_path):
    out, plan = run_cov(tmp_path, MIXED)
    assert plan.error is None and out.returncode == 0, out.stderr
    assert out.stdout == run_java(MIXED).stdout
    assert "boxed<q" in out.stdout and "float" in out.stdout
    bp = line_of(MIXED, "boxed == p")
    on_bp = [p.kind for p in plan.probes if p.line == bp]
    assert "line" in on_bp
    # Integer == int is ambiguous for the __Cov.r overloads: degradation round 1 drops the decision
    # probes of that line only (the line probe stays, other lines keep theirs)
    assert "rel" not in on_bp and "branch" not in on_bp
    h = read_hits(plan)
    assert counts(plan, h, "rel", "s == null") == {"==": 1, "!=": 0}
    assert counts(plan, h, "rel", "ch < 'z'") == {"<": 1, "==": 0, ">": 0}
    assert counts(plan, h, "rel", "L < p") == {"<": 1, "==": 0, ">": 0}
    assert counts(plan, h, "rel", "f == true") == {"==": 1, "!=": 0}
    assert counts(plan, h, "rel", "boxed < q") == {"<": 1, "==": 0, ">": 0}
    assert counts(plan, h, "rel", "16777217 == fl") == {"==": 1, "!=": 0}


TRICKY = """import java.util.*;
import java.util.function.*;

public class Tri {
    enum Color { RED, GREEN }
    static int abs(int x) { return x >= 0 ? x : -x; }
    static int loopForever() {
        int n = 0;
        for (;;) {
            if (++n > 2) return n;
        }
    }
    static int doForever() {
        int n = 0;
        do {
            n++;
            if (n == 4) return n;
        } while (true);
    }
    static String col(Color c) {
        switch (c) {
            case RED: return "r";
            default: return "g";
        }
    }
    public static void main(String[] args) {
        List<?> wild = Arrays.asList(1, 2, 3);
        String str = "abc";
        Object o = str;
        if ((abs(-3) > 2 ? abs(-3) : 0) > 2) System.out.println("tern-in-if");
        if (str != null && str.length() > 2 && o instanceof String) System.out.println("and3");
        Function<Integer, String> fmt = v -> v > 1 ? "many" : v == 1 ? "one" : "none";
        System.out.println(fmt.apply(0) + fmt.apply(1) + fmt.apply(5));
        outer:
        while (wild.size() > 0) {
            for (Object w : wild) {
                if (w.equals(2)) break outer;
                System.out.println("w" + w);
            }
        }
        Iterator<?> it = wild.iterator();
        while (it.hasNext())
            if (it.next().equals(3)) System.out.println("three");
            else System.out.println("other");
        for (int i = 0, j = 10; i < j; i += 4, j--) System.out.println(i + ":" + j);
        while (true) { if (args.length == 0) break; }
        System.out.println(loopForever() + doForever());
        System.out.println(col(Color.RED) + col(Color.GREEN));
        switch (str) { case "abc": System.out.println("s"); break; case "x": }
        try {
            Object[] arr = new Integer[1];
            arr[0] = "s";
        } catch (ArrayStoreException | IllegalStateException e) {
            System.out.println("multi");
        } finally {
            System.out.println("fin");
        }
        Runnable r = () -> { int z = 0; while (z < 2) z++; System.out.println("lambda" + z); };
        r.run();
        int a = 0;
        if (a < 1)
            if (a > -1) System.out.println("in");
            else System.out.println("dangle");
        do a++; while (a < 3);
        System.out.println(!(a == 3) ? "no" : "yes");
    }
}
"""


def test_tricky_constructs(tmp_path):
    out, plan = run_cov(tmp_path, TRICKY)
    assert plan.error is None and out.returncode == 0, out.stderr
    assert out.stdout == run_java(TRICKY).stdout
    assert len(plan.probes) == len(instrument_java(TRICKY).probes)   # nothing degraded
    h = read_hits(plan)
    labels = {(p.kind, p.label) for p in plan.probes}
    # constant loops: no branch probe
    assert not [p for p in plan.probes if p.kind == "branch" and "true" in p.label or p.label == "for (;;)"]
    assert counts(plan, h, "branch", "?: (x >= 0)") == {T: 1, F: 2}   # abs(-3) twice, abs(3)? no: -3,-3
    assert counts(plan, h, "branch", "if ((abs(-3) > 2 ? abs(-3) : 0) > 2)") == {T: 1, F: 0}
    assert counts(plan, h, "branch", "?: (abs(-3) > 2)") == {T: 1, F: 0}
    assert counts(plan, h, "cond", "o instanceof String") == {T: 1, F: 0}
    assert ("rel", "o instanceof String") not in labels
    assert counts(plan, h, "branch", "?: (v > 1)") == {T: 1, F: 2}
    assert counts(plan, h, "branch", "?: (v == 1)") == {T: 1, F: 1}
    assert counts(plan, h, "branch", "while (wild.size() > 0)") == {RAN: 1, NEVER: 0}
    assert counts(plan, h, "branch", "for (Object w : wild)") == {RAN: 1, NEVER: 0}
    assert counts(plan, h, "branch", "while (it.hasNext())") == {RAN: 1, NEVER: 0}
    assert counts(plan, h, "branch", "if (it.next().equals(3))") == {T: 1, F: 2}
    assert counts(plan, h, "branch", "while (z < 2)") == {RAN: 1, NEVER: 0}
    assert counts(plan, h, "branch", "case RED") == {"выполнен": 1}
    assert counts(plan, h, "branch", 'case "abc"') == {"выполнен": 1}
    assert ("branch", 'case "x"') not in labels         # empty group: no probe
    assert counts(plan, h, "branch", "catch (ArrayStoreException | IllegalStateException)") == {"выполнен": 1}
    assert counts(plan, h, "branch", "do…while (a < 3)") == {T: 2, F: 1}
    assert counts(plan, h, "branch", "?: (!(a == 3))") == {T: 0, F: 1}
    assert counts(plan, h, "cond", "a == 3") == {T: 1, F: 0}
    assert counts(plan, h, "branch", "if (a > -1)") == {T: 1, F: 0}
    assert find(plan, "branch", "while (z < 2)").method == "Tri.main"


def test_labels_collapse_and_truncate():
    code = ("public class Lab {\n  static boolean f(int a, int b) {\n"
            "    if (a   >\n        b) return true;\n"
            "    if (a + a + a + a + a + a + a + a + a + a + a + a + a + a + a + a + a > b) return false;\n"
            "    return a == b;\n  }\n}\n")
    inst = instrument_java(code)
    assert inst.code.count("\n") == code.count("\n")
    branches = [p for p in inst.probes if p.kind == "branch"]
    assert branches[0].label == "if (a > b)" and branches[0].line == 3
    long = branches[1].label
    assert len(long) == 60 and long.endswith("…") and long.startswith("if (a + a")
    # `return a == b;` is not a decision: no probes for it
    assert not [p for p in inst.probes if p.kind == "rel" and p.label == "a == b"]


def test_overhead(tmp_path):
    code = """public class Over {
    public static void main(String[] args) {
        long c = 0;
        for (int i = 0; i < 5000000; i++) {
            if (i % 3 == 0 && i > 10) c++;
        }
        System.out.println(c);
    }
}
"""
    t0 = time.monotonic()
    out, plan = run_cov(tmp_path, code, timeout=60)
    elapsed = time.monotonic() - t0
    assert plan.error is None and out.returncode == 0, out.stderr
    assert out.stdout.strip() == "1666663"
    assert elapsed < 10, elapsed
    assert counts(plan, read_hits(plan), "cond", "i > 10") == {T: 1666663, F: 4}

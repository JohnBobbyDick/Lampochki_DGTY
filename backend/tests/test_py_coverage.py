import json
import os
import subprocess
import sys
import textwrap

from core import runner
from core.coverage import build, instrument
from core.coverage.build import prepare_python, python_cov_env, read_hits


def run_py(tmp_path, code, stdin=""):
    code = textwrap.dedent(code)
    plan = prepare_python(tmp_path, code)
    assert plan.error is None, plan.error
    out = subprocess.run(
        [sys.executable, "-u", "_jb_run.py"], cwd=tmp_path, input=stdin, capture_output=True, text=True,
        timeout=30, env=python_cov_env(plan), preexec_fn=runner.python_preexec(),
    )
    return out, plan, read_hits(plan), code


def hits_of(plan, hits, kind, line=None):
    return [hits[p.slot:p.slot + len(p.outcomes)] for p in plan.probes
            if p.kind == kind and (line is None or p.line == line)]


def line_of(code, needle):
    return next(i for i, s in enumerate(code.split("\n"), 1) if needle in s)


def test_if_branch_true(tmp_path):
    out, plan, hits, code = run_py(tmp_path, """\
        x = 1
        if x > 0:
            print("pos")
        else:
            print("neg")
        """)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "pos\n"
    assert hits_of(plan, hits, "branch", 2) == [[1, 0]]
    assert build.marker_set(tmp_path / "cov" / "compiled")


def test_for_empty_list(tmp_path):
    out, plan, hits, _ = run_py(tmp_path, """\
        for i in []:
            print(i)
        for j in [1, 2]:
            pass
        """)
    assert out.returncode == 0, out.stderr
    assert hits_of(plan, hits, "branch", 1) == [[0, 1]]
    assert hits_of(plan, hits, "branch", 3) == [[1, 0]]
    assert [p.outcomes for p in plan.probes if p.kind == "branch"] == [instrument._LOOP] * 2


def test_cond_and_rel_probes(tmp_path):
    out, plan, hits, _ = run_py(tmp_path, """\
        a, b, c = 1, 2, 3
        if a > 0 and b:
            pass
        if a < b:
            pass
        if a < b < c:
            pass
        if a == b:
            pass
        """)
    assert out.returncode == 0, out.stderr
    assert hits_of(plan, hits, "cond", 2) == [[1, 0], [1, 0]]
    assert hits_of(plan, hits, "rel", 2) == [[0, 0, 1]]           # a > 0: a > b-side
    assert hits_of(plan, hits, "rel", 4) == [[1, 0, 0]]
    assert [p.outcomes for p in plan.probes if p.kind == "rel" and p.line == 4] == [instrument._ORDER]
    assert hits_of(plan, hits, "rel", 6) == []
    assert hits_of(plan, hits, "rel", 8) == [[0, 1]]
    assert [p.outcomes for p in plan.probes if p.kind == "rel" and p.line == 8] == [instrument._EQ]


def test_line_and_method_probes(tmp_path):
    out, plan, hits, code = run_py(tmp_path, """\
        def f(n):
            if n:
                return 1
            return 2

        def g():
            return 3

        print(f(0))
        """)
    assert out.returncode == 0, out.stderr
    assert hits_of(plan, hits, "line", line_of(code, "return 1")) == [[0]]
    assert hits_of(plan, hits, "line", line_of(code, "return 2")) == [[1]]
    assert hits_of(plan, hits, "line", line_of(code, "print(f(0))")) == [[1]]
    methods = {p.method: hits[p.slot] for p in plan.probes if p.kind == "method"}
    assert methods == {"Module.f": 1, "Module.g": 0}
    assert next(p for p in plan.probes if p.kind == "line" and p.line == 9).method == "Module.main"


def test_traceback_points_to_user_line(tmp_path):
    out, plan, hits, _ = run_py(tmp_path, """\
        def boom():
            return 1 / 0

        boom()
        """)
    assert out.returncode == 1
    assert 'File "main.py", line 2, in boom' in out.stderr
    assert "ZeroDivisionError" in out.stderr
    assert "_jb_run" not in out.stderr and "py_cov" not in out.stderr
    assert hits_of(plan, hits, "method") == [[1]]


def test_name_mangling_and_nested(tmp_path):
    out, plan, hits, _ = run_py(tmp_path, """\
        class Box:
            def __secret(self, x):
                def inner(y):
                    if y > 1:
                        return y * 2
                    return y
                return inner(x)

            def open(self, x):
                return self.__secret(x)

        print(Box().open(3))
        """)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "6\n"
    methods = {p.method: hits[p.slot] for p in plan.probes if p.kind == "method"}
    assert methods == {"Box.__secret": 1, "Box.__secret.inner": 1, "Box.open": 1}


def test_docstrings_and_future(tmp_path):
    out, plan, hits, _ = run_py(tmp_path, '''\
        """Module doc."""
        from __future__ import annotations
        from dataclasses import dataclass


        @dataclass
        class P:
            """Point."""
            x: int

        def f(a: P) -> P:
            """Func doc."""
            return a

        print(__doc__, f.__doc__, P.__doc__, f(P(1)).x, __name__)
        ''')
    assert out.returncode == 0, out.stderr
    assert out.stdout == "Module doc. Func doc. Point. 1 __main__\n"


def test_short_circuit_and_side_effects(tmp_path):
    out, plan, hits, _ = run_py(tmp_path, """\
        calls = []
        def f():
            calls.append("f")
            return True
        def g():
            calls.append("g")
            return False
        def k(v):
            calls.append(v)
            return v
        if f() or g():
            pass
        while k(0) < k(1) and not k(""):
            break
        x = "a" if k(2) > 5 else "b"
        print(calls, x)
        """)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "['f', 0, 1, '', 2] b\n"
    assert hits_of(plan, hits, "cond", 11) == [[1, 0], [0, 0]]
    assert hits_of(plan, hits, "branch", 15) == [[0, 1]]


def test_except_and_case(tmp_path):
    out, plan, hits, _ = run_py(tmp_path, """\
        try:
            int("x")
        except ValueError:
            print("bad")
        except KeyError:
            print("key")
        match 2:
            case 1:
                print(1)
            case 2:
                print(2)
        """)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "bad\n2\n"
    assert [(p.label, hits[p.slot]) for p in plan.probes if p.kind == "branch"] == [
        ("except ValueError", 1), ("except KeyError", 0), ("case 1", 0), ("case 2", 1)]


def test_sibling_import_and_argv(tmp_path):
    (tmp_path / "helper.py").write_text("def two():\n    return 2\n", encoding="utf-8")
    out, plan, hits, _ = run_py(tmp_path, """\
        import sys
        from helper import two
        print(two(), sys.argv)
        """)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "2 ['main.py']\n"


def test_probes_deterministic_across_processes(tmp_path):
    code = textwrap.dedent("""\
        def f(a, b):
            if a and (b or not a):
                return [x for x in range(a) if x > 1]
            while a < b:
                a += 1
            return a if a == b else -1
        print(f(1, 3))
        """)
    plan = prepare_python(tmp_path, code)
    script = "import json, py_cov; print(json.dumps(py_cov.instrument(open('main.py').read())[1]))"
    env = dict(python_cov_env(plan), PYTHONHASHSEED="12345")
    child = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True,
                           env=env, timeout=30)
    assert child.returncode == 0, child.stderr
    key = ("id", "slot", "line", "kind", "method", "label", "outcomes")
    assert [tuple(p[k] for k in key) for p in json.loads(child.stdout)] == \
        [tuple(getattr(p, k) for k in key) for p in plan.probes]
    assert [p.id for p in plan.probes] == list(range(len(plan.probes)))
    assert plan.slots == sum(len(p.outcomes) for p in plan.probes)
    assert isinstance(plan.probes[0], instrument.Probe)


def test_constants_match_java():
    from core.coverage import py_cov
    for name in ("_DONE", "_TF", "_LOOP", "_HIT", "_ORDER", "_EQ"):
        assert getattr(py_cov, name) == getattr(instrument, name)


def test_cov_files_and_env(tmp_path):
    plan = prepare_python(tmp_path, "print(1)\n")
    assert plan.data_file == tmp_path / "cov" / "hits.bin"
    assert plan.data_file.stat().st_size == plan.slots * 4
    if sys.platform != "win32":
        assert oct(os.stat(tmp_path / "cov").st_mode & 0o777) == "0o755"
    marker = tmp_path / "cov" / "compiled"      # pre-created empty: the child only writes into it
    assert marker.is_file() and marker.stat().st_size == 0 and oct(marker.stat().st_mode & 0o777) == "0o666"
    assert plan.language == "python" and not build.marker_set(marker)
    assert (tmp_path / "py_cov.py").exists() and (tmp_path / "_jb_run.py").exists()
    env = python_cov_env(plan)
    assert env["JB_COV"] == str(plan.data_file) and env["JB_COV_SLOTS"] == str(plan.slots)
    assert not any(k.startswith("GEMINI") for k in env)
    assert build.PY_RUN_CMD[1:] == ["-u", "_jb_run.py"]


def test_syntax_error_no_coverage(tmp_path):
    plan = prepare_python(tmp_path, "def f(:\n")
    assert plan.error is not None and plan.data_file is None
    assert not plan.error.startswith("Покрытие недоступно")


def test_run_without_cov_env(tmp_path):
    plan = prepare_python(tmp_path, "print('hi')\n")
    out = subprocess.run([sys.executable, "-u", "_jb_run.py"], cwd=tmp_path, capture_output=True, text=True,
                         env=runner.python_env(), timeout=30)
    assert out.returncode == 0 and out.stdout == "hi\n"
    assert not build.marker_set(tmp_path / "cov" / "compiled")
    assert read_hits(plan) == [0] * plan.slots

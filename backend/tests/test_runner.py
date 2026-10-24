import os

import pytest

from core.comparator import compare_code
from core.runner import detect_main_class, run_java

HELLO = 'public class Hello { public static void main(String[] a){ System.out.println("hi " + (1+2)); } }'


def test_run_ok():
    r = run_java(HELLO)
    assert r.exit_code == 0 and r.stdout.strip() == "hi 3"


def test_compile_error_has_line():
    r = run_java("public class B { void f(){ int a = ; } public static void main(String[] x){} }")
    assert r.exit_code != 0 and r.compile_errors and r.compile_errors[0]["line"] == 1


def test_timeout():
    r = run_java("public class T { public static void main(String[] a){ while(true){} } }", timeout_sec=1)
    assert r.exit_code == 124


def test_detect_main_class(read_java):
    assert detect_main_class(read_java("Logger")) == "Logger"


def test_compare_same_and_different():
    changed = HELLO.replace('"hi "', '"yo "')
    assert compare_code(HELLO, HELLO).behavior_preserved
    cmp = compare_code(HELLO, changed)
    assert not cmp.behavior_preserved and "-hi 3" in cmp.diff


@pytest.mark.parametrize("name", ["Analyzer", "Calculator", "Logger", "Store", "Streams"])
def test_monoliths_run(read_java, name):
    assert run_java(read_java(name)).exit_code == 0


@pytest.mark.parametrize("bad", ["../Evil", "A;rm -rf /", "a b"])
def test_rejects_bad_main_class(bad):
    r = run_java(HELLO, main_class=bad)
    assert r.exit_code == 2 and "Недопустимое" in r.stderr


def test_docker_command_with_coverage(tmp_path):
    from core.runner import docker_command

    plain = " ".join(docker_command(tmp_path, ["A.java"], "A"))
    assert "/cov" not in plain and "-Djb.cov" not in plain
    cmd = " ".join(docker_command(tmp_path, ["A.java"], "A", cov=True))
    assert f"{tmp_path / 'cov'}:/cov:rw" in cmd
    assert "-Djb.cov=/cov/cov.bin" in cmd and "touch /cov/compiled" in cmd
    assert "-Xmx256m" in cmd
    assert "ulimit -f" in cmd and cmd.index("ulimit -f") < cmd.index("java -Xmx256m")
    assert "ulimit -f 9;" in " ".join(docker_command(tmp_path, ["A.java"], "A", cov=True, slots=100))


def test_ensure_path_never_points_java_home_at_a_launcher_stub(tmp_path, monkeypatch):
    # macOS: /usr/bin/javac is a stub; JAVA_HOME=/usr makes it exec itself forever
    from core import runner
    stub_bin = tmp_path / "usr" / "bin"
    stub_bin.mkdir(parents=True)
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setenv("PATH", "/bin")
    runner._ensure_path(stub_bin)
    assert "JAVA_HOME" not in os.environ
    jdk_bin = tmp_path / "jdk" / "bin"
    jdk_bin.mkdir(parents=True)
    (tmp_path / "jdk" / "release").write_text('JAVA_VERSION="17"')
    runner._ensure_path(jdk_bin)
    assert os.environ["JAVA_HOME"] == str(tmp_path / "jdk")

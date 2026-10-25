from core.comparator import compare_runs, normalize
from models.schemas import RunResponse


def test_identical_output_is_preserved():
    ok = RunResponse(stdout="hi\n", exit_code=0)
    assert compare_runs(ok, ok).behavior_preserved


def test_missing_jdk_is_not_reported_as_preserved():
    """Two identical 'toolchain not found' failures must not count as matching behaviour."""
    broken = RunResponse(stderr="Java toolchain not found: [WinError 2]", exit_code=127)
    assert not compare_runs(broken, broken).behavior_preserved


def test_crlf_and_trailing_whitespace_and_empty_lines_preserved():
    r1 = RunResponse(stdout="hello   \r\nworld\r\n\r\n", exit_code=0)
    r2 = RunResponse(stdout="hello\nworld\n", exit_code=0)
    res = compare_runs(r1, r2)
    assert res.behavior_preserved
    assert res.diff == ""


def test_ansi_and_timestamp_normalized():
    out1 = "\x1b[32m2026-10-25 12:00:00\x1b[0m Result: 42\r\n"
    out2 = "2026-10-25 15:30:11 Result: 42\n"
    assert normalize(out1) == normalize(out2)

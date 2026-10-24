from core.comparator import compare_runs
from models.schemas import RunResponse


def test_identical_output_is_preserved():
    ok = RunResponse(stdout="hi\n", exit_code=0)
    assert compare_runs(ok, ok).behavior_preserved


def test_missing_jdk_is_not_reported_as_preserved():
    """Two identical 'toolchain not found' failures must not count as matching behaviour."""
    broken = RunResponse(stderr="Java toolchain not found: [WinError 2]", exit_code=127)
    assert not compare_runs(broken, broken).behavior_preserved

import pytest

from chatnotify.models import (
    FAILED,
    INTERRUPTED,
    PASSED,
    CiInfo,
    RunResult,
    TestCounts,
    resolve_status,
)


def _result(exit_code=0, interrupted=False):
    return RunResult(exit_code=exit_code, duration_seconds=1.5, interrupted=interrupted)


def test_clean_exit_with_no_counts_is_passed():
    assert resolve_status(_result(0), None) == PASSED


def test_clean_exit_with_all_passing_counts_is_passed():
    counts = TestCounts(total=3, passed=3, failed=0, skipped=0)
    assert resolve_status(_result(0), counts) == PASSED


def test_nonzero_exit_with_zero_failures_is_failed():
    """A pytest collection error reports no failures but exits 1."""
    counts = TestCounts(total=0, passed=0, failed=0, skipped=0)
    assert resolve_status(_result(1), counts) == FAILED


def test_zero_exit_with_failures_recorded_is_failed():
    counts = TestCounts(total=5, passed=4, failed=1, skipped=0)
    assert resolve_status(_result(0), counts) == FAILED


def test_interrupted_overrides_everything():
    counts = TestCounts(total=5, passed=5, failed=0, skipped=0)
    assert resolve_status(_result(130, interrupted=True), counts) == INTERRUPTED


def test_counts_and_meta_are_frozen():
    counts = TestCounts(total=1, passed=1, failed=0, skipped=0)
    with pytest.raises(Exception):
        counts.total = 99


def test_ci_info_detected_reflects_provider():
    assert CiInfo().detected is False
    assert CiInfo(provider="GitHub Actions").detected is True

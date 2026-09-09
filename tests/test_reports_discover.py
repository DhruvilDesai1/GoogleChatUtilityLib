import os
import time

import pytest

from chatnotify import reports

PASSING_XML = (
    '<testsuite name="s" tests="1"><testcase classname="c" name="t"/></testsuite>'
)


def write(path, content=PASSING_XML, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_default_globs_find_surefire_reports(tmp_path):
    write(str(tmp_path / "target" / "surefire-reports" / "TEST-Login.xml"))
    found = reports.discover(str(tmp_path))
    assert len(found) == 1


def test_default_globs_find_root_junit_xml(tmp_path):
    write(str(tmp_path / "junit.xml"))
    assert len(reports.discover(str(tmp_path))) == 1


def test_default_globs_recurse_into_test_results(tmp_path):
    write(str(tmp_path / "test-results" / "chrome" / "results.xml"))
    assert len(reports.discover(str(tmp_path))) == 1


def test_stale_autodetected_report_is_ignored(tmp_path):
    started = time.time()
    write(str(tmp_path / "junit.xml"), mtime=started - 86400)
    assert reports.discover(str(tmp_path), since=started) == []


def test_fresh_autodetected_report_is_kept(tmp_path):
    started = time.time()
    write(str(tmp_path / "junit.xml"), mtime=started + 1)
    assert len(reports.discover(str(tmp_path), since=started)) == 1


def test_report_written_in_the_same_second_is_kept(tmp_path):
    """Coarse filesystem mtime must not discard a legitimately fresh report."""
    started = time.time()
    write(str(tmp_path / "junit.xml"), mtime=started - 0.5)
    assert len(reports.discover(str(tmp_path), since=started)) == 1


def test_explicit_glob_is_also_staleness_filtered(tmp_path):
    started = time.time()
    write(str(tmp_path / "custom" / "out.xml"), mtime=started - 86400)
    assert reports.discover(str(tmp_path), patterns=["custom/*.xml"], since=started) == []


def test_fresh_explicit_glob_is_returned(tmp_path):
    started = time.time()
    write(str(tmp_path / "custom" / "out.xml"), mtime=started + 1)
    found = reports.discover(str(tmp_path), patterns=["custom/*.xml"], since=started)
    assert len(found) == 1


def test_explicit_glob_overrides_defaults(tmp_path):
    write(str(tmp_path / "junit.xml"))
    write(str(tmp_path / "custom" / "out.xml"))
    found = reports.discover(str(tmp_path), patterns=["custom/*.xml"])
    assert len(found) == 1
    assert found[0].endswith("out.xml")


def test_directories_are_not_returned(tmp_path):
    os.makedirs(str(tmp_path / "test-results" / "nested.xml"), exist_ok=True)
    assert reports.discover(str(tmp_path)) == []


def test_duplicate_matches_are_deduplicated(tmp_path):
    write(str(tmp_path / "test-results" / "a.xml"))
    found = reports.discover(str(tmp_path), patterns=["test-results/*.xml", "test-results/**/*.xml"])
    assert len(found) == 1


def test_collect_returns_counts_for_discovered_reports(tmp_path):
    write(str(tmp_path / "junit.xml"))
    counts = reports.collect(str(tmp_path))
    assert counts.total == 1 and counts.passed == 1


def test_collect_returns_none_when_nothing_found(tmp_path):
    assert reports.collect(str(tmp_path)) is None


TWO_TEST_XML = (
    '<testsuite name="s" tests="2">'
    '<testcase classname="c" name="one"/>'
    '<testcase classname="c" name="two"><failure/></testcase>'
    "</testsuite>"
)


def test_duplicate_report_sets_are_not_summed(tmp_path):
    """The same 2-test run emitted to three default locations must count as 2, not 6."""
    write(str(tmp_path / "junit.xml"), content=TWO_TEST_XML)
    write(str(tmp_path / "test-results" / "r.xml"), content=TWO_TEST_XML)
    write(str(tmp_path / "reports" / "r.xml"), content=TWO_TEST_XML)
    counts = reports.collect(str(tmp_path), quiet=True)
    assert counts.total == 2
    assert counts.failed == 1


def test_ambiguous_sets_use_only_the_newest(tmp_path):
    write(str(tmp_path / "junit.xml"), content=TWO_TEST_XML, mtime=1000)
    write(str(tmp_path / "test-results" / "r.xml"), content=TWO_TEST_XML, mtime=2000)
    write(str(tmp_path / "reports" / "r.xml"), content=TWO_TEST_XML, mtime=1500)
    found = reports.discover(str(tmp_path), quiet=True)
    assert len(found) == 1
    assert found[0].endswith(os.path.join("test-results", "r.xml"))


def test_surefire_and_failsafe_reports_share_one_set(tmp_path):
    """Surefire and failsafe both come from one `mvn verify` and must still be summed."""
    write(str(tmp_path / "target" / "surefire-reports" / "a.xml"), mtime=1000)
    write(str(tmp_path / "target" / "failsafe-reports" / "b.xml"), mtime=2000)
    found = reports.discover(str(tmp_path), quiet=True)
    assert len(found) == 2


def test_discarding_older_sets_is_announced_on_stderr(tmp_path, capsys):
    write(str(tmp_path / "junit.xml"), mtime=1000)
    write(str(tmp_path / "test-results" / "r.xml"), mtime=2000)
    reports.discover(str(tmp_path))
    err = capsys.readouterr().err
    assert "using 'test-results' reports (1 files)" in err
    assert "ignoring older sets: root" in err


def test_unambiguous_autodetect_announces_file_count(tmp_path, capsys):
    write(str(tmp_path / "junit.xml"))
    reports.discover(str(tmp_path))
    err = capsys.readouterr().err
    assert "using 'root' reports (1 files)" in err
    assert "ignoring" not in err


def test_quiet_suppresses_set_selection_message(tmp_path, capsys):
    write(str(tmp_path / "junit.xml"), mtime=1000)
    write(str(tmp_path / "test-results" / "r.xml"), mtime=2000)
    reports.discover(str(tmp_path), quiet=True)
    assert capsys.readouterr().err == ""


def test_explicit_glob_found_count_is_announced_on_stderr(tmp_path, capsys):
    write(str(tmp_path / "custom" / "out.xml"))
    reports.discover(str(tmp_path), patterns=["custom/*.xml"])
    err = capsys.readouterr().err
    assert "using 1 report file(s)" in err


def test_stale_explicit_glob_is_announced_on_stderr(tmp_path, capsys):
    started = time.time()
    write(str(tmp_path / "custom" / "out.xml"), mtime=started - 86400)
    reports.discover(str(tmp_path), patterns=["custom/*.xml"], since=started)
    err = capsys.readouterr().err
    assert "ignoring 1 stale report file(s) older than this run" in err


def test_quiet_suppresses_stale_explicit_glob_message(tmp_path, capsys):
    started = time.time()
    write(str(tmp_path / "custom" / "out.xml"), mtime=started - 86400)
    reports.discover(str(tmp_path), patterns=["custom/*.xml"], since=started, quiet=True)
    assert capsys.readouterr().err == ""


# --- future-dated reports (clock skew forwards) --------------------------------

FAILING_XML = (
    '<testsuite name="s" tests="1">'
    '<testcase classname="ancient" name="ANCIENT_STALE_FAILURE"><failure/></testcase>'
    "</testsuite>"
)


def test_future_dated_report_does_not_beat_a_fresh_one(tmp_path):
    """A report stamped in the future must never win the newest-set comparison."""
    started = time.time()
    write(
        str(tmp_path / "build" / "test-results" / "old.xml"),
        content=FAILING_XML,
        mtime=started + 7200,
    )
    write(str(tmp_path / "target" / "surefire-reports" / "fresh.xml"), mtime=started + 0.1)
    found = reports.discover(str(tmp_path), since=started, quiet=True)
    assert len(found) == 1
    assert found[0].endswith("fresh.xml")


def test_future_dated_report_is_the_only_candidate_yields_nothing(tmp_path):
    started = time.time()
    write(str(tmp_path / "junit.xml"), content=FAILING_XML, mtime=started + 7200)
    assert reports.discover(str(tmp_path), since=started, quiet=True) == []
    assert reports.collect(str(tmp_path), since=started, quiet=True) is None


def test_future_dated_report_is_announced_on_stderr(tmp_path, capsys):
    started = time.time()
    write(str(tmp_path / "junit.xml"), mtime=started + 7200)
    reports.discover(str(tmp_path), since=started)
    err = capsys.readouterr().err
    assert "future-dated" in err
    assert "1" in err


def test_future_dated_explicit_report_is_ignored_and_announced(tmp_path, capsys):
    started = time.time()
    write(str(tmp_path / "custom" / "out.xml"), mtime=started + 7200)
    found = reports.discover(str(tmp_path), patterns=["custom/*.xml"], since=started)
    assert found == []
    assert "future-dated" in capsys.readouterr().err


def test_quiet_suppresses_future_dated_message(tmp_path, capsys):
    started = time.time()
    write(str(tmp_path / "junit.xml"), mtime=started + 7200)
    reports.discover(str(tmp_path), since=started, quiet=True)
    assert capsys.readouterr().err == ""


# --- stale autodetected reports must say so ------------------------------------


def test_stale_autodetected_report_is_announced_on_stderr(tmp_path, capsys):
    """Backwards clock skew must not drop every count without a diagnostic."""
    started = time.time()
    write(str(tmp_path / "junit.xml"), mtime=started - 30)
    assert reports.discover(str(tmp_path), since=started) == []
    err = capsys.readouterr().err
    assert "ignoring 1 stale report file(s) older than this run" in err


def test_quiet_suppresses_stale_autodetect_message(tmp_path, capsys):
    started = time.time()
    write(str(tmp_path / "junit.xml"), mtime=started - 30)
    reports.discover(str(tmp_path), since=started, quiet=True)
    assert capsys.readouterr().err == ""


# --- concurrency lock ----------------------------------------------------------


def lock_path(tmp_path):
    return str(tmp_path / reports.LOCK_FILENAME)


def test_overlapping_autodetect_warns_and_returns_nothing(tmp_path, capsys):
    """The second, overlapping discovery must refuse to guess rather than mix runs."""
    write(str(tmp_path / "junit.xml"))
    inner = {}
    real_match = reports._match_files

    def reentrant(root, patterns):
        if "found" not in inner:
            inner["found"] = "pending"
            inner["found"] = reports.discover(str(tmp_path), quiet=False)
        return real_match(root, patterns)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(reports, "_match_files", reentrant)
    try:
        outer = reports.discover(str(tmp_path))
    finally:
        monkey.undo()

    assert len(outer) == 1
    assert inner["found"] == []
    err = capsys.readouterr().err
    assert "another chatnotify run appears active" in err
    assert "--report" in err


def test_held_lock_blocks_autodetect(tmp_path, capsys):
    write(str(tmp_path / "junit.xml"))
    with open(lock_path(tmp_path), "w", encoding="utf-8") as handle:
        handle.write("999999\n")
    assert reports.discover(str(tmp_path)) == []
    assert reports.collect(str(tmp_path)) is None
    assert "another chatnotify run appears active" in capsys.readouterr().err


def test_quiet_suppresses_lock_contention_message(tmp_path, capsys):
    write(str(tmp_path / "junit.xml"))
    with open(lock_path(tmp_path), "w", encoding="utf-8") as handle:
        handle.write("999999\n")
    assert reports.discover(str(tmp_path), quiet=True) == []
    assert capsys.readouterr().err == ""


def test_explicit_report_bypasses_a_held_lock(tmp_path):
    write(str(tmp_path / "custom" / "out.xml"))
    with open(lock_path(tmp_path), "w", encoding="utf-8") as handle:
        handle.write("999999\n")
    found = reports.discover(str(tmp_path), patterns=["custom/*.xml"], quiet=True)
    assert len(found) == 1
    assert os.path.exists(lock_path(tmp_path))


def test_stale_lock_file_is_reclaimed(tmp_path):
    write(str(tmp_path / "junit.xml"))
    stale = time.time() - (reports.LOCK_STALE_SECONDS + 60)
    with open(lock_path(tmp_path), "w", encoding="utf-8") as handle:
        handle.write("31337\n")
    os.utime(lock_path(tmp_path), (stale, stale))
    assert len(reports.discover(str(tmp_path), quiet=True)) == 1
    assert not os.path.exists(lock_path(tmp_path))


def test_lock_is_removed_after_successful_discovery(tmp_path):
    write(str(tmp_path / "junit.xml"))
    reports.discover(str(tmp_path), quiet=True)
    assert not os.path.exists(lock_path(tmp_path))


def test_lock_is_released_when_discovery_raises(tmp_path, monkeypatch):
    write(str(tmp_path / "junit.xml"))

    def boom(root, patterns):
        raise RuntimeError("glob exploded")

    monkeypatch.setattr(reports, "_match_files", boom)
    with pytest.raises(RuntimeError):
        reports.discover(str(tmp_path), quiet=True)
    assert not os.path.exists(lock_path(tmp_path))


def test_unlockable_root_degrades_to_unlocked_discovery(tmp_path, monkeypatch):
    """A read-only discovery root must never stop the tool."""
    write(str(tmp_path / "junit.xml"))
    real_open = os.open

    def refuse(path, *args, **kwargs):
        if os.path.basename(str(path)) == reports.LOCK_FILENAME:
            raise PermissionError(13, "read-only directory")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", refuse)
    assert len(reports.discover(str(tmp_path), quiet=True)) == 1
    assert not os.path.exists(lock_path(tmp_path))


# --- reports vanishing mid-discovery -------------------------------------------


def test_report_vanishing_before_mtime_comparison_does_not_raise(tmp_path, monkeypatch):
    write(str(tmp_path / "junit.xml"))
    write(str(tmp_path / "test-results" / "r.xml"))
    real_getmtime = os.path.getmtime

    def flaky(path):
        if str(path).endswith("junit.xml"):
            raise FileNotFoundError(2, "vanished")
        return real_getmtime(path)

    monkeypatch.setattr(os.path, "getmtime", flaky)
    found = reports.discover(str(tmp_path), quiet=True)
    assert len(found) == 1
    assert found[0].endswith("r.xml")


def test_all_reports_vanishing_yields_no_counts(tmp_path, monkeypatch):
    write(str(tmp_path / "junit.xml"))

    def gone(path):
        raise FileNotFoundError(2, "vanished")

    monkeypatch.setattr(os.path, "getmtime", gone)
    assert reports.discover(str(tmp_path), quiet=True) == []
    assert reports.collect(str(tmp_path), quiet=True) is None


# --- unparseable reports are announced -----------------------------------------


def test_collect_warns_about_unparseable_autodetected_report(tmp_path, capsys):
    write(str(tmp_path / "junit.xml"), content="<testsuite><testcase")
    assert reports.collect(str(tmp_path)) is None
    assert "could not be parsed" in capsys.readouterr().err


def test_collect_quiet_suppresses_unparseable_warning(tmp_path, capsys):
    write(str(tmp_path / "junit.xml"), content="<testsuite><testcase")
    assert reports.collect(str(tmp_path), quiet=True) is None
    assert capsys.readouterr().err == ""

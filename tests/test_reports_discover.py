import os
import time

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

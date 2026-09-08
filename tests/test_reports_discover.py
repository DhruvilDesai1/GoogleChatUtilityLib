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


def test_explicit_glob_ignores_staleness(tmp_path):
    started = time.time()
    write(str(tmp_path / "custom" / "out.xml"), mtime=started - 86400)
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

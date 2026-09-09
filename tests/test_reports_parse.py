import os

from chatnotify import reports

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "reports")


def fixture(name):
    return os.path.join(FIXTURES, name)


def test_pytest_report_counts_cases_not_attributes():
    counts = reports.parse_files([fixture("pytest.xml")])
    assert (counts.total, counts.passed, counts.failed, counts.skipped) == (4, 2, 1, 1)


def test_pytest_report_captures_failed_name():
    counts = reports.parse_files([fixture("pytest.xml")])
    assert counts.failed_names == ("tests.test_math.test_divide",)


def test_surefire_error_element_counts_as_failed():
    counts = reports.parse_files([fixture("surefire.xml")])
    assert (counts.total, counts.passed, counts.failed, counts.skipped) == (3, 2, 1, 0)
    assert counts.failed_names == ("com.teamninja.LoginTest.expiredSession",)


def test_jest_case_without_classname_uses_bare_name():
    counts = reports.parse_files([fixture("jest.xml")])
    assert counts.failed_names == ("removes item",)


def test_multiple_files_are_summed():
    counts = reports.parse_files([fixture("pytest.xml"), fixture("surefire.xml")])
    assert (counts.total, counts.passed, counts.failed, counts.skipped) == (7, 4, 2, 1)


def test_malformed_xml_is_skipped_not_raised():
    counts = reports.parse_files([fixture("malformed.xml"), fixture("surefire.xml")])
    assert counts.total == 3


def test_only_malformed_input_returns_none():
    assert reports.parse_files([fixture("malformed.xml")]) is None


def test_missing_file_returns_none():
    assert reports.parse_files([fixture("does-not-exist.xml")]) is None


def test_empty_input_returns_none():
    assert reports.parse_files([]) is None


def test_summary_attributes_are_ignored_in_favour_of_real_cases():
    """The testsuite element claims 99 tests and 50 failures; only 3 cases exist.

    This is the regression guard for the whole module: an implementation that read
    <testsuite> attributes instead of walking <testcase> elements would report the
    fictional 99/50 here. That mistake is how the retired Java library double-counted
    retried tests.
    """
    counts = reports.parse_files([fixture("lying_attributes.xml")])
    assert (counts.total, counts.passed, counts.failed, counts.skipped) == (3, 1, 1, 1)


def test_case_without_name_attribute_falls_back_to_placeholder():
    counts = reports.parse_files([fixture("lying_attributes.xml")])
    assert counts.failed_names == ("retry.Suite.flakyFailed",)
    assert counts.skipped == 1


# --- unparseable reports must not disappear silently ---------------------------


def test_unparseable_report_is_announced_on_stderr(capsys):
    counts = reports.parse_files([fixture("malformed.xml"), fixture("surefire.xml")])
    assert counts.total == 3
    err = capsys.readouterr().err
    assert "1 report file(s) could not be parsed" in err


def test_truncated_report_is_announced_on_stderr(tmp_path, capsys):
    """A runner killed mid-write leaves a truncated file; counts must not go quiet."""
    path = tmp_path / "truncated.xml"
    path.write_text('<testsuite name="s"><testcase classname="c" name="t"', encoding="utf-8")
    assert reports.parse_files([str(path)]) is None
    assert "1 report file(s) could not be parsed" in capsys.readouterr().err


def test_null_byte_report_is_announced_on_stderr(tmp_path, capsys):
    path = tmp_path / "nul.xml"
    path.write_bytes(b'<testsuite name="s">\x00<testcase name="t"/></testsuite>')
    assert reports.parse_files([str(path)]) is None
    assert "could not be parsed" in capsys.readouterr().err


def test_missing_report_is_announced_on_stderr(capsys):
    assert reports.parse_files([fixture("does-not-exist.xml")]) is None
    assert "could not be parsed" in capsys.readouterr().err


def test_parse_files_quiet_suppresses_the_warning(capsys):
    assert reports.parse_files([fixture("malformed.xml")], quiet=True) is None
    assert capsys.readouterr().err == ""


def test_parse_files_quiet_is_accepted_positionally(capsys):
    """`paths` stays the first parameter; quiet is appended after it."""
    assert reports.parse_files([fixture("malformed.xml")], True) is None
    assert capsys.readouterr().err == ""


def test_parseable_reports_produce_no_warning(capsys):
    reports.parse_files([fixture("pytest.xml")])
    assert capsys.readouterr().err == ""

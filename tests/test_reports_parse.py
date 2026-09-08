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

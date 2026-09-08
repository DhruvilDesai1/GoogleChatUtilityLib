"""Discover and parse JUnit XML. The universal counts source across all runners."""

from typing import Iterable, Optional
from xml.etree import ElementTree

from .models import TestCounts


def _case_name(case) -> str:
    name = case.get("name") or "<unnamed>"
    classname = case.get("classname")
    if classname:
        return "%s.%s" % (classname, name)
    return name


def parse_files(paths: Iterable[str]) -> Optional[TestCounts]:
    """Sum counts across JUnit XML files. Returns None if no test cases were found."""
    total = passed = failed = skipped = 0
    failed_names = []

    for path in paths:
        try:
            tree = ElementTree.parse(str(path))
        except (ElementTree.ParseError, OSError):
            continue
        for case in tree.iter("testcase"):
            total += 1
            if case.find("failure") is not None or case.find("error") is not None:
                failed += 1
                failed_names.append(_case_name(case))
            elif case.find("skipped") is not None:
                skipped += 1
            else:
                passed += 1

    if total == 0:
        return None
    return TestCounts(
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        failed_names=tuple(failed_names),
    )

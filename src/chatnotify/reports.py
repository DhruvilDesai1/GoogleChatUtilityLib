"""Discover and parse JUnit XML. The universal counts source across all runners."""

import glob
import os
from typing import Iterable, List, Optional, Sequence
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


DEFAULT_GLOBS = (
    "target/surefire-reports/*.xml",
    "target/failsafe-reports/*.xml",
    "junit.xml",
    "test-results/**/*.xml",
    "reports/**/*.xml",
    "build/test-results/**/*.xml",
)

_MTIME_TOLERANCE_SECONDS = 1.0


def discover(
    root: str,
    patterns: Optional[Sequence[str]] = None,
    since: Optional[float] = None,
) -> List[str]:
    """Find report files under root. Staleness filtering applies to defaults only."""
    explicit = patterns is not None
    active = tuple(patterns) if explicit else DEFAULT_GLOBS
    cutoff = None if (explicit or since is None) else since - _MTIME_TOLERANCE_SECONDS

    found = set()
    for pattern in active:
        for match in glob.glob(os.path.join(root, pattern), recursive=True):
            if not os.path.isfile(match):
                continue
            if cutoff is not None:
                try:
                    if os.path.getmtime(match) < cutoff:
                        continue
                except OSError:
                    continue
            found.add(os.path.normpath(match))
    return sorted(found)


def collect(
    root: str,
    patterns: Optional[Sequence[str]] = None,
    since: Optional[float] = None,
) -> Optional[TestCounts]:
    """Discover reports then parse them. None means no counts are available."""
    return parse_files(discover(root, patterns=patterns, since=since))

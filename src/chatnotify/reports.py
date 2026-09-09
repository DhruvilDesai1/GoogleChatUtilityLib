"""Discover and parse JUnit XML. The universal counts source across all runners."""

import glob
import os
import sys
from typing import Iterable, List, Optional, Sequence, Tuple
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


DEFAULT_GLOB_SETS = (
    ("maven", ("target/surefire-reports/*.xml", "target/failsafe-reports/*.xml")),
    ("gradle", ("build/test-results/**/*.xml",)),
    ("test-results", ("test-results/**/*.xml",)),
    ("reports", ("reports/**/*.xml",)),
    ("root", ("junit.xml",)),
)

DEFAULT_GLOBS = tuple(
    pattern for _name, patterns in DEFAULT_GLOB_SETS for pattern in patterns
)

_MTIME_TOLERANCE_SECONDS = 1.0


def _match_files(root: str, patterns: Sequence[str]) -> List[str]:
    """Glob `patterns` under `root`; files only, deduplicated by normalized path."""
    found = set()
    for pattern in patterns:
        for match in glob.glob(os.path.join(root, pattern), recursive=True):
            if os.path.isfile(match):
                found.add(os.path.normpath(match))
    return sorted(found)


def _split_staleness(paths: List[str], cutoff: Optional[float]) -> Tuple[List[str], int]:
    """Partition `paths` at the staleness cutoff. Returns (kept, stale_count)."""
    if cutoff is None:
        return paths, 0
    kept = []
    stale = 0
    for path in paths:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime < cutoff:
            stale += 1
        else:
            kept.append(path)
    return kept, stale


def discover(
    root: str,
    patterns: Optional[Sequence[str]] = None,
    since: Optional[float] = None,
    quiet: bool = False,
) -> List[str]:
    """Find report files under root.

    An explicit `patterns` argument is the union of every pattern given, since the
    user named those files deliberately. Auto-detection instead groups the
    built-in globs into named sets (see `DEFAULT_GLOB_SETS`) and returns only the
    set containing the newest file, so a single run's report emitted to more than
    one default location is never summed twice.

    Staleness filtering (files older than `since`, within a small tolerance)
    applies in both cases: a report named explicitly with `--report` is just as
    capable of being a stale leftover from a previous run as an auto-detected one.
    """
    cutoff = None if since is None else since - _MTIME_TOLERANCE_SECONDS

    if patterns is not None:
        matched = _match_files(root, patterns)
        kept, stale = _split_staleness(matched, cutoff)
        if stale and not quiet:
            print(
                "chatnotify: ignoring %d stale report file(s) older than this run" % stale,
                file=sys.stderr,
            )
        if kept and not quiet:
            print("chatnotify: using %d report file(s)" % len(kept), file=sys.stderr)
        return kept

    candidates = []  # [(name, files, newest_mtime), ...]
    for name, set_patterns in DEFAULT_GLOB_SETS:
        matched = _match_files(root, set_patterns)
        kept, _stale = _split_staleness(matched, cutoff)
        if kept:
            candidates.append((name, kept, max(os.path.getmtime(path) for path in kept)))

    if not candidates:
        return []

    winner_name, winner_files, _winner_mtime = max(candidates, key=lambda item: item[2])
    ignored_names = [name for name, _files, _mtime in candidates if name != winner_name]

    if not quiet:
        if ignored_names:
            print(
                "chatnotify: using '%s' reports (%d files); ignoring older sets: %s"
                % (winner_name, len(winner_files), ", ".join(ignored_names)),
                file=sys.stderr,
            )
        else:
            print(
                "chatnotify: using '%s' reports (%d files)" % (winner_name, len(winner_files)),
                file=sys.stderr,
            )

    return sorted(winner_files)


def collect(
    root: str,
    patterns: Optional[Sequence[str]] = None,
    since: Optional[float] = None,
    quiet: bool = False,
) -> Optional[TestCounts]:
    """Discover reports then parse them. None means no counts are available."""
    return parse_files(discover(root, patterns=patterns, since=since, quiet=quiet))

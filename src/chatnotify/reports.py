"""Discover and parse JUnit XML. The universal counts source across all runners."""

import glob
import os
import sys
import time
from typing import Iterable, List, Optional, Sequence, Tuple
from xml.etree import ElementTree

from .models import TestCounts


def _case_name(case) -> str:
    name = case.get("name") or "<unnamed>"
    classname = case.get("classname")
    if classname:
        return "%s.%s" % (classname, name)
    return name


def parse_files(paths: Iterable[str], quiet: bool = False) -> Optional[TestCounts]:
    """Sum counts across JUnit XML files. Returns None if no test cases were found.

    A file that cannot be parsed (truncated because the runner was killed, a null
    byte, not XML at all, unreadable) is skipped rather than raised, but the number
    skipped is reported on stderr unless `quiet`: counts going missing or partial
    without a word is how a wrong card looks right.
    """
    total = passed = failed = skipped = 0
    failed_names = []
    unparseable = 0

    for path in paths:
        try:
            tree = ElementTree.parse(str(path))
        except (ElementTree.ParseError, OSError):
            unparseable += 1
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

    if unparseable and not quiet:
        print(
            "chatnotify: %d report file(s) could not be parsed "
            "(unreadable or not valid JUnit XML); their tests are not counted"
            % unparseable,
            file=sys.stderr,
        )

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

LOCK_FILENAME = ".chatnotify.lock"

#: A lock file older than this is assumed to belong to a crashed run and is
#: reclaimed. Generous on purpose: a long test suite must never lose its lock.
LOCK_STALE_SECONDS = 3600.0


def _warn(quiet: bool, message: str) -> None:
    if not quiet:
        print("chatnotify: " + message, file=sys.stderr)


def _match_files(root: str, patterns: Sequence[str]) -> List[str]:
    """Glob `patterns` under `root`; files only, deduplicated by normalized path."""
    found = set()
    for pattern in patterns:
        for match in glob.glob(os.path.join(root, pattern), recursive=True):
            if os.path.isfile(match):
                found.add(os.path.normpath(match))
    return sorted(found)


def _split_staleness(
    paths: List[str], cutoff: Optional[float], ceiling: Optional[float] = None
) -> Tuple[List[str], int, int]:
    """Partition `paths` by mtime window. Returns (kept, stale_count, future_count).

    `cutoff` rejects leftovers from a previous run. `ceiling` rejects the mirror
    image: a file stamped in the future by clock skew (NFS mounts, containers),
    which would otherwise always win the newest-set comparison and resurrect an
    ancient result as the current one.
    """
    if cutoff is None and ceiling is None:
        return paths, 0, 0
    kept = []
    stale = 0
    future = 0
    for path in paths:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if cutoff is not None and mtime < cutoff:
            stale += 1
        elif ceiling is not None and mtime > ceiling:
            future += 1
        else:
            kept.append(path)
    return kept, stale, future


def _newest_mtime(paths: List[str]) -> Tuple[Optional[float], List[str]]:
    """Newest mtime among `paths`, skipping any that vanished. Returns (mtime, alive).

    A report deleted between the glob and this comparison must not raise a
    traceback into the user's build log, so every `getmtime` here is guarded.
    `mtime` is None exactly when no path is still readable.
    """
    newest = None
    alive = []
    for path in paths:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        alive.append(path)
        if newest is None or mtime > newest:
            newest = mtime
    return newest, alive


_LOCK_ACQUIRED = "acquired"
_LOCK_HELD = "held"
_LOCK_UNAVAILABLE = "unavailable"


def _lock_is_abandoned(lock_path: str) -> bool:
    """True if the lock file looks like the debris of a crashed run and was removed."""
    try:
        age = time.time() - os.path.getmtime(lock_path)
    except OSError:
        return True  # It vanished under us; the holder is gone either way.
    if age <= LOCK_STALE_SECONDS:
        return False
    try:
        os.unlink(lock_path)
    except OSError:
        return False
    return True


def _acquire_lock(root: str, quiet: bool = False) -> Tuple[str, Optional[str]]:
    """Take the advisory discovery lock for `root`. Returns (state, lock_path).

    `O_CREAT | O_EXCL` makes creation atomic on both POSIX and Windows, so two
    concurrent runs in one directory cannot both believe they own discovery. A
    root the lock cannot be created in (read-only checkout, exotic filesystem)
    degrades to `_LOCK_UNAVAILABLE`: locking is advisory, and never a reason to
    stop the tool.
    """
    lock_path = os.path.join(root, LOCK_FILENAME)
    for attempt in (0, 1):
        try:
            handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if attempt == 0 and _lock_is_abandoned(lock_path):
                _warn(
                    quiet,
                    "reclaiming an abandoned %s (older than %d seconds)"
                    % (LOCK_FILENAME, int(LOCK_STALE_SECONDS)),
                )
                continue
            return _LOCK_HELD, lock_path
        except OSError:
            return _LOCK_UNAVAILABLE, None
        try:
            os.write(handle, ("%d\n" % os.getpid()).encode("ascii"))
        except OSError:
            pass
        finally:
            os.close(handle)
        return _LOCK_ACQUIRED, lock_path
    return _LOCK_HELD, lock_path


def _release_lock(lock_path: Optional[str]) -> None:
    if not lock_path:
        return
    try:
        os.unlink(lock_path)
    except OSError:
        pass


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
    A `since` also bounds the window from above, so a future-dated file cannot
    win the newest-set comparison.

    Auto-detection additionally takes an advisory lock on `root` for the duration
    of discovery (see `_acquire_lock`). If another run already holds it, nothing
    is returned: guessing which of two concurrent runs a report belongs to is how
    one run ends up announcing another's failures. An explicit `patterns` bypasses
    the lock entirely, because the user named the files and nothing is guessed.
    """
    cutoff = None if since is None else since - _MTIME_TOLERANCE_SECONDS
    ceiling = None if since is None else time.time() + _MTIME_TOLERANCE_SECONDS

    if patterns is not None:
        matched = _match_files(root, patterns)
        kept, stale, future = _split_staleness(matched, cutoff, ceiling)
        if stale:
            _warn(quiet, "ignoring %d stale report file(s) older than this run" % stale)
        if future:
            _warn(quiet, _future_message(future))
        if kept:
            _warn(quiet, "using %d report file(s)" % len(kept))
        return kept

    lock_state, lock_path = _acquire_lock(root, quiet=quiet)
    if lock_state == _LOCK_HELD:
        _warn(
            quiet,
            "another chatnotify run appears active in this directory (%s is held); "
            "auto-detected test counts would be unreliable, so no reports were read. "
            "Pass --report to name this run's report files explicitly." % LOCK_FILENAME,
        )
        return []

    try:
        return _autodetect(root, cutoff, ceiling, quiet)
    finally:
        if lock_state == _LOCK_ACQUIRED:
            _release_lock(lock_path)


def _future_message(count: int) -> str:
    return (
        "ignoring %d future-dated report file(s) (mtime ahead of this run — check for "
        "clock skew); a stale result must never be reported as current" % count
    )


def _autodetect(
    root: str, cutoff: Optional[float], ceiling: Optional[float], quiet: bool
) -> List[str]:
    """The set-based auto-detection body, run while the discovery lock is held."""
    candidates = []  # [(name, files, newest_mtime), ...]
    stale_total = 0
    future_total = 0
    for name, set_patterns in DEFAULT_GLOB_SETS:
        matched = _match_files(root, set_patterns)
        kept, stale, future = _split_staleness(matched, cutoff, ceiling)
        stale_total += stale
        future_total += future
        newest, alive = _newest_mtime(kept)
        if alive and newest is not None:
            candidates.append((name, alive, newest))

    if future_total:
        _warn(quiet, _future_message(future_total))

    if not candidates:
        # Filtering everything out and printing nothing leaves the user with a
        # card that has no test numbers and no way to find out why.
        if stale_total:
            _warn(
                quiet,
                "ignoring %d stale report file(s) older than this run" % stale_total,
            )
        return []

    winner_name, winner_files, _winner_mtime = max(candidates, key=lambda item: item[2])
    ignored_names = [name for name, _files, _mtime in candidates if name != winner_name]

    if ignored_names:
        _warn(
            quiet,
            "using '%s' reports (%d files); ignoring older sets: %s"
            % (winner_name, len(winner_files), ", ".join(ignored_names)),
        )
    else:
        _warn(quiet, "using '%s' reports (%d files)" % (winner_name, len(winner_files)))

    return sorted(winner_files)


def collect(
    root: str,
    patterns: Optional[Sequence[str]] = None,
    since: Optional[float] = None,
    quiet: bool = False,
) -> Optional[TestCounts]:
    """Discover reports then parse them. None means no counts are available."""
    found = discover(root, patterns=patterns, since=since, quiet=quiet)
    return parse_files(found, quiet=quiet)

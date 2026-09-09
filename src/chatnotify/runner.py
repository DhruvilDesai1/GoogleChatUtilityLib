"""Run the wrapped command. The child's stdio is inherited, its exit code untouched."""

import os
import shutil
import signal
import subprocess
import sys
import time
from typing import List, Optional, Sequence

from .models import RunResult

EXIT_NOT_FOUND = 127
EXIT_NOT_EXECUTABLE = 126
EXIT_INTERRUPTED = 130

_WINDOWS = os.name == "nt"
_SIGKILL = getattr(signal, "SIGKILL", getattr(signal, "SIGTERM", 15))


def _complain(quiet: bool, message: str) -> None:
    """Say why the command never ran. Silent under --quiet, and never raises."""
    if quiet:
        return
    try:
        print("chatnotify: %s" % message, file=sys.stderr)
    except Exception:
        pass


def _resolve_argv(argv: Sequence[str]) -> List[str]:
    """Return argv with argv[0] replaced by the executable a PATH lookup finds.

    Windows CreateProcess does not consult PATHEXT, so a bare `npm`, `npx`, `mvn`,
    `yarn` or `gradlew` - every one of them a .cmd/.bat shim - is otherwise simply
    not found. shutil.which is stdlib and PATHEXT-aware.

    When it finds nothing (a shell builtin, a typo, a path that does not exist) argv
    is passed to Popen untouched, so Popen's own error - and the exit code we map it
    to - stay exactly as they were.
    """
    command = list(argv)
    try:
        resolved = shutil.which(command[0])
    except Exception:
        return command
    if resolved:
        command[0] = resolved
    return command


def _isolation_kwargs() -> dict:
    """Popen kwargs that make the child the leader of its own process group.

    POSIX gets a new session: `killpg` then reaches every grandchild, and it costs
    nothing because `_forward_interrupt` hands the child the Ctrl+C itself.

    Windows deliberately gets nothing. CREATE_NEW_PROCESS_GROUP would stop the
    console delivering Ctrl+C to the child, and because `Popen.wait()` on Windows
    blocks in `WaitForSingleObject(INFINITE)` a pending SIGINT cannot surface in
    this process until the child exits - so an interactive Ctrl+C would appear to
    hang instead of stopping anything. `taskkill /T` sweeps the tree there and needs
    no process group at all.
    """
    if _WINDOWS:
        return {}
    return {"start_new_session": True}


def _start_child(command: Sequence[str], isolation: Optional[dict] = None):
    """Spawn `command` with our stdout/stderr inherited. Never uses a shell.

    Falls back to a plain spawn when the platform (or a stubbed Popen) rejects the
    isolation kwargs: leading its own process group is a bonus, never a precondition.
    """
    if isolation is None:
        isolation = _isolation_kwargs()
    if isolation:
        try:
            return subprocess.Popen(list(command), shell=False, **isolation)
        except FileNotFoundError:
            raise
        except (OSError, ValueError, TypeError, AttributeError, NotImplementedError):
            pass
    return subprocess.Popen(list(command), shell=False)


def _child_group(process) -> Optional[int]:
    """The child's *own* process group, or None when it has not got one.

    Returning None whenever the child shares our group is what stops a cleanup from
    signalling chatnotify - and the shell that launched it - instead of the child.
    """
    if _WINDOWS:
        return None
    try:
        group = os.getpgid(process.pid)
        if group == os.getpgid(0):
            return None
        return group
    except BaseException:
        return None


def _signal_group(group: int, sig) -> None:
    try:
        os.killpg(group, sig)
    except BaseException:
        pass


def _terminate(process) -> bool:
    try:
        process.terminate()
        return True
    except BaseException:
        return False


def _force_kill(process) -> None:
    try:
        process.kill()
    except BaseException:
        pass


def _reap(process, timeout: Optional[float]) -> bool:
    """Wait for the child. True once it is gone; never raises, not even on Ctrl+C."""
    try:
        process.wait(timeout=timeout)
        return True
    except BaseException:
        return False


def _still_running(process) -> bool:
    try:
        return process.poll() is None
    except BaseException:
        return False


def _taskkill_tree(process, timeout: float) -> bool:
    """Kill the child and every descendant with the Windows built-in. True on success.

    `taskkill /T` walks *live* parent links, so this has to run before the child
    dies: terminate the child first and its children are orphaned beyond reach.
    (A Job Object is more precise in theory and a great deal more ctypes to get
    wrong days before a release; taskkill ships with Windows.)
    """
    try:
        killer = subprocess.Popen(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            # taskkill's own chatter is not the wrapped command's output.
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return killer.wait(timeout=max(timeout, 5.0)) == 0
    except BaseException:
        return False


def _stop(process, grace_seconds: float) -> None:
    """Stop the child and everything it spawned. Best effort; it never raises.

    Nothing here may cost us the child's exit code - not an OS error, and not a
    second Ctrl+C arriving mid-shutdown - so every step swallows BaseException.
    """
    if _WINDOWS:
        if _taskkill_tree(process, grace_seconds):
            _reap(process, grace_seconds)
            if not _still_running(process):
                return
    else:
        group = _child_group(process)
        if group is not None:
            # The child leads its own group, so ask the whole tree politely first.
            _signal_group(group, signal.SIGTERM)
            _reap(process, grace_seconds)
            # Anything still in the group outlived its parent: an orphaned pytest
            # worker or a dev server sitting on a port. Sweep it.
            _signal_group(group, _SIGKILL)
            _reap(process, grace_seconds)
            if not _still_running(process):
                return

    # No group to work with, or the sweep did not take: fall back to exactly what
    # runner.py did before - terminate the child, then force it.
    if _terminate(process) and _reap(process, grace_seconds):
        return
    _force_kill(process)
    _reap(process, grace_seconds)


def _forward_interrupt(process) -> None:
    """Hand the interrupt we just took to the child, as the console used to.

    On POSIX the child now leads its own session, so the terminal's Ctrl+C no longer
    reaches it; without this an interactive `pytest` would lose its own interrupt
    output. On Windows the child still shares our console group and already had the
    Ctrl+C first-hand, so there is nothing to forward.
    """
    group = _child_group(process)
    if group is None:
        return
    _signal_group(group, signal.SIGINT)


def exec_command(
    argv: Sequence[str], grace_seconds: float = 5.0, quiet: bool = False
) -> RunResult:
    if not argv:
        return RunResult(exit_code=EXIT_NOT_FOUND, duration_seconds=0.0)

    started = time.monotonic()
    try:
        process = _start_child(_resolve_argv(argv))
    except FileNotFoundError:
        _complain(quiet, "command not found: %s" % argv[0])
        return RunResult(exit_code=EXIT_NOT_FOUND, duration_seconds=time.monotonic() - started)
    except (OSError, ValueError) as error:
        _complain(quiet, "could not execute %s: %s" % (argv[0], error))
        return RunResult(
            exit_code=EXIT_NOT_EXECUTABLE, duration_seconds=time.monotonic() - started
        )

    interrupted = False
    try:
        exit_code = process.wait()
    except KeyboardInterrupt:
        interrupted = True
        exit_code = EXIT_INTERRUPTED
        try:
            _forward_interrupt(process)
            _stop(process, grace_seconds)
        except BaseException:
            # Cleanup is best effort. A second Ctrl+C must never cost us the result:
            # cli.py has to get a RunResult back or the child's exit code is lost.
            pass

    return RunResult(
        exit_code=exit_code,
        duration_seconds=time.monotonic() - started,
        interrupted=interrupted,
    )

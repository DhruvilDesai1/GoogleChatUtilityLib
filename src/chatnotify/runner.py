"""Run the wrapped command. The child's stdio is inherited, its exit code untouched."""

import subprocess
import time
from typing import Sequence

from .models import RunResult

EXIT_NOT_FOUND = 127
EXIT_NOT_EXECUTABLE = 126
EXIT_INTERRUPTED = 130


def _stop(process, grace_seconds: float) -> None:
    """Ask the child to stop, then force it if needed. Never raises."""
    terminated = False
    try:
        process.terminate()
        terminated = True
    except Exception:
        pass

    if terminated:
        try:
            process.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            return

    try:
        process.kill()
        process.wait()
    except Exception:
        pass


def exec_command(argv: Sequence[str], grace_seconds: float = 5.0) -> RunResult:
    if not argv:
        return RunResult(exit_code=EXIT_NOT_FOUND, duration_seconds=0.0)

    started = time.monotonic()
    try:
        process = subprocess.Popen(list(argv), shell=False)
    except FileNotFoundError:
        return RunResult(exit_code=EXIT_NOT_FOUND, duration_seconds=time.monotonic() - started)
    except (OSError, ValueError):
        return RunResult(
            exit_code=EXIT_NOT_EXECUTABLE, duration_seconds=time.monotonic() - started
        )

    interrupted = False
    try:
        exit_code = process.wait()
    except KeyboardInterrupt:
        interrupted = True
        _stop(process, grace_seconds)
        exit_code = EXIT_INTERRUPTED

    return RunResult(
        exit_code=exit_code,
        duration_seconds=time.monotonic() - started,
        interrupted=interrupted,
    )

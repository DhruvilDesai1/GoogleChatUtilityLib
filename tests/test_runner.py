import os
import sys
import time

import pytest

from chatnotify import runner

POSIX_ONLY = pytest.mark.skipif(
    os.name == "nt", reason="POSIX process groups / killpg have no Windows equivalent"
)
WINDOWS_ONLY = pytest.mark.skipif(
    os.name != "nt", reason="taskkill is the Windows-only tree-kill path"
)


def python_command(code):
    return [sys.executable, "-c", code]


def write_shim(directory, name, exit_code=3, message="shim ran"):
    """A tiny executable shim: a `.cmd` on Windows (the npm/mvn/gradlew case), else a sh script."""
    if os.name == "nt":
        path = directory / (name + ".cmd")
        path.write_text("@echo off\r\necho %s\r\nexit /b %d\r\n" % (message, exit_code))
    else:
        path = directory / name
        path.write_text("#!/bin/sh\necho %s\nexit %d\n" % (message, exit_code))
        path.chmod(0o755)
    return path


def write_process_tree(directory):
    """A child that spawns a grandchild which appends a heartbeat to a file.

    Both self-terminate after ~10s so a failing test cannot leak processes forever.
    """
    (directory / "grandchild.py").write_text(
        "import sys, time\n"
        "for _ in range(200):\n"
        "    with open(sys.argv[1], 'a') as handle:\n"
        "        handle.write('beat\\n')\n"
        "    time.sleep(0.05)\n"
    )
    parent = directory / "parent.py"
    parent.write_text(
        "import os, subprocess, sys, time\n"
        "here = os.path.dirname(os.path.abspath(__file__))\n"
        "subprocess.Popen([sys.executable, os.path.join(here, 'grandchild.py'), sys.argv[1]])\n"
        "time.sleep(12)\n"
    )
    return parent


def test_successful_command_returns_zero():
    result = runner.exec_command(python_command("pass"))
    assert result.exit_code == 0
    assert result.interrupted is False


def test_failing_exit_code_is_passed_through_unchanged():
    result = runner.exec_command(python_command("import sys; sys.exit(7)"))
    assert result.exit_code == 7


def test_duration_is_measured():
    result = runner.exec_command(python_command("import time; time.sleep(0.2)"))
    assert result.duration_seconds >= 0.15


def test_missing_executable_returns_127():
    result = runner.exec_command(["definitely-not-a-real-binary-xyz"])
    assert result.exit_code == 127
    assert result.interrupted is False


def test_child_stdout_reaches_the_terminal(capfd):
    runner.exec_command(python_command("print('hello from child')"))
    assert "hello from child" in capfd.readouterr().out


def test_child_stderr_reaches_the_terminal(capfd):
    runner.exec_command(python_command("import sys; print('oops', file=sys.stderr)"))
    assert "oops" in capfd.readouterr().err


def test_keyboard_interrupt_marks_result_interrupted(monkeypatch):
    class FakeProcess:
        def __init__(self):
            self.terminated = False

        def wait(self, timeout=None):
            if not self.terminated:
                raise KeyboardInterrupt()
            return 130

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.terminated = True

    fake = FakeProcess()
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: fake)
    result = runner.exec_command(["anything"])
    assert result.interrupted is True
    assert result.exit_code == 130
    assert fake.terminated is True, "_stop must be called so the child cannot be orphaned"


def test_kill_is_attempted_when_terminate_raises(monkeypatch):
    """A terminate() that fails must not skip the force-kill."""
    events = []

    class UnterminatableProcess:
        def wait(self, timeout=None):
            if not events:
                raise KeyboardInterrupt()
            return 137

        def terminate(self):
            events.append("terminate-failed")
            raise OSError("cannot terminate")

        def kill(self):
            events.append("kill")

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: UnterminatableProcess())
    result = runner.exec_command(["anything"])
    assert "kill" in events, "kill must be attempted when terminate raises"
    assert result.interrupted is True


def test_unkillable_child_is_force_killed(monkeypatch):
    events = []

    class StubbornProcess:
        def wait(self, timeout=None):
            if not events:
                raise KeyboardInterrupt()
            if events == ["terminate"]:
                events.append("timeout")
                raise runner.subprocess.TimeoutExpired(cmd="x", timeout=1)
            return 137

        def terminate(self):
            events.append("terminate")

        def kill(self):
            events.append("kill")

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: StubbornProcess())
    runner.exec_command(["anything"], grace_seconds=0.01)
    assert "kill" in events


def test_empty_argv_returns_127_without_raising():
    assert runner.exec_command([]).exit_code == 127


# --- Fix 1: PATHEXT resolution and diagnostics on the failure paths ------------------


def test_shim_on_path_is_found_and_its_exit_code_returned(tmp_path, monkeypatch, capfd):
    """`npm`/`mvn`/`gradlew` are .cmd shims; CreateProcess does not consult PATHEXT."""
    write_shim(tmp_path, "chatnotify-shim", exit_code=3)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    result = runner.exec_command(["chatnotify-shim"])
    assert result.exit_code == 3
    assert "shim ran" in capfd.readouterr().out


def test_absolute_path_to_a_shim_still_runs(tmp_path):
    shim = write_shim(tmp_path, "abs-shim", exit_code=4)
    assert runner.exec_command([str(shim)]).exit_code == 4


def test_relative_path_to_a_shim_still_runs(tmp_path, monkeypatch):
    shim = write_shim(tmp_path, "rel-shim", exit_code=5)
    monkeypatch.chdir(tmp_path)
    assert runner.exec_command([os.path.join(".", shim.name)]).exit_code == 5


def test_missing_command_says_so_on_stderr(capfd):
    result = runner.exec_command(["definitely-not-a-real-binary-xyz"])
    assert result.exit_code == 127
    captured = capfd.readouterr().err
    assert "definitely-not-a-real-binary-xyz" in captured
    assert "not found" in captured.lower()


def test_quiet_suppresses_the_not_found_diagnostic(capfd):
    result = runner.exec_command(["definitely-not-a-real-binary-xyz"], quiet=True)
    assert result.exit_code == 127
    assert capfd.readouterr().err == ""


def test_unrunnable_file_returns_126_and_says_so(tmp_path, capfd):
    if os.name == "nt":
        target = tmp_path / "not-an-exe.dat"
        target.write_text("this is not a Win32 application")
    else:
        target = tmp_path / "not-an-exe"
        target.write_text("#!/bin/sh\necho hi\n")
        target.chmod(0o644)
    result = runner.exec_command([str(target)])
    assert result.exit_code == 126
    assert "not-an-exe" in capfd.readouterr().err


def test_child_stdio_stays_inherited_and_no_shell_is_used(monkeypatch):
    """Guards the two properties runner.py exists for: no PIPE, never a shell."""
    seen = {}

    class Child:
        def wait(self, timeout=None):
            return 0

    def fake_popen(args, **kwargs):
        seen["kwargs"] = kwargs
        return Child()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    runner.exec_command(python_command("pass"))
    assert seen["kwargs"].get("shell") is False
    for stream in ("stdin", "stdout", "stderr"):
        assert stream not in seen["kwargs"], "the child's stdio must stay inherited"


# --- Fix 2: a second Ctrl+C must not discard the child's result ----------------------


def test_second_interrupt_during_shutdown_still_returns_a_result(monkeypatch):
    """Ctrl+C pressed again while we are shutting the child down must not escape."""

    class DoublyInterrupted:
        def __init__(self):
            self.waits = 0
            self.killed = False

        def wait(self, timeout=None):
            self.waits += 1
            raise KeyboardInterrupt()

        def terminate(self):
            pass

        def kill(self):
            self.killed = True

    fake = DoublyInterrupted()
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: fake)
    result = runner.exec_command(["anything"])
    assert result.interrupted is True
    assert result.exit_code == 130
    assert fake.waits >= 2, "the interrupt must have arrived during _stop's own wait"
    assert fake.killed is True, "a second interrupt should force the child, not abandon it"


# --- Fix 3: nothing the child spawned may outlive the run ----------------------------


class InterruptedRun:
    """A real child process whose first wait() raises, as a console Ctrl+C would.

    Only the interrupt's *delivery* is simulated: the tree, the signals and the
    killing are all real. (A real console Ctrl+C cannot be delivered under pytest,
    and on Windows a pending SIGINT cannot even surface from a blocking wait().)
    """

    def __init__(self, process, before_interrupt):
        self._process = process
        self._before_interrupt = before_interrupt
        self._raised = False

    def __getattr__(self, name):
        return getattr(self._process, name)

    def wait(self, timeout=None):
        if not self._raised:
            self._raised = True
            self._before_interrupt()
            raise KeyboardInterrupt()
        return self._process.wait(timeout=timeout)


def test_grandchild_does_not_outlive_an_interrupted_run(tmp_path, monkeypatch):
    beats = tmp_path / "beats.txt"
    parent = write_process_tree(tmp_path)

    def let_the_tree_come_up():
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if beats.exists() and beats.read_text():
                return
            time.sleep(0.05)
        raise AssertionError("the grandchild never started; this test would prove nothing")

    real_popen = runner.subprocess.Popen
    wrapped = []

    def popen(*args, **kwargs):
        """Wrap only the run's own child; runner's cleanup spawns must be untouched."""
        process = real_popen(*args, **kwargs)
        if wrapped:
            return process
        wrapped.append(process)
        return InterruptedRun(process, let_the_tree_come_up)

    monkeypatch.setattr(runner.subprocess, "Popen", popen)

    result = runner.exec_command(
        [sys.executable, str(parent), str(beats)], grace_seconds=2.0
    )
    assert result.interrupted is True

    time.sleep(0.3)  # let the last signal land before taking the baseline
    settled = beats.read_text()
    assert settled, "the grandchild wrote nothing; this test would prove nothing"
    time.sleep(0.8)
    assert beats.read_text() == settled, "grandchild survived: its heartbeat kept advancing"


@POSIX_ONLY
def test_child_leads_its_own_process_group(tmp_path):
    process = runner._start_child(python_command("import time; time.sleep(10)"))
    try:
        assert os.getpgid(process.pid) != os.getpgid(0)
    finally:
        process.kill()
        process.wait()


@POSIX_ONLY
def test_interrupt_is_forwarded_to_the_childs_own_group(monkeypatch):
    """The child no longer shares our terminal's group, so hand it the interrupt."""
    import signal

    sent = []
    monkeypatch.setattr(runner.os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    monkeypatch.setattr(runner.os, "getpgid", lambda pid: 1 if pid == 0 else 4242)

    class Child:
        pid = 99

        def wait(self, timeout=None):
            if not sent:
                raise KeyboardInterrupt()
            return 0

        def terminate(self):
            pass

        def kill(self):
            pass

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: Child())
    runner.exec_command(["anything"])
    assert sent[0] == (4242, signal.SIGINT), "the child's group must get the interrupt first"
    assert all(pgid == 4242 for pgid, _ in sent), "chatnotify's own group must never be signalled"


@POSIX_ONLY
def test_a_child_sharing_our_group_is_never_signalled_as_a_group(monkeypatch):
    """If the session could not be created, fall back to child-only cleanup."""
    import signal

    killed_groups = []
    monkeypatch.setattr(runner.os, "killpg", lambda pgid, sig: killed_groups.append(pgid))
    monkeypatch.setattr(runner.os, "getpgid", lambda pid: 777)  # child shares our group
    events = []

    class Child:
        pid = 99

        def wait(self, timeout=None):
            if not events:
                raise KeyboardInterrupt()
            return 0

        def terminate(self):
            events.append("terminate")

        def kill(self):
            events.append("kill")

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: Child())
    result = runner.exec_command(["anything"])
    assert killed_groups == []
    assert "terminate" in events
    assert result.exit_code == 130
    assert signal.SIGTERM is not None  # keeps the import honest


@WINDOWS_ONLY
def test_tree_is_swept_before_the_child_is_terminated(monkeypatch):
    """taskkill /T walks live parent links, so the child must not die first."""
    events = []

    class Child:
        pid = 4242

        def wait(self, timeout=None):
            if not events:
                raise KeyboardInterrupt()
            return 0

        def terminate(self):
            events.append("terminate")

        def kill(self):
            events.append("kill")

    class Killer:
        def wait(self, timeout=None):
            return 0

    def fake_popen(args, **kwargs):
        argv = list(args)
        if argv[:1] == ["taskkill"]:
            events.append(" ".join(argv))
            return Killer()
        return Child()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    result = runner.exec_command(["anything"])
    assert events, "no cleanup was attempted at all"
    assert events[0].startswith("taskkill"), "the tree must be swept before the child dies"
    assert "/T" in events[0] and "4242" in events[0]
    assert result.exit_code == 130


@WINDOWS_ONLY
def test_failing_taskkill_falls_back_to_killing_the_child(monkeypatch):
    events = []

    class Child:
        pid = 4242

        def wait(self, timeout=None):
            if not events:
                raise KeyboardInterrupt()
            if events == ["taskkill-exploded", "terminate"]:
                raise runner.subprocess.TimeoutExpired(cmd="x", timeout=1)
            return 0

        def terminate(self):
            events.append("terminate")

        def kill(self):
            events.append("kill")

    def fake_popen(args, **kwargs):
        if list(args)[:1] == ["taskkill"]:
            events.append("taskkill-exploded")
            raise OSError("taskkill is missing")
        return Child()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    result = runner.exec_command(["anything"], grace_seconds=0.01)
    assert "terminate" in events and "kill" in events
    assert result.interrupted is True
    assert result.exit_code == 130

import sys

from chatnotify import runner


def python_command(code):
    return [sys.executable, "-c", code]


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

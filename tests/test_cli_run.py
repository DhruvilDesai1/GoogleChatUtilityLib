import signal
import sys

from chatnotify import cli

PY = sys.executable


def base_env(webhook):
    return {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CHATNOTIFY_ENABLED": "1"}


def test_split_argv_separates_own_flags_from_command():
    own, command = cli.split_argv(["run", "--project", "X", "--", "pytest", "-v"])
    assert own == ["run", "--project", "X"]
    assert command == ["pytest", "-v"]


def test_split_argv_with_no_separator_yields_empty_command():
    own, command = cli.split_argv(["run", "--project", "X"])
    assert own == ["run", "--project", "X"]
    assert command == []


def test_split_argv_keeps_double_dash_inside_child_command():
    own, command = cli.split_argv(["run", "--", "pytest", "--", "-k", "x"])
    assert command == ["pytest", "--", "-k", "x"]


def test_run_without_command_returns_usage_error(capsys):
    assert cli.main(["run", "--project", "X"]) == cli.EXIT_USAGE
    assert "no command" in capsys.readouterr().err


def test_exit_code_of_child_is_returned(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    code = cli.main(["run", "--project", "X", "--", PY, "-c", "import sys; sys.exit(3)"])
    assert code == 3


def test_start_and_finish_cards_are_both_posted(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    cli.main(["run", "--project", "X", "--", PY, "-c", "pass"])
    assert len(webhook.requests) == 2
    assert webhook.requests[0]["body"]["cardsV2"][0]["card"]["header"]["subtitle"] == "Started"
    assert webhook.requests[1]["body"]["cardsV2"][0]["card"]["header"]["subtitle"] == "Passed"


def test_both_messages_share_one_thread_key(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    cli.main(["run", "--project", "X", "--", PY, "-c", "pass"])
    first = webhook.requests[0]["path"]
    second = webhook.requests[1]["path"]
    assert "threadKey=" in first
    assert first.split("threadKey=")[1] == second.split("threadKey=")[1]


def test_counts_from_report_appear_in_finish_card(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    report = tmp_path / "junit.xml"
    code = (
        "open(r'%s','w').write('<testsuite tests=\\'1\\'>"
        "<testcase classname=\\'c\\' name=\\'t\\'/></testsuite>')" % report
    )
    cli.main(["run", "--project", "X", "--", PY, "-c", code])
    rendered = str(webhook.requests[1]["body"])
    assert "Total Tests" in rendered


def test_unreachable_webhook_does_not_change_exit_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": "http://127.0.0.1:1/hook", "CHATNOTIFY_ENABLED": "1"},
    )
    monkeypatch.setattr("chatnotify.transport.time.sleep", lambda _: None)
    assert cli.main(["run", "--", PY, "-c", "import sys; sys.exit(4)"]) == 4


def test_missing_webhook_still_runs_the_command(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {"CHATNOTIFY_ENABLED": "1"})
    assert cli.main(["run", "--", PY, "-c", "import sys; sys.exit(5)"]) == 5
    assert "webhook" in capsys.readouterr().err.lower()


def test_disabled_posts_nothing_but_still_runs(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CHATNOTIFY_DISABLED": "1"},
    )
    assert cli.main(["run", "--", PY, "-c", "import sys; sys.exit(6)"]) == 6
    assert webhook.requests == []


def test_only_on_failure_suppresses_both_cards_when_passing(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    cli.main(["run", "--only-on-failure", "--", PY, "-c", "pass"])
    assert webhook.requests == []


def test_only_on_failure_posts_finish_card_when_failing(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    cli.main(["run", "--only-on-failure", "--", PY, "-c", "import sys; sys.exit(1)"])
    assert len(webhook.requests) == 1
    assert webhook.requests[0]["body"]["cardsV2"][0]["card"]["header"]["subtitle"] == "Failed"


def test_sigterm_handler_is_installed_around_the_child_and_restored_after(
    tmp_path, webhook, monkeypatch
):
    """A SIGTERM handler must be in place while the child runs, and gone once `run` returns."""
    from chatnotify.models import RunResult

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    previous = signal.getsignal(signal.SIGTERM)
    seen = {}

    def fake_exec(command, quiet=False, **kwargs):
        seen["during"] = signal.getsignal(signal.SIGTERM)
        return RunResult(exit_code=0, duration_seconds=0.0)

    monkeypatch.setattr(cli.runner, "exec_command", fake_exec)
    try:
        cli.main(["run", "--project", "X", "--", "ignored-command"])
        assert seen["during"] is not previous
        assert signal.getsignal(signal.SIGTERM) is previous
    finally:
        signal.signal(signal.SIGTERM, previous)


# --- Fix 1: the never-fatal guard must cover the whole notification prologue ---


def test_config_load_failure_still_runs_the_command(tmp_path, monkeypatch, capsys):
    """A broken config layer is a notification problem; the child must still run."""

    def explode(*args, **kwargs):
        raise FileNotFoundError("cwd is gone")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.config, "load", explode)
    assert cli.main(["run", "--", PY, "-c", "import sys; sys.exit(7)"]) == 7
    assert "notification" in capsys.readouterr().err.lower()


def test_render_start_failure_still_runs_the_command(tmp_path, webhook, monkeypatch, capsys):
    """A bug in card rendering must not stop the wrapped command from running."""

    def explode(*args, **kwargs):
        raise RuntimeError("render exploded")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    monkeypatch.setattr(cli.render, "start", explode)
    assert cli.main(["run", "--", PY, "-c", "import sys; sys.exit(7)"]) == 7
    assert "notification" in capsys.readouterr().err.lower()
    assert webhook.requests == []


def test_prologue_guard_still_lets_keyboard_interrupt_through(tmp_path, monkeypatch):
    """The guard swallows bugs, not the user's Ctrl+C."""

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.config, "load", interrupt)
    try:
        cli.main(["run", "--", PY, "-c", "pass"])
    except KeyboardInterrupt:
        return
    raise AssertionError("KeyboardInterrupt was swallowed by the prologue guard")


def test_report_collection_failure_still_returns_the_child_exit_code(
    tmp_path, webhook, monkeypatch, capsys
):
    """The finish half of the notification is guarded too; the exit code stands."""

    def explode(*args, **kwargs):
        raise OSError("cwd is gone")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    monkeypatch.setattr(cli.reports, "collect", explode)
    assert cli.main(["run", "--", PY, "-c", "import sys; sys.exit(7)"]) == 7
    assert "exit code stands" in capsys.readouterr().err


# --- Fix 3: the child's argv must not publish secrets ---


def test_redaction_leaves_ordinary_commands_untouched():
    command = ["pytest", "tests/", "--junitxml=junit.xml", "-k", "not slow"]
    assert cli._redact_command(command, None) == "pytest tests/ --junitxml=junit.xml -k not slow"


def test_redaction_masks_query_parameter_secrets():
    rendered = cli._redact_command(["curl", "https://api.example/v1?key=SECRETKEY123"], None)
    assert "SECRETKEY123" not in rendered
    assert "key=***" in rendered


def test_redaction_masks_assignment_style_secrets():
    rendered = cli._redact_command(["deploy", "--token=hunter2", "PASSWORD=letmein"], None)
    assert "hunter2" not in rendered
    assert "letmein" not in rendered


def test_redaction_masks_the_value_after_a_secret_flag():
    rendered = cli._redact_command(["tool", "--api-key", "AKIAsecret", "--verbose"], None)
    assert "AKIAsecret" not in rendered
    assert "--verbose" in rendered


def test_redaction_masks_the_configured_webhook_url():
    url = "https://chat.googleapis.com/v1/spaces/S/messages?key=K&token=T"
    rendered = cli._redact_command(["post-hook", url], url)
    assert "chat.googleapis.com" not in rendered
    assert "***" in rendered


def test_misordered_secret_flags_never_reach_the_card(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    cli.main(
        [
            "run",
            "--",
            PY,
            "-c",
            "pass",
            "--webhook-url",
            "https://chat.googleapis.com/v1/spaces/S?key=SECRETKEY123",
            "--token",
            "hunter2",
        ]
    )
    rendered = str(webhook.requests)
    assert "SECRETKEY123" not in rendered
    assert "hunter2" not in rendered


# --- Fix 4: POSIX signal exit codes follow shell convention ---


def _stub_exit_code(monkeypatch, code):
    from chatnotify.models import RunResult

    def fake_exec(command, quiet=False, **kwargs):
        return RunResult(exit_code=code, duration_seconds=0.0)

    monkeypatch.setattr(cli.runner, "exec_command", fake_exec)


def test_sigkill_exit_code_becomes_137(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    _stub_exit_code(monkeypatch, -9)
    assert cli.main(["run", "--", "ignored"]) == 137


def test_sigsegv_exit_code_becomes_139(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    _stub_exit_code(monkeypatch, -11)
    assert cli.main(["run", "--", "ignored"]) == 139


def test_positive_exit_code_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    _stub_exit_code(monkeypatch, 3)
    assert cli.main(["run", "--", "ignored"]) == 3


# --- Fix 9: --quiet reaches the runner diagnostics ---


def test_quiet_suppresses_command_not_found_diagnostic(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    assert cli.main(["run", "--quiet", "--", "definitely-not-a-real-binary-xyz"]) == 127
    assert "command not found" not in capsys.readouterr().err


def test_without_quiet_the_command_not_found_diagnostic_is_printed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    assert cli.main(["run", "--", "definitely-not-a-real-binary-xyz"]) == 127
    assert "command not found" in capsys.readouterr().err


def test_version_flag_prints_version(capsys):
    try:
        cli.main(["--version"])
    except SystemExit:
        pass
    assert "2.0.0" in capsys.readouterr().out


def test_entrypoint_exits_two_when_crash_precedes_child(monkeypatch, capsys):
    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "main", explode)
    try:
        cli.entrypoint()
    except SystemExit as exit_signal:
        assert exit_signal.code == cli.EXIT_USAGE
    assert "boom" in capsys.readouterr().err

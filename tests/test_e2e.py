import json
import os
import subprocess
import sys

SUITE = """
def test_passes():
    assert True


def test_also_passes():
    assert True


def test_fails():
    assert 1 == 2


def test_skipped():
    import pytest
    pytest.skip("not ready")
"""


def run_cli(cwd, env, *args):
    command = [sys.executable, "-m", "chatnotify"] + list(args)
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)


def test_real_pytest_run_produces_accurate_cards(tmp_path, webhook):
    (tmp_path / "test_sample.py").write_text(SUITE, encoding="utf-8")
    env = dict(os.environ)
    env["CHATNOTIFY_WEBHOOK_URL"] = webhook.url
    env["CHATNOTIFY_ENABLED"] = "1"
    env["CHATNOTIFY_PROJECT"] = "E2E Suite"

    completed = run_cli(
        str(tmp_path),
        env,
        "run",
        "--",
        sys.executable,
        "-m",
        "pytest",
        "test_sample.py",
        "--junitxml=junit.xml",
    )

    assert completed.returncode == 1, completed.stderr
    assert len(webhook.requests) == 2

    start = webhook.requests[0]["body"]["cardsV2"][0]["card"]
    assert start["header"]["title"] == "E2E Suite"
    assert start["header"]["subtitle"] == "Started"

    finish_card = webhook.requests[1]["body"]["cardsV2"][0]["card"]
    assert finish_card["header"]["subtitle"] == "Failed"

    widgets = [w for section in finish_card["sections"] for w in section.get("widgets", [])]
    labelled = {
        w["decoratedText"]["topLabel"]: w["decoratedText"]["text"]
        for w in widgets
        if "decoratedText" in w
    }
    assert labelled["Total Tests"] == "4"
    assert labelled["Passed"] == "2"
    assert labelled["Failed"] == "1"
    assert labelled["Skipped"] == "1"

    paragraphs = " ".join(
        w["textParagraph"]["text"] for w in widgets if "textParagraph" in w
    )
    assert "test_fails" in paragraphs


def test_plain_script_reports_exit_code_only(tmp_path, webhook):
    (tmp_path / "job.py").write_text("import sys; sys.exit(0)", encoding="utf-8")
    env = dict(os.environ)
    env["CHATNOTIFY_WEBHOOK_URL"] = webhook.url
    env["CHATNOTIFY_ENABLED"] = "1"

    completed = run_cli(str(tmp_path), env, "run", "--project", "ETL", "--", sys.executable, "job.py")

    assert completed.returncode == 0
    finish = json.dumps(webhook.requests[1]["body"])
    assert '"subtitle": "Passed"' in finish
    assert "Exit Code" in finish
    assert "Total Tests" not in finish


def test_stale_report_is_not_reported_as_current(tmp_path, webhook):
    stale = tmp_path / "junit.xml"
    stale.write_text(
        '<testsuite tests="9"><testcase classname="old" name="stale"/></testsuite>',
        encoding="utf-8",
    )
    os.utime(str(stale), (0, 0))
    (tmp_path / "job.py").write_text("pass", encoding="utf-8")

    env = dict(os.environ)
    env["CHATNOTIFY_WEBHOOK_URL"] = webhook.url
    env["CHATNOTIFY_ENABLED"] = "1"

    run_cli(str(tmp_path), env, "run", "--project", "Stale", "--", sys.executable, "job.py")

    finish = json.dumps(webhook.requests[1]["body"])
    assert "stale" not in finish
    assert "Total Tests" not in finish


def test_child_output_is_not_swallowed(tmp_path):
    (tmp_path / "loud.py").write_text("print('CHILD SPEAKING')", encoding="utf-8")
    env = dict(os.environ)
    env["CHATNOTIFY_DISABLED"] = "1"
    completed = run_cli(str(tmp_path), env, "run", "--", sys.executable, "loud.py")
    assert "CHILD SPEAKING" in completed.stdout

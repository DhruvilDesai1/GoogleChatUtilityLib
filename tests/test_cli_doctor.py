from chatnotify import cli


def test_doctor_reports_provenance_for_each_value(tmp_path, webhook, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".chatnotify.ini").write_text("[chatnotify]\nproject = FromIni\n", encoding="utf-8")
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CHATNOTIFY_ENV": "staging", "CI": "true"},
    )
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "FromIni" in out
    assert ".chatnotify.ini" in out
    assert "staging" in out
    assert "env: CHATNOTIFY_ENV" in out
    assert "CI detected" in out


def test_doctor_sends_a_test_card(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CI": "true"},
    )
    cli.main(["doctor"])
    assert len(webhook.requests) == 1


def test_doctor_never_prints_the_webhook_url(tmp_path, webhook, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CI": "true"},
    )
    cli.main(["doctor"])
    captured = capsys.readouterr()
    assert "SECRET123" not in captured.out
    assert "SECRET123" not in captured.err


def test_doctor_returns_one_when_no_webhook_configured(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    assert cli.main(["doctor"]) == 1
    assert "not configured" in capsys.readouterr().out


def test_doctor_returns_one_when_webhook_unreachable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ", {"CHATNOTIFY_WEBHOOK_URL": "http://127.0.0.1:1/h"}
    )
    monkeypatch.setattr("chatnotify.transport.time.sleep", lambda _: None)
    assert cli.main(["doctor"]) == 1


def test_doctor_prints_version_and_machine_config_path(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "2.0.0" in out
    assert "config.ini" in out

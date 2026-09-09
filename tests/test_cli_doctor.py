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


# --- Fix 5: doctor accepts the shared configuration flags ---


def test_doctor_uses_webhook_url_from_the_flag(tmp_path, webhook, monkeypatch, capsys):
    """You must be able to test a webhook URL before committing it to config."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    assert cli.main(["doctor", "--webhook-url", webhook.url]) == 0
    assert len(webhook.requests) == 1
    assert "flag" in capsys.readouterr().out


def test_doctor_accepts_project_and_env_flags(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    cli.main(["doctor", "--project", "Flagged", "--env", "prod"])
    out = capsys.readouterr().out
    assert "Flagged" in out
    assert "prod" in out


# --- Fix 6: doctor is honest about CHATNOTIFY_DISABLED ---


def test_doctor_sends_test_card_even_when_disabled_and_says_so(
    tmp_path, webhook, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CHATNOTIFY_DISABLED": "1"},
    )
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "CHATNOTIFY_DISABLED" in out
    assert "disabled" in out.lower()
    assert "sending a test card anyway" in out.lower()
    assert len(webhook.requests) == 1


# --- Fix 7: the mask identifies the URL instead of hiding a wrong one ---


def test_doctor_mask_reveals_scheme_and_host_but_not_the_credential(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": "http://intranet.evil.local/collect?x=SECRETVALUE"},
    )
    monkeypatch.setattr(cli.transport, "post", lambda *args, **kwargs: False)
    cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "http://intranet.evil.local/..." in out
    assert "SECRETVALUE" not in out
    assert "collect" not in out


def test_doctor_mask_of_a_google_chat_url_shows_the_expected_host(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": "https://chat.googleapis.com/v1/spaces/S/messages?key=SEKRIT"},
    )
    monkeypatch.setattr(cli.transport, "post", lambda *args, **kwargs: False)
    cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "https://chat.googleapis.com/..." in out
    assert "SEKRIT" not in out


def test_doctor_prints_version_and_machine_config_path(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "2.0.0" in out
    assert "config.ini" in out

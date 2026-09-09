import urllib.error

import pytest

from chatnotify import transport


def test_successful_post_returns_true_and_delivers_payload(webhook):
    assert transport.post(webhook.url, {"text": "hello"}) is True
    assert len(webhook.requests) == 1
    assert webhook.requests[0]["body"] == {"text": "hello"}


def test_thread_key_is_appended_to_query(webhook):
    transport.post(webhook.url, {"text": "hi"}, thread_key="run-42")
    path = webhook.requests[0]["path"]
    assert "threadKey=run-42" in path
    assert "messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD" in path
    assert "key=SECRET123" in path


def test_client_error_returns_false_without_raising(webhook):
    webhook.default_status = 404
    assert transport.post(webhook.url, {"text": "hi"}) is False


def test_client_error_is_not_retried(webhook):
    webhook.default_status = 403
    transport.post(webhook.url, {"text": "hi"}, sleep=lambda _: None)
    assert len(webhook.requests) == 1


def test_rate_limit_is_retried_then_succeeds(webhook):
    webhook.status_queue = [429, 200]
    delays = []
    assert transport.post(webhook.url, {"text": "hi"}, sleep=delays.append) is True
    assert len(webhook.requests) == 2
    assert delays == [1.0]


def test_retries_give_up_after_two_attempts(webhook):
    webhook.default_status = 503
    delays = []
    assert transport.post(webhook.url, {"text": "hi"}, sleep=delays.append) is False
    assert len(webhook.requests) == 3
    assert delays == [1.0, 4.0]


def test_connection_refused_returns_false():
    url = "http://127.0.0.1:1/webhook"
    assert transport.post(url, {"text": "hi"}, sleep=lambda _: None) is False


def test_unserialisable_payload_returns_false_without_raising(webhook):
    assert transport.post(webhook.url, {"bad": object()}) is False


def test_webhook_url_never_appears_in_stderr(monkeypatch, capsys):
    """An exception whose text embeds the URL must not leak it into logs."""
    url = "https://chat.example/webhook?key=SUPERSECRET"

    def leaky_urlopen(*args, **kwargs):
        raise urllib.error.URLError("failed opening %s" % url)

    monkeypatch.setattr(transport, "_open",leaky_urlopen)
    assert transport.post(url, {"text": "hi"}, sleep=lambda _: None) is False
    captured = capsys.readouterr()
    assert "SUPERSECRET" not in captured.err
    assert "SUPERSECRET" not in captured.out


def test_keyboard_interrupt_propagates(monkeypatch):
    """Ctrl-C is a request to stop, not a webhook failure to swallow."""
    def interrupted_urlopen(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(transport, "_open",interrupted_urlopen)
    with pytest.raises(KeyboardInterrupt):
        transport.post("https://chat.example/hook", {"text": "hi"}, sleep=lambda _: None)


def test_quiet_suppresses_warnings(webhook, capsys):
    webhook.default_status = 404
    transport.post(webhook.url, {"text": "hi"}, quiet=True)
    assert capsys.readouterr().err == ""


# --- Fix 1: redirects must not be silently followed, scheme must be validated ---


def test_redirect_is_not_followed_and_reports_failure(webhook):
    """A 302 must be treated as a delivery failure, not silently followed to another host."""
    webhook.redirect_to = "/elsewhere"
    assert transport.post(webhook.url, {"text": "hi"}, sleep=lambda _: None) is False
    assert len(webhook.requests) == 1
    assert webhook.get_requests == []


def test_rejects_non_http_scheme(capsys):
    delays = []
    assert transport.post("file:///etc/passwd", {"text": "hi"}, sleep=delays.append) is False
    assert delays == []
    err = capsys.readouterr().err
    assert "file" in err
    assert "/etc/passwd" not in err


def test_http_to_non_loopback_host_warns_but_still_attempts(monkeypatch, capsys):
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=None):
        return FakeResponse()

    monkeypatch.setattr(transport, "_open",fake_urlopen)
    assert transport.post("http://example.com/webhook", {"text": "hi"}) is True
    err = capsys.readouterr().err.lower()
    assert "http" in err or "unencrypted" in err or "cleartext" in err


def test_http_to_loopback_does_not_warn(webhook, capsys):
    transport.post(webhook.url, {"text": "hi"})
    assert capsys.readouterr().err == ""


# --- Fix 2: a total wall-clock budget bounds retries; permanent errors are not retried ---


def test_total_budget_exceeded_before_backoff_gives_up(webhook):
    webhook.default_status = 503
    delays = []
    times = iter([0.0, 0.0, 25.0])
    result = transport.post(
        webhook.url, {"text": "hi"}, sleep=delays.append, monotonic=lambda: next(times)
    )
    assert result is False
    assert len(webhook.requests) == 1
    assert delays == []


def test_total_budget_exceeded_before_second_attempt_gives_up(webhook):
    webhook.default_status = 503
    delays = []
    times = iter([0.0, 0.0, 5.0, 25.0])
    result = transport.post(
        webhook.url, {"text": "hi"}, sleep=delays.append, monotonic=lambda: next(times)
    )
    assert result is False
    assert len(webhook.requests) == 1
    assert delays == [1.0]


def test_malformed_url_value_error_is_not_retried(monkeypatch):
    def bad_urlopen(*args, **kwargs):
        raise ValueError("unknown url type: 'http'")

    monkeypatch.setattr(transport, "_open",bad_urlopen)
    delays = []
    result = transport.post("https://chat.example/hook", {"text": "hi"}, sleep=delays.append)
    assert result is False
    assert delays == []

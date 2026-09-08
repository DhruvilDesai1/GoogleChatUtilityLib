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


def test_webhook_url_never_appears_in_stderr(capsys):
    url = "http://127.0.0.1:1/webhook?key=SUPERSECRET"
    transport.post(url, {"text": "hi"}, sleep=lambda _: None)
    captured = capsys.readouterr()
    assert "SUPERSECRET" not in captured.err
    assert "SUPERSECRET" not in captured.out


def test_quiet_suppresses_warnings(webhook, capsys):
    webhook.default_status = 404
    transport.post(webhook.url, {"text": "hi"}, quiet=True)
    assert capsys.readouterr().err == ""

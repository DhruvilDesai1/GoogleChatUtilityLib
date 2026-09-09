import json
import os

from chatnotify import render
from chatnotify.models import TEXT, CiInfo, RunMeta, RunResult, TestCounts

CARDS = os.path.join(os.path.dirname(__file__), "fixtures", "cards")


def golden(name):
    with open(os.path.join(CARDS, name), encoding="utf-8") as handle:
        return json.load(handle)


def meta(environment=None, ci=None):
    return RunMeta(
        project="Payments API",
        command="pytest tests/",
        run_id="run-1",
        started_at="2026-09-07 10:04:11",
        version="2.0.0",
        environment=environment,
        ci=ci or CiInfo(),
    )


def test_failed_finish_card_matches_golden():
    counts = TestCounts(
        total=10,
        passed=7,
        failed=2,
        skipped=1,
        failed_names=("tests.test_cart.test_add", "tests.test_cart.test_remove"),
    )
    result = RunResult(exit_code=1, duration_seconds=192.0)
    assert render.finish(meta(), result, counts) == golden("finish_failed.json")


def test_zero_exit_with_failures_is_titled_failed():
    counts = TestCounts(total=2, passed=1, failed=1, skipped=0, failed_names=("a",))
    payload = render.finish(meta(), RunResult(exit_code=0, duration_seconds=1.0), counts)
    assert payload["cardsV2"][0]["card"]["header"]["subtitle"] == "Failed"


def test_nonzero_exit_with_no_counts_is_titled_failed():
    payload = render.finish(meta(), RunResult(exit_code=2, duration_seconds=1.0), None)
    assert payload["cardsV2"][0]["card"]["header"]["subtitle"] == "Failed"


def test_interrupted_run_is_titled_interrupted():
    result = RunResult(exit_code=130, duration_seconds=5.0, interrupted=True)
    payload = render.finish(meta(), result, None)
    assert payload["cardsV2"][0]["card"]["header"]["subtitle"] == "Interrupted"


def test_no_counts_still_reports_duration_and_exit_code():
    payload = render.finish(meta(), RunResult(exit_code=0, duration_seconds=9.0), None)
    rendered = json.dumps(payload)
    assert "Duration" in rendered
    assert "Exit Code" in rendered
    assert "Total Tests" not in rendered
    assert "Results" not in rendered


def test_failure_list_is_truncated_at_ten():
    names = tuple("test_%02d" % index for index in range(25))
    counts = TestCounts(total=25, passed=0, failed=25, skipped=0, failed_names=names)
    payload = render.finish(meta(), RunResult(exit_code=1, duration_seconds=1.0), counts)
    paragraph = payload["cardsV2"][0]["card"]["sections"][2]["widgets"][0]["textParagraph"]["text"]
    assert paragraph.count("<br>") == 10
    assert "and 15 more" in paragraph


def test_version_is_stamped_as_a_trailing_widget_not_a_card_footer():
    """Cards v2 has no `footer` field - Chat rejects the whole message if one is sent.

    v2.0.0 set `card["footer"]`, so every finish card was rejected with
    'Unknown name "footer" ... Cannot find field'. The version still has to appear,
    so it is a trailing textParagraph widget instead. See tests/test_card_schema.py
    for the guard that makes this class of mistake impossible to ship again.
    """
    card = render.finish(meta(), RunResult(exit_code=0, duration_seconds=1.0), None)["cardsV2"][
        0
    ]["card"]
    assert "footer" not in card
    last_widget = card["sections"][-1]["widgets"][-1]
    assert "chatnotify v2.0.0" in last_widget["textParagraph"]["text"]


def test_build_button_present_when_ci_detected():
    ci = CiInfo(provider="Jenkins", build_url="https://ci.example/job/9")
    payload = render.finish(meta(ci=ci), RunResult(exit_code=0, duration_seconds=1.0), None)
    assert "View build" in json.dumps(payload)


def test_text_mode_includes_counts_and_exit_code():
    counts = TestCounts(total=3, passed=2, failed=1, skipped=0, failed_names=("a",))
    payload = render.finish(
        meta(), RunResult(exit_code=1, duration_seconds=65.0), counts, message_type=TEXT
    )
    assert set(payload) == {"text"}
    assert "Failed: 1" in payload["text"]
    assert "Exit Code: 1" in payload["text"]
    assert "1m 5s" in payload["text"]


def test_failed_names_are_html_escaped():
    counts = TestCounts(
        total=1, passed=0, failed=1, skipped=0, failed_names=("<b>evil</b>",)
    )
    rendered = json.dumps(render.finish(meta(), RunResult(exit_code=1, duration_seconds=1.0), counts))
    assert "<b>evil</b>" not in rendered
    assert "&lt;b&gt;evil&lt;/b&gt;" in rendered


def test_duration_formatting():
    assert render.format_duration(0.4) == "0s"
    assert render.format_duration(45.0) == "45s"
    assert render.format_duration(65.0) == "1m 5s"
    assert render.format_duration(192.0) == "3m 12s"
    assert render.format_duration(3725.0) == "1h 2m 5s"


# --- Fix 1: size limits -----------------------------------------------------


def test_overlong_failure_name_is_truncated():
    huge_name = "x" * 10_000
    counts = TestCounts(total=1, passed=0, failed=1, skipped=0, failed_names=(huge_name,))
    payload = render.finish(meta(), RunResult(exit_code=1, duration_seconds=1.0), counts)
    rendered = json.dumps(payload)
    assert huge_name not in rendered
    assert len(rendered) < 5000
    assert "..." in rendered

    text_payload = render.finish(
        meta(), RunResult(exit_code=1, duration_seconds=1.0), counts, message_type=TEXT
    )
    assert huge_name not in text_payload["text"]
    assert "..." in text_payload["text"]


def test_payload_exceeding_byte_cap_drops_optional_detail(monkeypatch):
    names = tuple("test_failure_number_%03d" % index for index in range(10))
    counts = TestCounts(total=10, passed=0, failed=10, skipped=0, failed_names=names)
    result = RunResult(exit_code=1, duration_seconds=1.0)

    # Derive the cap from the real payload size rather than hardcoding a byte count.
    # A hardcoded threshold silently stops engaging whenever field sizes or
    # sanitisation change, and the test then passes without exercising the backstop.
    monkeypatch.setattr(render, "MAX_PAYLOAD_BYTES", 10 ** 9)
    full_card = len(json.dumps(render.finish(meta(), result, counts)).encode("utf-8"))
    full_text = len(
        json.dumps(render.finish(meta(), result, counts, message_type=TEXT)).encode("utf-8")
    )
    monkeypatch.setattr(render, "MAX_PAYLOAD_BYTES", min(full_card, full_text) - 1)

    card_payload = render.finish(meta(), result, counts)
    card_rendered = json.dumps(card_payload)
    for name in names:
        assert name not in card_rendered
    assert "omitted" in card_rendered.lower()

    text_payload = render.finish(meta(), result, counts, message_type=TEXT)
    for name in names:
        assert name not in text_payload["text"]
    assert "omitted" in text_payload["text"].lower()


# --- Fix 2: TEXT mode link/header injection ---------------------------------


def test_text_mode_neutralizes_link_injection_in_failure_name():
    hostile = "<https://evil.example/pwn|Click to fix your build>"
    counts = TestCounts(total=1, passed=0, failed=1, skipped=0, failed_names=(hostile,))
    payload = render.finish(
        meta(), RunResult(exit_code=1, duration_seconds=1.0), counts, message_type=TEXT
    )
    text = payload["text"]
    assert "<https://evil.example/pwn|" not in text
    assert "evil.example" in text


def test_text_mode_project_newline_cannot_forge_header():
    hostile_meta = RunMeta(
        project="Real Project\n*Forged System Message*",
        command="pytest",
        run_id="r",
        started_at="2026-09-07 10:04:11",
        version="2.0.0",
    )
    payload = render.finish(
        hostile_meta, RunResult(exit_code=0, duration_seconds=1.0), None, message_type=TEXT
    )
    lines = payload["text"].split("\n")
    # a raw newline in project must not split the header into two lines - the
    # very next line must be the real Duration line, not a forged one.
    assert lines[1] == "Duration: 1s"
    assert "Forged System Message" not in lines[1]


# --- Fix 3: control characters / bidi override ------------------------------


def test_control_chars_and_bidi_override_stripped_from_card_and_text():
    hostile_name = "tests.test_bell\x07‮reversed"
    counts = TestCounts(total=1, passed=0, failed=1, skipped=0, failed_names=(hostile_name,))
    result = RunResult(exit_code=1, duration_seconds=1.0)

    card_rendered = json.dumps(render.finish(meta(), result, counts))
    assert "‮" not in card_rendered
    assert "\x07" not in card_rendered

    text_payload = render.finish(meta(), result, counts, message_type=TEXT)
    assert "‮" not in text_payload["text"]
    assert "\x07" not in text_payload["text"]

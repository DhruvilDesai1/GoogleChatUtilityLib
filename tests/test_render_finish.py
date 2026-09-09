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


def test_footer_carries_the_version():
    payload = render.finish(meta(), RunResult(exit_code=0, duration_seconds=1.0), None)
    assert payload["cardsV2"][0]["card"]["footer"]["text"] == "chatnotify v2.0.0"


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

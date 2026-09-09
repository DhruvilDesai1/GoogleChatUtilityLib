"""Validate emitted payloads against the Google Chat Cards v2 field names.

Why this file exists
--------------------
The rest of the suite posts to a local stub server (`tests/conftest.py`), which
accepts any JSON. That is deliberate - it keeps tests off the network - but it
means no amount of testing against it can discover that the *real* API rejects a
field name. v2.0.0 shipped with a `footer` key on the card, which Cards v2 has no
such field for, so Chat rejected every finish card with:

    Invalid JSON payload received. Unknown name "footer"
      at 'message.cards_v2[0].card': Cannot find field.

Worse, the golden fixture had been generated from the same buggy code, so the
oracle encoded the bug and the suite actively locked it in.

A golden fixture pins *layout*. This file pins *schema*: it walks the whole
payload and asserts every key is one the API actually defines. Field names come
from the Cards v2 reference; if a legitimate new field is needed, add it here
deliberately - that edit is the point, not an obstacle.
"""

import pytest

from chatnotify import render
from chatnotify.models import CARD, TEXT, CiInfo, RunMeta, RunResult, TestCounts

# Field names per the Google Chat Cards v2 reference. Only structures this project
# emits are listed; anything else showing up is a bug or an undeliberate addition.
MESSAGE = {"text", "cardsV2", "thread", "fallbackText", "privateMessageViewer"}
CARD_WITH_ID = {"cardId", "card"}
CARD = {
    "header",
    "sections",
    "sectionDividerStyle",
    "cardActions",
    "name",
    "fixedFooter",
    "displayStyle",
    "peekCardHeader",
}
CARD_HEADER = {"title", "subtitle", "imageType", "imageUrl", "imageAltText"}
SECTION = {"header", "widgets", "collapsible", "uncollapsibleWidgetsCount", "collapseControl"}
TEXT_PARAGRAPH = {"text", "maxLines"}
DECORATED_TEXT = {
    "icon",
    "startIcon",
    "topLabel",
    "text",
    "bottomLabel",
    "switchControl",
    "button",
    "endIcon",
    "wrapText",
    "onClick",
}
ICON = {"knownIcon", "iconUrl", "materialIcon", "altText", "imageType"}
BUTTON_LIST = {"buttons"}
BUTTON = {"text", "icon", "color", "onClick", "disabled", "altText", "type"}
ON_CLICK = {"action", "openLink", "openDynamicLinkAction", "card", "overflowMenu"}
OPEN_LINK = {"url", "openAs", "onClose"}

# A Widget is a one-of: exactly one of these keys, and nothing else.
WIDGET_TYPES = {
    "textParagraph",
    "image",
    "decoratedText",
    "buttonList",
    "textInput",
    "selectionInput",
    "dateTimePicker",
    "divider",
    "grid",
    "columns",
    "chipList",
    "carousel",
}


def _check(where, obj, allowed):
    unknown = set(obj) - allowed
    assert not unknown, "undocumented field(s) %s at '%s'" % (sorted(unknown), where)


def _check_icon(where, icon):
    _check(where, icon, ICON)


def _check_on_click(where, on_click):
    _check(where, on_click, ON_CLICK)
    if "openLink" in on_click:
        _check("%s.openLink" % where, on_click["openLink"], OPEN_LINK)


def _check_widget(where, widget):
    kinds = set(widget)
    assert len(kinds) == 1, "a Widget is a one-of but %s has keys %s" % (where, sorted(kinds))
    kind = kinds.pop()
    assert kind in WIDGET_TYPES, "unknown widget type %r at '%s'" % (kind, where)
    body = widget[kind]
    at = "%s.%s" % (where, kind)

    if kind == "textParagraph":
        _check(at, body, TEXT_PARAGRAPH)
    elif kind == "decoratedText":
        _check(at, body, DECORATED_TEXT)
        for icon_field in ("icon", "startIcon", "endIcon"):
            if icon_field in body:
                _check_icon("%s.%s" % (at, icon_field), body[icon_field])
        if "onClick" in body:
            _check_on_click("%s.onClick" % at, body["onClick"])
    elif kind == "buttonList":
        _check(at, body, BUTTON_LIST)
        for index, button in enumerate(body.get("buttons", [])):
            bat = "%s.buttons[%d]" % (at, index)
            _check(bat, button, BUTTON)
            if "icon" in button:
                _check_icon("%s.icon" % bat, button["icon"])
            if "onClick" in button:
                _check_on_click("%s.onClick" % bat, button["onClick"])


def assert_valid_payload(payload):
    """Every key in `payload` must be a field the Cards v2 API defines."""
    _check("message", payload, MESSAGE)

    for index, entry in enumerate(payload.get("cardsV2", [])):
        at = "message.cards_v2[%d]" % index
        _check(at, entry, CARD_WITH_ID)
        card = entry["card"]
        _check("%s.card" % at, card, CARD)

        if "header" in card:
            _check("%s.card.header" % at, card["header"], CARD_HEADER)

        for section_index, section in enumerate(card.get("sections", [])):
            sat = "%s.card.sections[%d]" % (at, section_index)
            _check(sat, section, SECTION)
            for widget_index, widget in enumerate(section.get("widgets", [])):
                _check_widget("%s.widgets[%d]" % (sat, widget_index), widget)


def _meta(environment=None, ci=None):
    return RunMeta(
        project="Payments API",
        command="pytest tests/",
        run_id="run-1",
        started_at="2026-09-07 10:04:11",
        version="2.0.0",
        environment=environment,
        ci=ci or CiInfo(),
    )


FULL_CI = CiInfo(
    provider="GitHub Actions",
    branch="main",
    commit="a1b2c3d4",
    actor="dhruvil",
    build_url="https://github.com/o/r/actions/runs/9",
)

COUNTS = TestCounts(
    total=10, passed=7, failed=2, skipped=1, failed_names=("tests.a.test_x", "tests.a.test_y")
)


@pytest.mark.parametrize(
    "environment,ci",
    [(None, None), ("staging", None), (None, FULL_CI), ("staging", FULL_CI)],
    ids=["minimal", "with-env", "with-ci", "with-env-and-ci"],
)
def test_start_card_uses_only_documented_fields(environment, ci):
    assert_valid_payload(render.start(_meta(environment, ci), "CARD"))


@pytest.mark.parametrize(
    "environment,ci",
    [(None, None), ("staging", None), (None, FULL_CI), ("staging", FULL_CI)],
    ids=["minimal", "with-env", "with-ci", "with-env-and-ci"],
)
def test_finish_card_uses_only_documented_fields(environment, ci):
    result = RunResult(exit_code=1, duration_seconds=192.0)
    assert_valid_payload(render.finish(_meta(environment, ci), result, COUNTS, "CARD"))


def test_finish_card_without_counts_uses_only_documented_fields():
    result = RunResult(exit_code=0, duration_seconds=3.0)
    assert_valid_payload(render.finish(_meta(), result, None, "CARD"))


def test_interrupted_finish_card_uses_only_documented_fields():
    result = RunResult(exit_code=130, duration_seconds=3.0, interrupted=True)
    assert_valid_payload(render.finish(_meta(), result, COUNTS, "CARD"))


def test_truncated_finish_card_uses_only_documented_fields(monkeypatch):
    """The oversized path rebuilds the payload; it must stay schema-valid too."""
    names = tuple("test_number_%03d" % index for index in range(40))
    counts = TestCounts(total=40, passed=0, failed=40, skipped=0, failed_names=names)
    result = RunResult(exit_code=1, duration_seconds=1.0)
    monkeypatch.setattr(render, "MAX_PAYLOAD_BYTES", 10 ** 9)
    full = render.finish(_meta(ci=FULL_CI), result, counts, "CARD")
    assert_valid_payload(full)
    monkeypatch.setattr(render, "MAX_PAYLOAD_BYTES", render._payload_size(full) - 1)
    assert_valid_payload(render.finish(_meta(ci=FULL_CI), result, counts, "CARD"))


def test_text_mode_payload_has_only_a_text_field():
    result = RunResult(exit_code=1, duration_seconds=192.0)
    for payload in (
        render.start(_meta(), TEXT),
        render.finish(_meta(), result, COUNTS, TEXT),
    ):
        assert set(payload) == {"text"}
        assert_valid_payload(payload)


def test_the_guard_would_have_caught_the_v2_0_0_footer_bug():
    """Pin the guard itself: the exact payload v2.0.0 sent must be rejected."""
    payload = render.finish(_meta(), RunResult(exit_code=1, duration_seconds=1.0), COUNTS, "CARD")
    payload["cardsV2"][0]["card"]["footer"] = {"text": "chatnotify v2.0.0"}
    with pytest.raises(AssertionError, match="footer"):
        assert_valid_payload(payload)

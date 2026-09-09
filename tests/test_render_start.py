import json
import os

from chatnotify import render
from chatnotify.models import CARD, TEXT, CiInfo, RunMeta

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


def test_minimal_start_card_matches_golden():
    assert render.start(meta()) == golden("start_minimal.json")


def test_full_start_card_matches_golden():
    ci = CiInfo(
        provider="GitHub Actions",
        branch="feature/checkout",
        commit="a1b2c3d4",
        actor="dhruvil",
        build_url="https://github.com/o/r/actions/runs/9",
    )
    assert render.start(meta(environment="staging", ci=ci)) == golden("start_full.json")


def test_empty_environment_is_omitted_entirely():
    payload = render.start(meta(environment=""))
    rendered = json.dumps(payload)
    assert "Environment" not in rendered


def test_partial_ci_metadata_omits_missing_widgets():
    payload = render.start(meta(ci=CiInfo(provider="Jenkins", branch="main")))
    rendered = json.dumps(payload)
    assert "Branch" in rendered
    assert "Commit" not in rendered
    assert "View build" not in rendered


def test_text_mode_returns_plain_text_payload():
    payload = render.start(meta(environment="staging"), message_type=TEXT)
    assert set(payload) == {"text"}
    assert "Payments API" in payload["text"]
    assert "staging" in payload["text"]
    assert "pytest tests/" in payload["text"]


def test_text_mode_omits_environment_when_unset():
    payload = render.start(meta(), message_type=TEXT)
    assert "Environment" not in payload["text"]


def test_html_in_project_name_is_escaped():
    hostile = RunMeta(
        project="<script>x</script>",
        command="pytest",
        run_id="r",
        started_at="2026-09-07 10:04:11",
        version="2.0.0",
    )
    rendered = json.dumps(render.start(hostile, message_type=CARD))
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_card_id_is_derived_from_run_id():
    assert render.start(meta())["cardsV2"][0]["cardId"] == "chatnotify-run-1"


# --- Fix 1: size limits -----------------------------------------------------


def test_overlong_command_is_truncated():
    huge_command = "pytest " + ("x" * 10_000)
    hostile = RunMeta(
        project="Payments API",
        command=huge_command,
        run_id="r",
        started_at="2026-09-07 10:04:11",
        version="2.0.0",
    )
    card_rendered = json.dumps(render.start(hostile, message_type=CARD))
    assert huge_command not in card_rendered
    assert len(card_rendered) < 5000
    assert "..." in card_rendered

    text_payload = render.start(hostile, message_type=TEXT)
    assert huge_command not in text_payload["text"]
    assert "..." in text_payload["text"]


def test_start_payload_exceeding_byte_cap_drops_command(monkeypatch):
    hostile = RunMeta(
        project="Payments API",
        command="pytest tests/test_a.py tests/test_b.py tests/test_c.py",
        run_id="run-1",
        started_at="2026-09-07 10:04:11",
        version="2.0.0",
    )

    # Derive the cap from the real payload size rather than hardcoding a byte count.
    # A hardcoded threshold silently stops engaging whenever field sizes or
    # sanitisation change, and the test then passes without exercising the backstop.
    monkeypatch.setattr(render, "MAX_PAYLOAD_BYTES", 10 ** 9)
    full_card = len(json.dumps(render.start(hostile, message_type=CARD)).encode("utf-8"))
    full_text = len(json.dumps(render.start(hostile, message_type=TEXT)).encode("utf-8"))
    monkeypatch.setattr(render, "MAX_PAYLOAD_BYTES", min(full_card, full_text) - 1)

    card_rendered = json.dumps(render.start(hostile, message_type=CARD))
    assert "omitted" in card_rendered.lower()

    text_payload = render.start(hostile, message_type=TEXT)
    assert "omitted" in text_payload["text"].lower()


# --- Fix 2: TEXT mode link/header injection ---------------------------------


def test_text_mode_neutralizes_metacharacters_in_command():
    hostile = RunMeta(
        project="Payments API",
        command="<https://evil.example/pwn|Click here> && rm *_stuff`",
        run_id="r",
        started_at="2026-09-07 10:04:11",
        version="2.0.0",
    )
    text = render.start(hostile, message_type=TEXT)["text"]
    assert "<https://evil.example/pwn|" not in text
    assert "evil.example" in text


def test_text_mode_project_newline_cannot_forge_header():
    hostile = RunMeta(
        project="Real Project\n*Forged Header*",
        command="pytest",
        run_id="r",
        started_at="2026-09-07 10:04:11",
        version="2.0.0",
    )
    lines = render.start(hostile, message_type=TEXT)["text"].split("\n")
    # a raw newline in project must not split the header into two lines - the
    # very next line must be the real Start Time line, not a forged one.
    assert lines[1] == "Start Time: 2026-09-07 10:04:11"
    assert "Forged Header" not in lines[1]


# --- Fix 3: control characters / bidi override ------------------------------


def test_control_chars_and_bidi_override_stripped_start():
    hostile = RunMeta(
        project="Payments API",
        command="pytest",
        run_id="r",
        started_at="2026-09-07 10:04:11",
        version="2.0.0",
        environment="prod‮-reversed\x07",
    )
    card_rendered = json.dumps(render.start(hostile, message_type=CARD))
    assert "‮" not in card_rendered
    assert "\x07" not in card_rendered

    text_payload = render.start(hostile, message_type=TEXT)
    assert "‮" not in text_payload["text"]
    assert "\x07" not in text_payload["text"]

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

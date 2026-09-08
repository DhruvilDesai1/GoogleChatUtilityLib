"""Pure payload construction. Imports only from .models - no I/O anywhere."""

from html import escape
from typing import List, Optional, Sequence, Tuple

from .models import (
    CARD,
    FAILED,
    INTERRUPTED,
    PASSED,
    RunMeta,
    RunResult,
    TestCounts,
    TEXT,
    resolve_status,
)

MAX_FAILED_NAMES = 10

ICON_PASSED = "https://fonts.gstatic.com/s/e/notoemoji/15.0/2705/512.png"
ICON_FAILED = "https://fonts.gstatic.com/s/e/notoemoji/15.0/274c/512.png"
ICON_SKIPPED = "https://fonts.gstatic.com/s/e/notoemoji/15.0/26a0/512.png"
ICON_ENVIRONMENT = "https://fonts.gstatic.com/s/e/notoemoji/15.0/1f30d/512.png"


def _decorated(
    top_label: str,
    text: str,
    icon_url: Optional[str] = None,
    known_icon: Optional[str] = None,
) -> dict:
    icon = {"iconUrl": icon_url} if icon_url else {"knownIcon": known_icon}
    return {
        "decoratedText": {
            "startIcon": icon,
            "topLabel": top_label,
            "text": escape(text),
        }
    }


def _paragraph(text: str) -> dict:
    return {"textParagraph": {"text": text}}


def _button(label: str, url: str) -> dict:
    return {"buttonList": {"buttons": [{"text": label, "onClick": {"openLink": {"url": url}}}]}}


def _truncate(items: Sequence[str], limit: int) -> Tuple[List[str], int]:
    kept = list(items)[:limit]
    return kept, max(0, len(items) - limit)


def _ci_section(meta: RunMeta) -> Optional[dict]:
    ci = meta.ci
    if not ci.detected:
        return None
    widgets = []
    if ci.branch:
        widgets.append(_decorated("Branch", ci.branch, known_icon="BOOKMARK"))
    if ci.commit:
        widgets.append(_decorated("Commit", ci.commit, known_icon="DESCRIPTION"))
    if ci.actor:
        widgets.append(_decorated("Triggered By", ci.actor, known_icon="PERSON"))
    if ci.build_url:
        widgets.append(_button("View build", ci.build_url))
    if not widgets:
        return None
    return {"header": ci.provider, "widgets": widgets}


def _cards_v2(meta: RunMeta, subtitle: str, sections: List[dict]) -> dict:
    return {
        "cardsV2": [
            {
                "cardId": "chatnotify-%s" % meta.run_id,
                "card": {
                    "header": {"title": escape(meta.project), "subtitle": subtitle},
                    "sections": sections,
                },
            }
        ]
    }


def start(meta: RunMeta, message_type: str = CARD) -> dict:
    if message_type == TEXT:
        lines = ["*%s - Started*" % meta.project, "Start Time: %s" % meta.started_at]
        if meta.environment:
            lines.append("Environment: %s" % meta.environment)
        lines.append("Command: %s" % meta.command)
        if meta.ci.branch:
            lines.append("Branch: %s" % meta.ci.branch)
        return {"text": "\n".join(lines)}

    widgets = [_decorated("Start Time", meta.started_at, known_icon="CLOCK")]
    if meta.environment:
        widgets.append(_decorated("Environment", meta.environment, icon_url=ICON_ENVIRONMENT))
    widgets.append(_paragraph("<b>Command:</b><br>" + escape(meta.command)))

    sections = [{"widgets": widgets}]
    ci_section = _ci_section(meta)
    if ci_section:
        sections.append(ci_section)
    return _cards_v2(meta, "Started", sections)


_SUBTITLES = {PASSED: "Passed", FAILED: "Failed", INTERRUPTED: "Interrupted"}


def format_duration(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return "%dh %dm %ds" % (hours, minutes, secs)
    if minutes:
        return "%dm %ds" % (minutes, secs)
    return "%ds" % secs


def finish(
    meta: RunMeta,
    result: RunResult,
    counts: Optional[TestCounts],
    message_type: str = CARD,
) -> dict:
    status = resolve_status(result, counts)
    duration = format_duration(result.duration_seconds)

    if message_type == TEXT:
        lines = [
            "*%s - %s*" % (meta.project, _SUBTITLES[status]),
            "Duration: %s" % duration,
        ]
        if meta.environment:
            lines.append("Environment: %s" % meta.environment)
        if counts is not None:
            lines.append(
                "Total: %d | Passed: %d | Failed: %d | Skipped: %d"
                % (counts.total, counts.passed, counts.failed, counts.skipped)
            )
            kept, extra = _truncate(counts.failed_names, MAX_FAILED_NAMES)
            if kept:
                lines.append("Failures:")
                lines.extend(kept)
                if extra:
                    lines.append("...and %d more" % extra)
        lines.append("Exit Code: %d" % result.exit_code)
        return {"text": "\n".join(lines)}

    summary = [_decorated("Duration", duration, known_icon="CLOCK")]
    if meta.environment:
        summary.append(_decorated("Environment", meta.environment, icon_url=ICON_ENVIRONMENT))
    if counts is not None:
        summary.append(_decorated("Total Tests", str(counts.total), known_icon="STAR"))
    summary.append(_decorated("Exit Code", str(result.exit_code), known_icon="DESCRIPTION"))

    sections = [{"header": "Execution Summary", "widgets": summary}]

    if counts is not None:
        sections.append(
            {
                "header": "Results",
                "widgets": [
                    _decorated("Passed", str(counts.passed), icon_url=ICON_PASSED),
                    _decorated("Failed", str(counts.failed), icon_url=ICON_FAILED),
                    _decorated("Skipped", str(counts.skipped), icon_url=ICON_SKIPPED),
                ],
            }
        )
        kept, extra = _truncate(counts.failed_names, MAX_FAILED_NAMES)
        if kept:
            text = "<br>".join(escape(name) for name in kept)
            if extra:
                text += "<br><i>...and %d more</i>" % extra
            sections.append({"header": "Failures", "widgets": [_paragraph(text)]})

    ci_section = _ci_section(meta)
    if ci_section:
        sections.append(ci_section)

    payload = _cards_v2(meta, _SUBTITLES[status], sections)
    payload["cardsV2"][0]["card"]["footer"] = {"text": "chatnotify v%s" % meta.version}
    return payload

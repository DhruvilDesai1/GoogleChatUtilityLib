"""Pure payload construction. Imports only from .models - no I/O anywhere."""

import json
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
MAX_FIELD_LENGTH = 200
MAX_PAYLOAD_BYTES = 30000

ICON_PASSED = "https://fonts.gstatic.com/s/e/notoemoji/15.0/2705/512.png"
ICON_FAILED = "https://fonts.gstatic.com/s/e/notoemoji/15.0/274c/512.png"
ICON_SKIPPED = "https://fonts.gstatic.com/s/e/notoemoji/15.0/26a0/512.png"
ICON_ENVIRONMENT = "https://fonts.gstatic.com/s/e/notoemoji/15.0/1f30d/512.png"

_ELLIPSIS = "..."

# Chat's plain-text ("TEXT") payload interprets `<...|...>` as a hyperlink and
# `*`, `_`, backtick as bold/italic/code markers. Neutralise them with
# visually-similar fullwidth lookalikes rather than deleting or HTML-escaping
# them (Chat TEXT payloads do not interpret HTML entities).
# Only the angle brackets are neutralised. `<url|label>` is Chat's link syntax, so an
# unescaped test name can render as a live hyperlink with attacker-chosen text — a real
# phishing vector. The emphasis markers (* _ ` ~) are deliberately left alone: at worst
# a name renders italic or bold, which is cosmetic, whereas `_` appears in virtually
# every Python test name and substituting it would mangle them all and break copying a
# name to re-run it. Newline forgery is handled separately by _CONTROL_CHAR_MAP.
_TEXT_METACHARS = {
    "<": "＜",  # fullwidth less-than sign
    ">": "＞",  # fullwidth greater-than sign
}


def _build_control_char_map():
    """C0/C1 control chars and bidi-override characters -> None (strip), except
    ordinary whitespace (space, tab) which is left untouched and line breaks
    which collapse to a single space so a value cannot forge new lines."""
    mapping = {}
    for codepoint in range(0x00, 0x20):
        mapping[codepoint] = None
    mapping[0x7F] = None
    for codepoint in range(0x80, 0xA0):
        mapping[codepoint] = None
    mapping.pop(0x09, None)  # keep tab
    line_breaks = (
        0x0A,  # LF
        0x0D,  # CR
        0x0B,  # VT
        0x0C,  # FF
        0x85,  # NEL
        0x2028,  # LINE SEPARATOR
        0x2029,  # PARAGRAPH SEPARATOR
    )
    for codepoint in line_breaks:
        mapping[codepoint] = " "
    bidi_controls = (
        0x061C,  # ARABIC LETTER MARK
        0x200E,  # LEFT-TO-RIGHT MARK
        0x200F,  # RIGHT-TO-LEFT MARK
        0x202A,  # LEFT-TO-RIGHT EMBEDDING
        0x202B,  # RIGHT-TO-LEFT EMBEDDING
        0x202C,  # POP DIRECTIONAL FORMATTING
        0x202D,  # LEFT-TO-RIGHT OVERRIDE
        0x202E,  # RIGHT-TO-LEFT OVERRIDE
        0x2066,  # LEFT-TO-RIGHT ISOLATE
        0x2067,  # RIGHT-TO-LEFT ISOLATE
        0x2068,  # FIRST STRONG ISOLATE
        0x2069,  # POP DIRECTIONAL ISOLATE
    )
    for codepoint in bidi_controls:
        mapping[codepoint] = None
    return mapping


_CONTROL_CHAR_MAP = _build_control_char_map()


def _sanitize(value: str) -> str:
    """Shared sanitisation for both CARD and TEXT paths: strip C0/C1 control
    characters and Unicode bidi-override characters, collapsing line breaks to
    a space so a value cannot forge new lines or visually reorder text."""
    return value.translate(_CONTROL_CHAR_MAP)


def _sanitize_text(value: str) -> str:
    """TEXT-path sanitisation: shared control-char stripping plus neutralising
    Chat's plain-text formatting metacharacters (link syntax, bold, italic,
    code) so an interpolated value cannot inject markup."""
    value = _sanitize(value)
    for char, replacement in _TEXT_METACHARS.items():
        value = value.replace(char, replacement)
    return value


def _safe(value: str) -> str:
    """CARD-path sanitisation: shared control-char stripping, then HTML-escape."""
    return escape(_sanitize(value))


def _truncate_field(value: str, limit: int = MAX_FIELD_LENGTH) -> str:
    """Cap a single field's length (e.g. a failure name or command line) so one
    oversized value can't blow out the payload, marking the cut with an
    ellipsis."""
    if len(value) <= limit:
        return value
    keep = max(limit - len(_ELLIPSIS), 0)
    return value[:keep] + _ELLIPSIS


def _payload_size(payload: dict) -> int:
    return len(json.dumps(payload).encode("utf-8"))


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
            "text": _safe(text),
        }
    }


def _paragraph(text: str) -> dict:
    return {"textParagraph": {"text": text}}


def _version_note(version: str) -> str:
    """The version stamp shown at the bottom of the finish card.

    It exists so a card of unexpected shape is traceable to the version that
    produced it, which matters when a team is spread across versions.
    """
    return '<font color="#888888">chatnotify v%s</font>' % _safe(version)


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
                    "header": {"title": _safe(meta.project), "subtitle": subtitle},
                    "sections": sections,
                },
            }
        ]
    }


def start(meta: RunMeta, message_type: str = CARD) -> dict:
    command = _truncate_field(meta.command)

    def build(include_command: bool) -> dict:
        if message_type == TEXT:
            lines = [
                "*%s - Started*" % _sanitize_text(meta.project),
                "Start Time: %s" % meta.started_at,
            ]
            if meta.environment:
                lines.append("Environment: %s" % _sanitize_text(meta.environment))
            if include_command:
                lines.append("Command: %s" % _sanitize_text(command))
            else:
                lines.append("Command: (omitted - message too large)")
            if meta.ci.branch:
                lines.append("Branch: %s" % _sanitize_text(meta.ci.branch))
            return {"text": "\n".join(lines)}

        widgets = [_decorated("Start Time", meta.started_at, known_icon="CLOCK")]
        if meta.environment:
            widgets.append(_decorated("Environment", meta.environment, icon_url=ICON_ENVIRONMENT))
        if include_command:
            widgets.append(_paragraph("<b>Command:</b><br>" + _safe(command)))
        else:
            widgets.append(_paragraph("<i>Command omitted - message too large.</i>"))

        sections = [{"widgets": widgets}]
        ci_section = _ci_section(meta)
        if ci_section:
            sections.append(ci_section)
        return _cards_v2(meta, "Started", sections)

    payload = build(True)
    if _payload_size(payload) > MAX_PAYLOAD_BYTES:
        payload = build(False)
    return payload


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

    def build(include_failures: bool) -> dict:
        if message_type == TEXT:
            lines = [
                "*%s - %s*" % (_sanitize_text(meta.project), _SUBTITLES[status]),
                "Duration: %s" % duration,
            ]
            if meta.environment:
                lines.append("Environment: %s" % _sanitize_text(meta.environment))
            if counts is not None:
                lines.append(
                    "Total: %d | Passed: %d | Failed: %d | Skipped: %d"
                    % (counts.total, counts.passed, counts.failed, counts.skipped)
                )
                if include_failures:
                    kept, extra = _truncate(counts.failed_names, MAX_FAILED_NAMES)
                    if kept:
                        lines.append("Failures:")
                        lines.extend(_sanitize_text(_truncate_field(name)) for name in kept)
                        if extra:
                            lines.append("...and %d more" % extra)
                elif counts.failed_names:
                    lines.append("Failures: (omitted - message too large)")
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
            if include_failures:
                kept, extra = _truncate(counts.failed_names, MAX_FAILED_NAMES)
                if kept:
                    text = "<br>".join(_safe(_truncate_field(name)) for name in kept)
                    if extra:
                        text += "<br><i>...and %d more</i>" % extra
                    sections.append({"header": "Failures", "widgets": [_paragraph(text)]})
            elif counts.failed_names:
                sections.append(
                    {
                        "header": "Failures",
                        "widgets": [_paragraph("<i>Failure details omitted - message too large.</i>")],
                    }
                )

        ci_section = _ci_section(meta)
        if ci_section:
            sections.append(ci_section)

        # The version is a trailing widget, not a card `footer`. Cards v2 has no
        # `footer` field - Chat rejects the whole message with
        #   Invalid JSON payload received. Unknown name "footer"
        #     at 'message.cards_v2[0].card': Cannot find field.
        # The nearest real field, `fixedFooter`, is a CardFixedFooter and holds only
        # primaryButton/secondaryButton, so a version string cannot live there at all.
        sections.append({"widgets": [_paragraph(_version_note(meta.version))]})

        return _cards_v2(meta, _SUBTITLES[status], sections)

    payload = build(True)
    if _payload_size(payload) > MAX_PAYLOAD_BYTES:
        payload = build(False)
    return payload

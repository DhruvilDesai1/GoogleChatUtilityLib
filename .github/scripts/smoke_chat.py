"""Post real payloads to a real Google Chat space and require it to accept them.

Why this exists
---------------
The test suite posts to a local stub server, which accepts any JSON. A stub can
validate transport but never schema, so it cannot discover that the live API
rejects a field name. v2.0.0 shipped a `footer` key on the card and Chat rejected
every finish card with:

    Invalid JSON payload received. Unknown name "footer"
      at 'message.cards_v2[0].card': Cannot find field.

`tests/test_card_schema.py` guards the field names, but that guard is a
transcription of the API's documentation - it cannot notice if the transcription
itself is wrong, or if Google changes the contract. Only a real post can.

Why this asserts on the HTTP status rather than on chatnotify's exit code
------------------------------------------------------------------------
`chatnotify run` deliberately never fails a build because a notification failed.
So a smoke test that merely ran the CLI and checked its exit code would pass even
while every card was being rejected - reproducing the exact blind spot this file
exists to close. It therefore posts the payloads itself and requires 2xx.

Run by .github/workflows/ci.yml on a published release. Needs the
CHATNOTIFY_SMOKE_WEBHOOK repository secret.
"""

import json
import os
import sys
import urllib.error
import urllib.request

from chatnotify import __version__, render
from chatnotify.models import CARD, TEXT, CiInfo, RunMeta, RunResult, TestCounts

TIMEOUT_SECONDS = 20


def fail(message):
    print("SMOKE FAILED: %s" % message, file=sys.stderr)
    raise SystemExit(1)


def post(webhook, label, payload):
    """POST one payload. Returns None on success, or a description of the failure.

    Never prints the webhook: it is a credential, and CI logs are durable.
    """
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json; charset=UTF-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None) or response.getcode()
        if 200 <= status < 300:
            print("  %-28s HTTP %d  (%d bytes)" % (label, status, len(body)))
            return None
        return "%s: HTTP %d" % (label, status)
    except urllib.error.HTTPError as error:
        # The response body is the whole point - it names the offending field,
        # which is how the v2.0.0 bug was diagnosed in the first place.
        detail = error.read().decode("utf-8", "replace")[:1200]
        return "%s: HTTP %d\n%s" % (label, error.code, detail)
    except Exception as error:  # network trouble is a failure, not a pass
        return "%s: %s: %s" % (label, type(error).__name__, error)


def payloads(tag):
    """Every distinct card shape the tool can emit, so all of them get checked."""
    ci = CiInfo(
        provider="GitHub Actions",
        branch="main",
        commit="smoke123",
        actor="ci",
        build_url="https://github.com/DhruvilDesai1/GoogleChatUtilityLib/actions",
    )
    meta = RunMeta(
        project="chatnotify release smoke (%s)" % tag,
        command="python -c 'import sys; sys.exit(1)'",
        run_id="smoke-%s" % tag,
        started_at="release smoke test",
        version=__version__,
        environment="release-check",
        ci=ci,
    )
    counts = TestCounts(
        total=4,
        passed=2,
        failed=1,
        skipped=1,
        failed_names=("tests.smoke.test_deliberate_failure",),
    )
    failed = RunResult(exit_code=1, duration_seconds=192.0)
    passed = RunResult(exit_code=0, duration_seconds=3.0)

    return [
        ("start CARD", render.start(meta, CARD)),
        ("finish CARD with counts", render.finish(meta, failed, counts, CARD)),
        # The plain-script shape: no report found, so no counts section.
        ("finish CARD no counts", render.finish(meta, passed, None, CARD)),
        ("finish TEXT", render.finish(meta, failed, counts, TEXT)),
    ]


def main():
    webhook = (os.environ.get("WEBHOOK") or "").strip()
    if not webhook:
        fail(
            "CHATNOTIFY_SMOKE_WEBHOOK is not set.\n"
            "  This check posts real cards to a Google Chat space and requires the API\n"
            "  to accept them. It is the only thing that can catch a payload the live\n"
            "  API rejects - the test suite's stub server accepts anything.\n"
            "  Add the secret at Settings > Secrets and variables > Actions, or remove\n"
            "  this job. A silently skipped safety check is worse than no check."
        )

    tag = (os.environ.get("TAG") or "untagged").strip()
    print("Posting %s payloads as chatnotify %s (tag %s)" % (4, __version__, tag))

    failures = [problem for label, payload in payloads(tag)
                for problem in [post(webhook, label, payload)] if problem]

    if failures:
        print("", file=sys.stderr)
        for problem in failures:
            print("REJECTED %s" % problem, file=sys.stderr)
        fail("%d of 4 payloads were rejected by Google Chat" % len(failures))

    print("\nAll 4 payload shapes accepted by Google Chat.")


if __name__ == "__main__":
    main()

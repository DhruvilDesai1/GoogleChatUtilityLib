"""Argparse surface, subcommand dispatch, and the top-level never-fatal guard."""

import argparse
import os
import re
import signal
import sys
import time
import traceback
import uuid
from datetime import datetime
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from . import __version__, ci, config, render, reports, runner, transport
from .models import CARD, PASSED, TEXT, RunMeta, resolve_status

EXIT_USAGE = 2

_child_exit_code = None


def _install_sigterm_handler():
    """Route SIGTERM into the KeyboardInterrupt path. Returns a restore callable.

    Windows does not deliver SIGTERM to a process killed via TerminateProcess, so
    this is effectively a no-op there; installing it is still harmless.
    """
    if not hasattr(signal, "SIGTERM"):
        return lambda: None

    def _raise_interrupt(signum, frame):
        raise KeyboardInterrupt()

    try:
        previous = signal.signal(signal.SIGTERM, _raise_interrupt)
    except (ValueError, OSError):
        return lambda: None

    def _restore():
        try:
            signal.signal(signal.SIGTERM, previous)
        except (ValueError, OSError):
            pass

    return _restore


def split_argv(argv: Sequence[str]) -> Tuple[List[str], List[str]]:
    """Everything after the first `--` is the child command, left unparsed."""
    argv = list(argv)
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1:]
    return argv, []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatnotify",
        description="Post Google Chat notifications around any command.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="subcommand")

    # The configuration cascade is the same for every subcommand, so the flags that
    # feed it belong to all three: `doctor` is the tool for verifying a webhook URL
    # before you commit it to config, which it cannot do if it will not accept one.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--project")
    shared.add_argument("--env", dest="environment")
    shared.add_argument("--webhook-url", dest="webhook_url")
    shared.add_argument("--message-type", dest="message_type", choices=[CARD, TEXT])
    shared.add_argument("--quiet", action="store_true")

    run_parser = subparsers.add_parser(
        "run", parents=[shared], help="run a command and notify around it"
    )
    # These two only mean something when there is a wrapped command to report on.
    run_parser.add_argument("--report", help="glob(s) for JUnit XML, comma-separated")
    run_parser.add_argument("--only-on-failure", action="store_true")

    subparsers.add_parser(
        "doctor", parents=[shared], help="show resolved config and send a test card"
    )
    subparsers.add_parser(
        "init", parents=[shared], help="create .chatnotify.ini in this repository"
    )
    return parser


def _flags_from(args: argparse.Namespace) -> dict:
    return {
        "project": getattr(args, "project", None),
        "environment": getattr(args, "environment", None),
        "webhook_url": getattr(args, "webhook_url", None),
        "message_type": getattr(args, "message_type", None),
        "report": getattr(args, "report", None),
        "only_on_failure": getattr(args, "only_on_failure", False),
        "quiet": getattr(args, "quiet", False),
    }


REDACTED = "***"

# Names that mark a value as a credential, matched against a flag name with every
# non-alphanumeric character stripped, so `--api-key` and `--api_key` look alike.
_SECRET_NAMES = (
    "token",
    "password",
    "passwd",
    "pwd",
    "secret",
    "apikey",
    "key",
    "auth",
    "authtoken",
    "bearer",
    "credential",
    "credentials",
    "webhookurl",
    "webhook",
)
_SECRET_SUFFIXES = (
    "token",
    "password",
    "passwd",
    "secret",
    "apikey",
    "key",
    "credential",
    "credentials",
)

# A secret-named `=` assignment or URL query parameter: `?key=AAA`, `--token=BBB`,
# `PASSWORD=ccc`. The value stops at whitespace or `&` so only the one parameter of
# a multi-parameter query is masked.
_ASSIGNMENT_RE = re.compile(
    r"([A-Za-z0-9_.\-]*(?:token|password|passwd|pwd|secret|api[_.\-]?key|key|auth|credentials?))"
    r"(=)"
    r"([^\s&]+)",
    re.IGNORECASE,
)


def _is_secret_flag(token: str) -> bool:
    """Whether `token` is a flag whose *following* argument is a credential."""
    if not token.startswith("-"):
        return False
    name = token.lstrip("-").split("=")[0]
    normalized = "".join(char for char in name.lower() if char.isalnum())
    if not normalized:
        return False
    return normalized in _SECRET_NAMES or normalized.endswith(_SECRET_SUFFIXES)


def _redact_command(command: Sequence[str], webhook_url: Optional[str]) -> str:
    """Render the child's argv for publication, with credential-shaped tokens masked.

    A flag meant for chatnotify that lands *after* the `--` becomes part of the child
    command, and from there it is rendered into a card - so `run -- pytest --token X`
    would publish X. Ordinary commands are returned unchanged; only the configured
    webhook URL, a secret-named assignment or query parameter, and the value after a
    secret-named flag are replaced.
    """
    rendered = []
    mask_next = False
    for token in command:
        if mask_next and not token.startswith("--"):
            rendered.append(REDACTED)
            mask_next = False
            continue
        # `--token=X` carries its value inline, so nothing follows it to mask.
        mask_next = _is_secret_flag(token) and "=" not in token
        cleaned = token
        if webhook_url and webhook_url in cleaned:
            cleaned = cleaned.replace(webhook_url, REDACTED)
        cleaned = _ASSIGNMENT_RE.sub(r"\1\2" + REDACTED, cleaned)
        rendered.append(cleaned)
    return " ".join(rendered)


def _shell_exit_code(code: int) -> int:
    """Translate a signal death into the shell's 128+N convention.

    `Popen.wait()` reports a POSIX signal death as a negative number, and
    `sys.exit(-11)` surfaces as 245 rather than the 139 every CI script checks for.
    Only the process exit status is translated; the RunResult keeps the raw code so
    the finish card still describes the run accurately.
    """
    if code < 0:
        return 128 + abs(code)
    return code


class _NotificationsOff:
    """Stand-in for Config when loading it failed: notifications off, nothing else.

    It exists so that a failure in the notification prologue leaves the rest of
    `run_command` - which must still run the user's command - with a settings object
    it can read, instead of `None` to special-case at every use.
    """

    project = config.DEFAULT_PROJECT
    environment = None
    webhook_url = None
    message_type = CARD
    enabled = False
    only_on_failure = False
    report_patterns = None

    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet


def run_command(args: argparse.Namespace, command: List[str]) -> int:
    global _child_exit_code

    if not command:
        print("chatnotify: no command given; use -- <command>", file=sys.stderr)
        return EXIT_USAGE

    quiet_flag = bool(getattr(args, "quiet", False))
    meta = None
    posting = False

    # Everything that exists only to notify goes inside this guard. Loading config,
    # building the meta and rendering the start card are all as capable of raising as
    # the POST is - a deleted cwd makes `os.getcwd()` itself throw - and if any of
    # them decided the build's fate the wrapped command would never run at all.
    try:
        settings = config.load(flags=_flags_from(args), cwd=os.getcwd())
        posting = settings.enabled and bool(settings.webhook_url)

        if settings.enabled and not settings.webhook_url and not settings.quiet:
            print("chatnotify: no webhook configured; skipping notifications", file=sys.stderr)

        meta = RunMeta(
            project=settings.project,
            command=_redact_command(command, settings.webhook_url),
            run_id=uuid.uuid4().hex[:12],
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            version=__version__,
            environment=settings.environment,
            ci=ci.detect(),
        )

        if posting and not settings.only_on_failure:
            transport.post(
                settings.webhook_url,
                render.start(meta, settings.message_type),
                thread_key=meta.run_id,
                quiet=settings.quiet,
            )
    except (KeyboardInterrupt, SystemExit):
        # The user's Ctrl+C and a deliberate exit are not chatnotify bugs.
        raise
    except BaseException as error:
        settings = _NotificationsOff(quiet=quiet_flag)
        meta = None
        # Without meta there is nothing to thread a finish card onto, and the config
        # that would say where to send it is what failed.
        posting = False
        if not quiet_flag:
            print(
                "chatnotify: notification setup failed (%s: %s);"
                " running the command anyway" % (type(error).__name__, error),
                file=sys.stderr,
            )

    started_epoch = time.time()
    restore_sigterm = _install_sigterm_handler()
    try:
        result = runner.exec_command(command, quiet=settings.quiet)
    finally:
        restore_sigterm()
    exit_code = _shell_exit_code(result.exit_code)
    _child_exit_code = exit_code

    # The mirror of the prologue guard: reading reports and rendering the finish card
    # are notification work too, and the same deleted cwd breaks `os.getcwd()` here.
    # The child's exit code is already recorded, so nothing below can change it - this
    # only keeps a notification failure from surfacing as a traceback.
    try:
        counts = reports.collect(
            os.getcwd(), settings.report_patterns, since=started_epoch, quiet=settings.quiet
        )
        status = resolve_status(result, counts)

        if posting and (not settings.only_on_failure or status != PASSED):
            transport.post(
                settings.webhook_url,
                render.finish(meta, result, counts, settings.message_type),
                thread_key=meta.run_id,
                quiet=settings.quiet,
            )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as error:
        if not settings.quiet:
            print(
                "chatnotify: finish notification failed (%s: %s);"
                " the command's exit code stands" % (type(error).__name__, error),
                file=sys.stderr,
            )

    return exit_code


def _mask_url(url: str) -> str:
    """Identify a webhook URL without revealing its credential.

    The scheme and host are exactly what tells a misconfiguration from a working
    setup - a wrong host, or `http` where `https` was meant - and neither is a
    secret. Everything from the path on, where Google Chat carries the key and
    token, is dropped. A fixed literal would hide the very mistake `doctor` exists
    to surface.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "(unparseable URL)"
    if parts.scheme and parts.netloc:
        return "%s://%s/..." % (parts.scheme, parts.netloc)
    return "(malformed URL - no scheme://host)"


def doctor_command(args: argparse.Namespace) -> int:
    settings = config.load(flags=_flags_from(args), cwd=os.getcwd())
    rows = [
        ("project", settings.project, settings.provenance["project"]),
        ("environment", settings.environment or "(unset)", settings.provenance["environment"]),
        (
            "webhook_url",
            _mask_url(settings.webhook_url) if settings.webhook_url else "(not configured)",
            settings.provenance["webhook_url"],
        ),
        ("message_type", settings.message_type, settings.provenance["message_type"]),
        ("enabled", "yes" if settings.enabled else "no", settings.provenance["enabled"]),
        ("reports", "auto-detect", settings.provenance["report_patterns"]),
    ]
    for name, value, source in rows:
        print("%-14s %-24s (%s)" % (name, value, source))
    print("%-14s %s" % ("machine config", config.machine_config_path()))
    print("%-14s chatnotify %s" % ("version", __version__))

    if not settings.webhook_url:
        print("-> webhook is not configured; set CHATNOTIFY_WEBHOOK_URL")
        return 1

    # `enabled` governs the notifications chatnotify sends *for you*, around a run.
    # Typing `doctor` is an explicit request for a card, so it still goes out - but
    # printing `enabled no` and then posting anyway would be self-contradictory, so
    # say what is about to happen.
    if not settings.enabled:
        print(
            "-> scheduled notifications are disabled (%s);"
            " sending a test card anyway because you asked for one"
            % settings.provenance["enabled"]
        )

    meta = RunMeta(
        project=settings.project,
        command="chatnotify doctor",
        run_id=uuid.uuid4().hex[:12],
        started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        version=__version__,
        environment=settings.environment,
        ci=ci.detect(),
    )
    delivered = transport.post(
        settings.webhook_url,
        render.start(meta, settings.message_type),
        thread_key=meta.run_id,
        quiet=settings.quiet,
    )
    print("-> test card sent successfully" if delivered else "-> test card could not be delivered")
    return 0 if delivered else 1


_INIT_TEMPLATE = """; chatnotify repository config - safe to commit, contains no secrets.
; Set the webhook URL in your environment instead:
;   CHATNOTIFY_WEBHOOK_URL=...
[chatnotify]
project = %s
message_type = CARD
"""


def _already_ignored(existing: str, entry: str) -> bool:
    """Whether these gitignore lines actually ignore `entry`, as git would read them.

    Only meaningful pattern lines count: blank lines and `#` comments are skipped, so
    a "never commit .env" reminder is not mistaken for a rule. A `!entry` negation
    un-ignores it, and because git applies the *last* matching pattern, a negation
    after the entry means it is not ignored at all.
    """
    ignored = False
    for raw in existing.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == entry:
            ignored = True
        elif line == "!" + entry:
            ignored = False
    return ignored


def _ensure_gitignored(path: str, entry: str) -> bool:
    """Append `entry` to the gitignore at `path`. Returns True if it is present after."""
    existing = ""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                existing = handle.read()
        except (OSError, UnicodeDecodeError):
            return False
    if _already_ignored(existing, entry):
        return True
    separator = "" if (not existing or existing.endswith("\n")) else "\n"
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("%s%s\n" % (separator, entry))
    except OSError:
        return False
    return True


def init_command(args: argparse.Namespace) -> int:
    target = os.path.join(os.getcwd(), ".chatnotify.ini")
    if os.path.exists(target):
        print("chatnotify: .chatnotify.ini already exists; not overwriting", file=sys.stderr)
        return 1

    project = getattr(args, "project", None) or os.path.basename(os.path.abspath(os.getcwd()))
    try:
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(_INIT_TEMPLATE % project)
    except OSError as error:
        print(
            "chatnotify: could not write %s: %s" % (target, error),
            file=sys.stderr,
        )
        return 1

    if _ensure_gitignored(os.path.join(os.getcwd(), ".gitignore"), ".env"):
        print("Added .env to .gitignore")
    else:
        print(
            "chatnotify: could not update .gitignore - add `.env` to it yourself before"
            " putting a webhook URL in a .env file, or you risk committing a credential.",
            file=sys.stderr,
        )

    print("Created .chatnotify.ini with project = %s" % project)
    print("")
    print("Next: set your webhook URL, then verify with `chatnotify doctor`")
    print("  CHATNOTIFY_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/...")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw = list(sys.argv[1:]) if argv is None else list(argv)
    own, command = split_argv(raw)
    parser = build_parser()
    args = parser.parse_args(own)

    if args.subcommand == "run":
        return run_command(args, command)
    if args.subcommand == "doctor":
        return doctor_command(args)
    if args.subcommand == "init":
        return init_command(args)

    parser.print_help()
    return EXIT_USAGE


def entrypoint() -> None:
    """Never let a chatnotify bug decide the build's fate."""
    global _child_exit_code
    _child_exit_code = None
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        if _child_exit_code is not None:
            sys.exit(_child_exit_code)
        sys.exit(EXIT_USAGE)

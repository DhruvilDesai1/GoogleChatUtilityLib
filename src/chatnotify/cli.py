"""Argparse surface, subcommand dispatch, and the top-level never-fatal guard."""

import argparse
import os
import sys
import time
import traceback
import uuid
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from . import __version__, ci, config, render, reports, runner, transport
from .models import PASSED, RunMeta, resolve_status

EXIT_USAGE = 2

_child_exit_code = None


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

    run_parser = subparsers.add_parser("run", help="run a command and notify around it")
    run_parser.add_argument("--project")
    run_parser.add_argument("--env", dest="environment")
    run_parser.add_argument("--webhook-url", dest="webhook_url")
    run_parser.add_argument("--message-type", dest="message_type", choices=["CARD", "TEXT"])
    run_parser.add_argument("--report", help="glob(s) for JUnit XML, comma-separated")
    run_parser.add_argument("--only-on-failure", action="store_true")
    run_parser.add_argument("--quiet", action="store_true")

    subparsers.add_parser("doctor", help="show resolved config and send a test card")
    subparsers.add_parser("init", help="create .chatnotify.ini in this repository")
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


def run_command(args: argparse.Namespace, command: List[str]) -> int:
    global _child_exit_code

    if not command:
        print("chatnotify: no command given; use -- <command>", file=sys.stderr)
        return EXIT_USAGE

    settings = config.load(flags=_flags_from(args), cwd=os.getcwd())
    posting = settings.enabled and bool(settings.webhook_url)

    if settings.enabled and not settings.webhook_url and not settings.quiet:
        print("chatnotify: no webhook configured; skipping notifications", file=sys.stderr)

    meta = RunMeta(
        project=settings.project,
        command=" ".join(command),
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

    started_epoch = time.time()
    result = runner.exec_command(command)
    _child_exit_code = result.exit_code

    counts = reports.collect(os.getcwd(), settings.report_patterns, since=started_epoch)
    status = resolve_status(result, counts)

    if posting and (not settings.only_on_failure or status != PASSED):
        transport.post(
            settings.webhook_url,
            render.finish(meta, result, counts, settings.message_type),
            thread_key=meta.run_id,
            quiet=settings.quiet,
        )

    return result.exit_code


_MASK = "https://chat.g..."


def doctor_command(args: argparse.Namespace) -> int:
    settings = config.load(flags=_flags_from(args), cwd=os.getcwd())
    rows = [
        ("project", settings.project, settings.provenance["project"]),
        ("environment", settings.environment or "(unset)", settings.provenance["environment"]),
        (
            "webhook_url",
            _MASK if settings.webhook_url else "(not configured)",
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

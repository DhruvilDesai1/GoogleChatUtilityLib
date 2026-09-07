# chatnotify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stdlib-only Python CLI that wraps any command in any language and posts Google Chat start/finish cards with accurate pass/fail counts.

**Architecture:** Six behavioural modules plus a shared dataclass module. `render.py` is a pure function of `(RunMeta, RunResult, TestCounts)` so card layout is fixture-testable with no I/O; only `config.py`, `runner.py`, `reports.py`, and `transport.py` touch the outside world. Counts come from JUnit XML, which every runner in use can emit, so no framework-specific code exists anywhere.

**Tech Stack:** Python 3.8+, standard library only at runtime (`urllib`, `argparse`, `configparser`, `xml.etree`, `subprocess`, `glob`, `json`). pytest is a **dev-only** dependency and never ships to consumers.

**Spec:** `docs/superpowers/specs/2026-09-07-chatnotify-design.md`

**Project root:** `C:\Users\Adit\IdeaProjects\chatnotify` — a new repository, separate from `GoogleChatUtilityLib`. All paths and commands in this plan are relative to that root unless stated otherwise.

## Global Constraints

Every task's requirements implicitly include this section.

- **Python floor: 3.8.** No walrus-only idioms are banned, but no `tomllib` (3.11+), no `functools.cache` (3.9+), no `dict |` merge (3.9+), no `X | Y` type unions in annotations (3.10+). Use `typing.Optional` / `typing.Dict`.
- **Zero runtime dependencies.** If a task needs a third-party import at runtime, the task is wrong. pytest is dev-only.
- **Exit-code transparency.** `chatnotify run -- <cmd>` exits with exactly `<cmd>`'s code. Never alter it.
- **Notification failure is never fatal.** `transport.post()` returns a bool and never raises.
- **Exit code is authoritative for pass/fail.** Status is `FAILED` if `exit_code != 0` **or** `failed > 0`. Never derive status from counts alone.
- **The webhook URL is never logged**, at any verbosity, in any message, including exception text.
- **Windows is a first-class target.** No POSIX-only signal assumptions, `shell=False` always, `os.path.join` for glob roots.
- **Google Chat payload shape:** `cardsV2` for `CARD`, `{"text": ...}` for `TEXT`.
- **Icon URLs** are reused verbatim from the retired Java library for visual continuity:
  - passed `https://fonts.gstatic.com/s/e/notoemoji/15.0/2705/512.png`
  - failed `https://fonts.gstatic.com/s/e/notoemoji/15.0/274c/512.png`
  - skipped `https://fonts.gstatic.com/s/e/notoemoji/15.0/26a0/512.png`
  - environment `https://fonts.gstatic.com/s/e/notoemoji/15.0/1f30d/512.png`

### Three deliberate refinements to the spec

Recorded here so an implementer does not "fix" them back:

1. **Single HTTP timeout, not 5s connect + 10s read.** Stdlib `urllib` and `http.client` expose one socket timeout, not separate connect and read timeouts. Implemented as one `timeout=10.0`. Honouring the spec literally would require a third-party HTTP library, violating the zero-dependency constraint.
2. **Two extra modules beyond the spec's six.** `models.py` holds the shared frozen dataclasses (prevents an import cycle between `render`, `reports`, and `runner`), and `ci.py` holds CI metadata detection (keeps `config.py` to one responsibility). Neither changes any module's stated responsibility.
3. **Crash-before-spawn exits 2, not 0.** The spec says a top-level crash exits with the child's code. If `chatnotify` crashes *before* the child ever started, there is no child code, and exiting 0 would report success for tests that never ran — the one outcome worse than a false failure. Unknown child code therefore exits 2.

## File Structure

```
chatnotify/
├── pyproject.toml                  packaging, console_scripts entry point, pytest config
├── README.md                       install, quickstart, config reference
├── .gitignore
├── .github/workflows/ci.yml        3.8-3.13 x ubuntu/windows/macos
├── src/chatnotify/
│   ├── __init__.py                 __version__ only
│   ├── __main__.py                 python -m chatnotify
│   ├── models.py                   frozen dataclasses + resolve_status()
│   ├── transport.py                POST with retry/timeout; never raises
│   ├── render.py                   PURE: payload construction + truncation
│   ├── reports.py                  JUnit XML discovery + parsing
│   ├── ci.py                       CI provider metadata detection
│   ├── config.py                   6-layer cascade with provenance
│   ├── runner.py                   subprocess execution, signals, timing
│   └── cli.py                      argparse, subcommands, top-level guard
└── tests/
    ├── conftest.py                 stub HTTP server fixture
    ├── fixtures/reports/           real JUnit XML from each runner
    ├── fixtures/cards/             golden JSON payloads
    ├── test_models.py
    ├── test_transport.py
    ├── test_render_start.py
    ├── test_render_finish.py
    ├── test_reports_parse.py
    ├── test_reports_discover.py
    ├── test_ci.py
    ├── test_config.py
    ├── test_runner.py
    ├── test_cli_run.py
    ├── test_cli_doctor.py
    ├── test_cli_init.py
    └── test_e2e.py
```

Responsibility boundaries: `render.py` never imports `transport` or `config`; `reports.py` never imports `render`; `models.py` imports nothing from the package. `cli.py` is the only module that wires others together.

---

## Task 1: Project scaffold, data models, and the status rule

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/chatnotify/__init__.py`
- Create: `src/chatnotify/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `chatnotify.__version__: str`. From `models`: constants `CARD`, `TEXT`, `PASSED`, `FAILED`, `INTERRUPTED`; frozen dataclasses `TestCounts(total: int, passed: int, failed: int, skipped: int, failed_names: Tuple[str, ...] = ())`, `CiInfo(provider, branch, commit, actor, build_url — all Optional[str], default None)` with property `detected: bool`, `RunMeta(project: str, command: str, run_id: str, started_at: str, version: str, environment: Optional[str] = None, ci: CiInfo = CiInfo())`, `RunResult(exit_code: int, duration_seconds: float, interrupted: bool = False)`; and function `resolve_status(result: RunResult, counts: Optional[TestCounts]) -> str`.

- [ ] **Step 1: Create the repository and directory skeleton**

```bash
mkdir -p /c/Users/Adit/IdeaProjects/chatnotify/src/chatnotify
mkdir -p /c/Users/Adit/IdeaProjects/chatnotify/tests/fixtures/reports
mkdir -p /c/Users/Adit/IdeaProjects/chatnotify/tests/fixtures/cards
cd /c/Users/Adit/IdeaProjects/chatnotify && git init
```

- [ ] **Step 2: Write `pyproject.toml`**

Note `requires-python = ">=3.8"` and an empty `dependencies` list — that emptiness is the zero-dependency constraint made mechanical.

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "chatnotify"
version = "1.0.0"
description = "Post Google Chat notifications when any test suite or script starts and finishes"
requires-python = ">=3.8"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=7"]

[project.scripts]
chatnotify = "chatnotify.cli:entrypoint"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
build/
dist/
*.egg-info/
.env
*.pyz
```

- [ ] **Step 4: Write `src/chatnotify/__init__.py`**

```python
"""chatnotify - post Google Chat notifications around any command."""

__version__ = "1.0.0"
```

- [ ] **Step 5: Write the failing test for the status rule**

This is the single most important test in the project: it pins the invariant that a
crashing run with zero recorded failures is still a failure.

```python
import pytest

from chatnotify.models import (
    FAILED,
    INTERRUPTED,
    PASSED,
    CiInfo,
    RunResult,
    TestCounts,
    resolve_status,
)


def _result(exit_code=0, interrupted=False):
    return RunResult(exit_code=exit_code, duration_seconds=1.5, interrupted=interrupted)


def test_clean_exit_with_no_counts_is_passed():
    assert resolve_status(_result(0), None) == PASSED


def test_clean_exit_with_all_passing_counts_is_passed():
    counts = TestCounts(total=3, passed=3, failed=0, skipped=0)
    assert resolve_status(_result(0), counts) == PASSED


def test_nonzero_exit_with_zero_failures_is_failed():
    """A pytest collection error reports no failures but exits 1."""
    counts = TestCounts(total=0, passed=0, failed=0, skipped=0)
    assert resolve_status(_result(1), counts) == FAILED


def test_zero_exit_with_failures_recorded_is_failed():
    counts = TestCounts(total=5, passed=4, failed=1, skipped=0)
    assert resolve_status(_result(0), counts) == FAILED


def test_interrupted_overrides_everything():
    counts = TestCounts(total=5, passed=5, failed=0, skipped=0)
    assert resolve_status(_result(130, interrupted=True), counts) == INTERRUPTED


def test_counts_and_meta_are_frozen():
    counts = TestCounts(total=1, passed=1, failed=0, skipped=0)
    with pytest.raises(Exception):
        counts.total = 99


def test_ci_info_detected_reflects_provider():
    assert CiInfo().detected is False
    assert CiInfo(provider="GitHub Actions").detected is True
```

- [ ] **Step 6: Run the test to verify it fails**

```bash
cd /c/Users/Adit/IdeaProjects/chatnotify && pip install -e ".[dev]" && python -m pytest tests/test_models.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'chatnotify.models'`.

- [ ] **Step 7: Write `src/chatnotify/models.py`**

```python
"""Frozen data structures shared across modules. Imports nothing from the package."""

from dataclasses import dataclass, field
from typing import Optional, Tuple

CARD = "CARD"
TEXT = "TEXT"

PASSED = "PASSED"
FAILED = "FAILED"
INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True)
class TestCounts:
    total: int
    passed: int
    failed: int
    skipped: int
    failed_names: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CiInfo:
    provider: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    actor: Optional[str] = None
    build_url: Optional[str] = None

    @property
    def detected(self) -> bool:
        return self.provider is not None


@dataclass(frozen=True)
class RunMeta:
    project: str
    command: str
    run_id: str
    started_at: str
    version: str
    environment: Optional[str] = None
    ci: CiInfo = field(default_factory=CiInfo)


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    duration_seconds: float
    interrupted: bool = False


def resolve_status(result: RunResult, counts: Optional[TestCounts]) -> str:
    """Exit code is authoritative; recorded failures can only add a failure."""
    if result.interrupted:
        return INTERRUPTED
    if result.exit_code != 0:
        return FAILED
    if counts is not None and counts.failed > 0:
        return FAILED
    return PASSED
```

- [ ] **Step 8: Run the test to verify it passes**

```bash
python -m pytest tests/test_models.py -v
```

Expected: 7 passed.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .gitignore src/chatnotify/__init__.py src/chatnotify/models.py tests/test_models.py
git commit -m "feat: add project scaffold and status resolution rule"
```

---

## Task 2: Transport — POST that never raises

**Files:**
- Create: `src/chatnotify/transport.py`
- Create: `tests/conftest.py`
- Test: `tests/test_transport.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `transport.post(url: str, payload: dict, thread_key: Optional[str] = None, quiet: bool = False, sleep: Callable[[float], None] = time.sleep) -> bool`. Module constants `TIMEOUT_SECONDS = 10.0`, `RETRY_STATUSES = (429, 500, 502, 503, 504)`, `BACKOFF_SECONDS = (1.0, 4.0)`. The `sleep` parameter exists so tests never actually wait.

- [ ] **Step 1: Write the stub server fixture**

Create `tests/conftest.py`. A real local HTTP server, not a mock — the never-raises
contract has to be proven against actual socket behaviour.

```python
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _Stub:
    def __init__(self):
        self.requests = []
        self.status_queue = []
        self.default_status = 200

    def next_status(self):
        if self.status_queue:
            return self.status_queue.pop(0)
        return self.default_status


@pytest.fixture
def webhook():
    """A local webhook server. `webhook.url` is postable; `webhook.requests` records hits."""
    stub = _Stub()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8")
            stub.requests.append({"path": self.path, "body": json.loads(raw) if raw else None})
            status = stub.next_status()
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stub.url = "http://127.0.0.1:%d/webhook?key=SECRET123" % server.server_address[1]
    try:
        yield stub
    finally:
        server.shutdown()
        server.server_close()
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_transport.py`.

```python
from chatnotify import transport


def test_successful_post_returns_true_and_delivers_payload(webhook):
    assert transport.post(webhook.url, {"text": "hello"}) is True
    assert len(webhook.requests) == 1
    assert webhook.requests[0]["body"] == {"text": "hello"}


def test_thread_key_is_appended_to_query(webhook):
    transport.post(webhook.url, {"text": "hi"}, thread_key="run-42")
    path = webhook.requests[0]["path"]
    assert "threadKey=run-42" in path
    assert "messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD" in path
    assert "key=SECRET123" in path


def test_client_error_returns_false_without_raising(webhook):
    webhook.default_status = 404
    assert transport.post(webhook.url, {"text": "hi"}) is False


def test_client_error_is_not_retried(webhook):
    webhook.default_status = 403
    transport.post(webhook.url, {"text": "hi"}, sleep=lambda _: None)
    assert len(webhook.requests) == 1


def test_rate_limit_is_retried_then_succeeds(webhook):
    webhook.status_queue = [429, 200]
    delays = []
    assert transport.post(webhook.url, {"text": "hi"}, sleep=delays.append) is True
    assert len(webhook.requests) == 2
    assert delays == [1.0]


def test_retries_give_up_after_two_attempts(webhook):
    webhook.default_status = 503
    delays = []
    assert transport.post(webhook.url, {"text": "hi"}, sleep=delays.append) is False
    assert len(webhook.requests) == 3
    assert delays == [1.0, 4.0]


def test_connection_refused_returns_false():
    url = "http://127.0.0.1:1/webhook"
    assert transport.post(url, {"text": "hi"}, sleep=lambda _: None) is False


def test_unserialisable_payload_returns_false_without_raising(webhook):
    assert transport.post(webhook.url, {"bad": object()}) is False


def test_webhook_url_never_appears_in_stderr(capsys):
    url = "http://127.0.0.1:1/webhook?key=SUPERSECRET"
    transport.post(url, {"text": "hi"}, sleep=lambda _: None)
    captured = capsys.readouterr()
    assert "SUPERSECRET" not in captured.err
    assert "SUPERSECRET" not in captured.out


def test_quiet_suppresses_warnings(webhook, capsys):
    webhook.default_status = 404
    transport.post(webhook.url, {"text": "hi"}, quiet=True)
    assert capsys.readouterr().err == ""
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python -m pytest tests/test_transport.py -v
```

Expected: `ImportError: cannot import name 'transport' from 'chatnotify'`.

- [ ] **Step 4: Write `src/chatnotify/transport.py`**

```python
"""HTTP delivery. The only guarantee that matters: post() never raises."""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

TIMEOUT_SECONDS = 10.0
RETRY_STATUSES = (429, 500, 502, 503, 504)
BACKOFF_SECONDS = (1.0, 4.0)
_REPLY_OPTION = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"


def _warn(message: str, quiet: bool) -> None:
    if not quiet:
        print("chatnotify: " + message, file=sys.stderr)


def _thread_url(url: str, thread_key: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key not in ("threadKey", "messageReplyOption")
    ]
    query.append(("threadKey", thread_key))
    query.append(("messageReplyOption", _REPLY_OPTION))
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
    )


def post(
    url: str,
    payload: dict,
    thread_key: Optional[str] = None,
    quiet: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Deliver payload to url. Returns True on 2xx. Never raises, never logs the URL."""
    try:
        target = _thread_url(url, thread_key) if thread_key else url
        body = json.dumps(payload).encode("utf-8")
        attempts = len(BACKOFF_SECONDS) + 1

        for attempt in range(attempts):
            retryable = False
            try:
                request = urllib.request.Request(
                    target,
                    data=body,
                    headers={"Content-Type": "application/json; charset=UTF-8"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                    status = getattr(response, "status", None) or response.getcode()
                if 200 <= status < 300:
                    return True
                retryable = status in RETRY_STATUSES
                message = "webhook returned HTTP %d" % status
            except urllib.error.HTTPError as error:
                status = error.code
                retryable = status in RETRY_STATUSES
                message = "webhook returned HTTP %d" % status
            except Exception as error:
                retryable = True
                message = "could not reach webhook (%s)" % type(error).__name__

            if retryable and attempt < attempts - 1:
                sleep(BACKOFF_SECONDS[attempt])
                continue
            _warn(message, quiet)
            return False

        return False
    except BaseException as error:  # never fatal, by contract
        _warn("notification error (%s)" % type(error).__name__, quiet)
        return False
```

Note the exception messages deliberately carry only `type(error).__name__`, never
`str(error)` — some `urllib` errors embed the request URL in their text, which would
leak the webhook token into logs.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_transport.py -v
```

Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add src/chatnotify/transport.py tests/conftest.py tests/test_transport.py
git commit -m "feat: add HTTP transport with retry that never raises"
```

---

## Task 3: Report parsing — counts and failure names from JUnit XML

**Files:**
- Create: `src/chatnotify/reports.py`
- Create: `tests/fixtures/reports/pytest.xml`
- Create: `tests/fixtures/reports/surefire.xml`
- Create: `tests/fixtures/reports/jest.xml`
- Create: `tests/fixtures/reports/malformed.xml`
- Test: `tests/test_reports_parse.py`

**Interfaces:**
- Consumes: `models.TestCounts`.
- Produces: `reports.parse_files(paths: Iterable[str]) -> Optional[TestCounts]` — returns `None` when no `<testcase>` element was found in any file. Later tasks add `reports.discover()` and `reports.collect()` to this same module.

**Why count `<testcase>` elements rather than trust `<testsuite>` attributes:** the
attributes are inconsistent across tools (pytest records skips on the suite, jest-junit
differs, Surefire emits `errors` separately from `failures`), and summing them is exactly
how the Java library ended up double-counting retried tests. Walking the cases is uniform
across all five runners and immune to that class of bug.

- [ ] **Step 1: Write the fixture files**

`tests/fixtures/reports/pytest.xml` — 4 cases: 2 passed, 1 failed, 1 skipped.

```xml
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="0" failures="1" skipped="1" tests="4" time="0.412">
    <testcase classname="tests.test_math" name="test_add" time="0.001"/>
    <testcase classname="tests.test_math" name="test_subtract" time="0.001"/>
    <testcase classname="tests.test_math" name="test_divide" time="0.002">
      <failure message="assert 1 == 2">E assert 1 == 2</failure>
    </testcase>
    <testcase classname="tests.test_math" name="test_modulo" time="0.000">
      <skipped type="pytest.skip" message="not implemented"/>
    </testcase>
  </testsuite>
</testsuites>
```

`tests/fixtures/reports/surefire.xml` — bare `<testsuite>` root, and an `<error>`
rather than a `<failure>`, which must still count as failed.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.teamninja.LoginTest" tests="3" errors="1" skipped="0" failures="0" time="2.11">
  <testcase name="validLogin" classname="com.teamninja.LoginTest" time="1.02"/>
  <testcase name="invalidLogin" classname="com.teamninja.LoginTest" time="0.55"/>
  <testcase name="expiredSession" classname="com.teamninja.LoginTest" time="0.54">
    <error message="NullPointerException" type="java.lang.NullPointerException">stack</error>
  </testcase>
</testsuite>
```

`tests/fixtures/reports/jest.xml` — no `classname` attribute on one case, so the
name-building logic must degrade gracefully.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="jest tests" tests="2" failures="1" time="1.8">
  <testsuite name="cart.test.js" tests="2" failures="1" time="1.8">
    <testcase classname="cart adds item" name="adds item" time="0.9"/>
    <testcase name="removes item" time="0.9">
      <failure>Expected 0 received 1</failure>
    </testcase>
  </testsuite>
</testsuites>
```

`tests/fixtures/reports/malformed.xml` — truncated mid-element.

```xml
<?xml version="1.0"?>
<testsuite name="broken"><testcase name="a"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_reports_parse.py`.

```python
import os

from chatnotify import reports

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "reports")


def fixture(name):
    return os.path.join(FIXTURES, name)


def test_pytest_report_counts_cases_not_attributes():
    counts = reports.parse_files([fixture("pytest.xml")])
    assert (counts.total, counts.passed, counts.failed, counts.skipped) == (4, 2, 1, 1)


def test_pytest_report_captures_failed_name():
    counts = reports.parse_files([fixture("pytest.xml")])
    assert counts.failed_names == ("tests.test_math.test_divide",)


def test_surefire_error_element_counts_as_failed():
    counts = reports.parse_files([fixture("surefire.xml")])
    assert (counts.total, counts.passed, counts.failed, counts.skipped) == (3, 2, 1, 0)
    assert counts.failed_names == ("com.teamninja.LoginTest.expiredSession",)


def test_jest_case_without_classname_uses_bare_name():
    counts = reports.parse_files([fixture("jest.xml")])
    assert counts.failed_names == ("removes item",)


def test_multiple_files_are_summed():
    counts = reports.parse_files([fixture("pytest.xml"), fixture("surefire.xml")])
    assert (counts.total, counts.passed, counts.failed, counts.skipped) == (7, 4, 2, 1)


def test_malformed_xml_is_skipped_not_raised():
    counts = reports.parse_files([fixture("malformed.xml"), fixture("surefire.xml")])
    assert counts.total == 3


def test_only_malformed_input_returns_none():
    assert reports.parse_files([fixture("malformed.xml")]) is None


def test_missing_file_returns_none():
    assert reports.parse_files([fixture("does-not-exist.xml")]) is None


def test_empty_input_returns_none():
    assert reports.parse_files([]) is None
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python -m pytest tests/test_reports_parse.py -v
```

Expected: `ImportError: cannot import name 'reports' from 'chatnotify'`.

- [ ] **Step 4: Write `src/chatnotify/reports.py`**

```python
"""Discover and parse JUnit XML. The universal counts source across all runners."""

from typing import Iterable, Optional
from xml.etree import ElementTree

from .models import TestCounts


def _case_name(case) -> str:
    name = case.get("name") or "<unnamed>"
    classname = case.get("classname")
    if classname:
        return "%s.%s" % (classname, name)
    return name


def parse_files(paths: Iterable[str]) -> Optional[TestCounts]:
    """Sum counts across JUnit XML files. Returns None if no test cases were found."""
    total = passed = failed = skipped = 0
    failed_names = []

    for path in paths:
        try:
            tree = ElementTree.parse(str(path))
        except (ElementTree.ParseError, OSError):
            continue
        for case in tree.iter("testcase"):
            total += 1
            if case.find("failure") is not None or case.find("error") is not None:
                failed += 1
                failed_names.append(_case_name(case))
            elif case.find("skipped") is not None:
                skipped += 1
            else:
                passed += 1

    if total == 0:
        return None
    return TestCounts(
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        failed_names=tuple(failed_names),
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_reports_parse.py -v
```

Expected: 9 passed.

- [ ] **Step 6: Verify the fixtures against reality**

The fixtures above are hand-written from the real formats. Confirm the shape matches
actual output before trusting them, and replace any that differ:

```bash
python -m pytest --junitxml=/tmp/real-pytest.xml tests/test_models.py
head -20 /tmp/real-pytest.xml
```

Expected: a `<testsuites><testsuite>` wrapper with `<testcase classname=... name=.../>`
children, matching `pytest.xml`. If the structure differs, overwrite the fixture with
the real output and re-run Step 5.

- [ ] **Step 7: Commit**

```bash
git add src/chatnotify/reports.py tests/fixtures/reports tests/test_reports_parse.py
git commit -m "feat: parse JUnit XML counts and failure names"
```

---

## Task 4: Report discovery — globs and staleness

**Files:**
- Modify: `src/chatnotify/reports.py` (append `DEFAULT_GLOBS`, `discover`, `collect`)
- Test: `tests/test_reports_discover.py`

**Interfaces:**
- Consumes: `reports.parse_files()` from Task 3.
- Produces: `reports.DEFAULT_GLOBS: Tuple[str, ...]`; `reports.discover(root: str, patterns: Optional[Sequence[str]] = None, since: Optional[float] = None) -> List[str]`; `reports.collect(root: str, patterns: Optional[Sequence[str]] = None, since: Optional[float] = None) -> Optional[TestCounts]`. `since` is a `time.time()` epoch float.

**The staleness rule:** auto-detected files are ignored if their mtime predates the run
start; an explicit `--report` glob is authoritative and never filtered. Without this, a
report left over from yesterday gets parsed and announced as today's result — silent and
confidence-destroying. A 1-second tolerance absorbs coarse filesystem mtime granularity,
which on some Windows and network filesystems would otherwise discard a report written in
the same second the run began.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reports_discover.py`.

```python
import os
import time

from chatnotify import reports

PASSING_XML = (
    '<testsuite name="s" tests="1"><testcase classname="c" name="t"/></testsuite>'
)


def write(path, content=PASSING_XML, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_default_globs_find_surefire_reports(tmp_path):
    write(str(tmp_path / "target" / "surefire-reports" / "TEST-Login.xml"))
    found = reports.discover(str(tmp_path))
    assert len(found) == 1


def test_default_globs_find_root_junit_xml(tmp_path):
    write(str(tmp_path / "junit.xml"))
    assert len(reports.discover(str(tmp_path))) == 1


def test_default_globs_recurse_into_test_results(tmp_path):
    write(str(tmp_path / "test-results" / "chrome" / "results.xml"))
    assert len(reports.discover(str(tmp_path))) == 1


def test_stale_autodetected_report_is_ignored(tmp_path):
    started = time.time()
    write(str(tmp_path / "junit.xml"), mtime=started - 86400)
    assert reports.discover(str(tmp_path), since=started) == []


def test_fresh_autodetected_report_is_kept(tmp_path):
    started = time.time()
    write(str(tmp_path / "junit.xml"), mtime=started + 1)
    assert len(reports.discover(str(tmp_path), since=started)) == 1


def test_report_written_in_the_same_second_is_kept(tmp_path):
    """Coarse filesystem mtime must not discard a legitimately fresh report."""
    started = time.time()
    write(str(tmp_path / "junit.xml"), mtime=started - 0.5)
    assert len(reports.discover(str(tmp_path), since=started)) == 1


def test_explicit_glob_ignores_staleness(tmp_path):
    started = time.time()
    write(str(tmp_path / "custom" / "out.xml"), mtime=started - 86400)
    found = reports.discover(str(tmp_path), patterns=["custom/*.xml"], since=started)
    assert len(found) == 1


def test_explicit_glob_overrides_defaults(tmp_path):
    write(str(tmp_path / "junit.xml"))
    write(str(tmp_path / "custom" / "out.xml"))
    found = reports.discover(str(tmp_path), patterns=["custom/*.xml"])
    assert len(found) == 1
    assert found[0].endswith("out.xml")


def test_directories_are_not_returned(tmp_path):
    os.makedirs(str(tmp_path / "test-results" / "nested.xml"), exist_ok=True)
    assert reports.discover(str(tmp_path)) == []


def test_duplicate_matches_are_deduplicated(tmp_path):
    write(str(tmp_path / "test-results" / "a.xml"))
    found = reports.discover(str(tmp_path), patterns=["test-results/*.xml", "test-results/**/*.xml"])
    assert len(found) == 1


def test_collect_returns_counts_for_discovered_reports(tmp_path):
    write(str(tmp_path / "junit.xml"))
    counts = reports.collect(str(tmp_path))
    assert counts.total == 1 and counts.passed == 1


def test_collect_returns_none_when_nothing_found(tmp_path):
    assert reports.collect(str(tmp_path)) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_reports_discover.py -v
```

Expected: `AttributeError: module 'chatnotify.reports' has no attribute 'discover'`.

- [ ] **Step 3: Append to `src/chatnotify/reports.py`**

Add these imports at the top of the file, alongside the existing ones:

```python
import glob
import os
from typing import Iterable, List, Optional, Sequence
```

Then append to the end of the module:

```python
DEFAULT_GLOBS = (
    "target/surefire-reports/*.xml",
    "target/failsafe-reports/*.xml",
    "junit.xml",
    "test-results/**/*.xml",
    "reports/**/*.xml",
    "build/test-results/**/*.xml",
)

_MTIME_TOLERANCE_SECONDS = 1.0


def discover(
    root: str,
    patterns: Optional[Sequence[str]] = None,
    since: Optional[float] = None,
) -> List[str]:
    """Find report files under root. Staleness filtering applies to defaults only."""
    explicit = patterns is not None
    active = tuple(patterns) if explicit else DEFAULT_GLOBS
    cutoff = None if (explicit or since is None) else since - _MTIME_TOLERANCE_SECONDS

    found = set()
    for pattern in active:
        for match in glob.glob(os.path.join(root, pattern), recursive=True):
            if not os.path.isfile(match):
                continue
            if cutoff is not None:
                try:
                    if os.path.getmtime(match) < cutoff:
                        continue
                except OSError:
                    continue
            found.add(os.path.normpath(match))
    return sorted(found)


def collect(
    root: str,
    patterns: Optional[Sequence[str]] = None,
    since: Optional[float] = None,
) -> Optional[TestCounts]:
    """Discover reports then parse them. None means no counts are available."""
    return parse_files(discover(root, patterns=patterns, since=since))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_reports_discover.py tests/test_reports_parse.py -v
```

Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git add src/chatnotify/reports.py tests/test_reports_discover.py
git commit -m "feat: discover report files with staleness filtering"
```

---

## Task 5: Render the start card

**Files:**
- Create: `src/chatnotify/render.py`
- Create: `tests/fixtures/cards/start_minimal.json`
- Create: `tests/fixtures/cards/start_full.json`
- Test: `tests/test_render_start.py`

**Interfaces:**
- Consumes: `models.RunMeta`, `models.CiInfo`, `models.CARD`, `models.TEXT`.
- Produces: `render.start(meta: RunMeta, message_type: str = CARD) -> dict`. Internal helpers `render._decorated(top_label: str, text: str, icon_url: Optional[str] = None, known_icon: Optional[str] = None) -> dict`, `render._paragraph(text: str) -> dict`, `render._button(label: str, url: str) -> dict`, `render._truncate(items: Sequence[str], limit: int) -> Tuple[List[str], int]`, and constants `MAX_FAILED_NAMES = 10`, `ICON_PASSED`, `ICON_FAILED`, `ICON_SKIPPED`, `ICON_ENVIRONMENT`. Task 6 appends `render.finish()` to this module and reuses every helper above.

`render.py` imports only from `.models` — never `transport`, `config`, or `reports`.
That purity is what makes golden-fixture testing possible and is the seam a future Slack
backend would attach to.

- [ ] **Step 1: Write the golden fixtures**

`tests/fixtures/cards/start_minimal.json` — no environment, no CI.

```json
{
  "cardsV2": [
    {
      "cardId": "chatnotify-run-1",
      "card": {
        "header": {
          "title": "Payments API",
          "subtitle": "Started"
        },
        "sections": [
          {
            "widgets": [
              {
                "decoratedText": {
                  "startIcon": {"knownIcon": "CLOCK"},
                  "topLabel": "Start Time",
                  "text": "2026-09-07 10:04:11"
                }
              },
              {
                "textParagraph": {
                  "text": "<b>Command:</b><br>pytest tests/"
                }
              }
            ]
          }
        ]
      }
    }
  ]
}
```

`tests/fixtures/cards/start_full.json` — environment plus full CI metadata.

```json
{
  "cardsV2": [
    {
      "cardId": "chatnotify-run-1",
      "card": {
        "header": {
          "title": "Payments API",
          "subtitle": "Started"
        },
        "sections": [
          {
            "widgets": [
              {
                "decoratedText": {
                  "startIcon": {"knownIcon": "CLOCK"},
                  "topLabel": "Start Time",
                  "text": "2026-09-07 10:04:11"
                }
              },
              {
                "decoratedText": {
                  "startIcon": {"iconUrl": "https://fonts.gstatic.com/s/e/notoemoji/15.0/1f30d/512.png"},
                  "topLabel": "Environment",
                  "text": "staging"
                }
              },
              {
                "textParagraph": {
                  "text": "<b>Command:</b><br>pytest tests/"
                }
              }
            ]
          },
          {
            "header": "GitHub Actions",
            "widgets": [
              {
                "decoratedText": {
                  "startIcon": {"knownIcon": "BOOKMARK"},
                  "topLabel": "Branch",
                  "text": "feature/checkout"
                }
              },
              {
                "decoratedText": {
                  "startIcon": {"knownIcon": "DESCRIPTION"},
                  "topLabel": "Commit",
                  "text": "a1b2c3d4"
                }
              },
              {
                "decoratedText": {
                  "startIcon": {"knownIcon": "PERSON"},
                  "topLabel": "Triggered By",
                  "text": "dhruvil"
                }
              },
              {
                "buttonList": {
                  "buttons": [
                    {
                      "text": "View build",
                      "onClick": {"openLink": {"url": "https://github.com/o/r/actions/runs/9"}}
                    }
                  ]
                }
              }
            ]
          }
        ]
      }
    }
  ]
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_render_start.py`.

```python
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
        version="1.0.0",
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
        version="1.0.0",
    )
    rendered = json.dumps(render.start(hostile, message_type=CARD))
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_card_id_is_derived_from_run_id():
    assert render.start(meta())["cardsV2"][0]["cardId"] == "chatnotify-run-1"
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python -m pytest tests/test_render_start.py -v
```

Expected: `ImportError: cannot import name 'render' from 'chatnotify'`.

- [ ] **Step 4: Write `src/chatnotify/render.py`**

```python
"""Pure payload construction. Imports only from .models - no I/O anywhere."""

from html import escape
from typing import List, Optional, Sequence, Tuple

from .models import CARD, TEXT, RunMeta

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
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_render_start.py -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add src/chatnotify/render.py tests/fixtures/cards tests/test_render_start.py
git commit -m "feat: render the start card"
```

---

## Task 6: Render the finish card, with truncation

**Files:**
- Modify: `src/chatnotify/render.py` (append `finish`)
- Create: `tests/fixtures/cards/finish_failed.json`
- Test: `tests/test_render_finish.py`

**Interfaces:**
- Consumes: every helper produced by Task 5, plus `models.RunResult`, `models.TestCounts`, `models.resolve_status`, `models.PASSED`, `models.FAILED`, `models.INTERRUPTED`.
- Produces: `render.finish(meta: RunMeta, result: RunResult, counts: Optional[TestCounts], message_type: str = CARD) -> dict` and `render.format_duration(seconds: float) -> str`.

Truncation lives here rather than in `reports.py` so it is covered by fixture tests — an
oversized payload must be impossible to ship, and defect 3 in the retired Java library was
exactly this omission.

- [ ] **Step 1: Write the golden fixture**

`tests/fixtures/cards/finish_failed.json`

```json
{
  "cardsV2": [
    {
      "cardId": "chatnotify-run-1",
      "card": {
        "header": {
          "title": "Payments API",
          "subtitle": "Failed"
        },
        "sections": [
          {
            "header": "Execution Summary",
            "widgets": [
              {
                "decoratedText": {
                  "startIcon": {"knownIcon": "CLOCK"},
                  "topLabel": "Duration",
                  "text": "3m 12s"
                }
              },
              {
                "decoratedText": {
                  "startIcon": {"knownIcon": "STAR"},
                  "topLabel": "Total Tests",
                  "text": "10"
                }
              },
              {
                "decoratedText": {
                  "startIcon": {"knownIcon": "DESCRIPTION"},
                  "topLabel": "Exit Code",
                  "text": "1"
                }
              }
            ]
          },
          {
            "header": "Results",
            "widgets": [
              {
                "decoratedText": {
                  "startIcon": {"iconUrl": "https://fonts.gstatic.com/s/e/notoemoji/15.0/2705/512.png"},
                  "topLabel": "Passed",
                  "text": "7"
                }
              },
              {
                "decoratedText": {
                  "startIcon": {"iconUrl": "https://fonts.gstatic.com/s/e/notoemoji/15.0/274c/512.png"},
                  "topLabel": "Failed",
                  "text": "2"
                }
              },
              {
                "decoratedText": {
                  "startIcon": {"iconUrl": "https://fonts.gstatic.com/s/e/notoemoji/15.0/26a0/512.png"},
                  "topLabel": "Skipped",
                  "text": "1"
                }
              }
            ]
          },
          {
            "header": "Failures",
            "widgets": [
              {
                "textParagraph": {
                  "text": "tests.test_cart.test_add<br>tests.test_cart.test_remove"
                }
              }
            ]
          }
        ],
        "footer": {
          "text": "chatnotify v1.0.0"
        }
      }
    }
  ]
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_render_finish.py`.

```python
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
        version="1.0.0",
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
    assert payload["cardsV2"][0]["card"]["footer"]["text"] == "chatnotify v1.0.0"


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
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python -m pytest tests/test_render_finish.py -v
```

Expected: `AttributeError: module 'chatnotify.render' has no attribute 'finish'`.

- [ ] **Step 4: Append to `src/chatnotify/render.py`**

Extend the existing import from `.models` to include the new names:

```python
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
```

Then append to the end of the module:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_render_finish.py tests/test_render_start.py -v
```

Expected: 19 passed.

- [ ] **Step 6: Commit**

```bash
git add src/chatnotify/render.py tests/fixtures/cards/finish_failed.json tests/test_render_finish.py
git commit -m "feat: render the finish card with truncated failure list"
```

---

## Task 7: CI metadata detection

**Files:**
- Create: `src/chatnotify/ci.py`
- Test: `tests/test_ci.py`

**Interfaces:**
- Consumes: `models.CiInfo`.
- Produces: `ci.detect(env: Optional[Mapping[str, str]] = None) -> CiInfo`. Passing `env` explicitly is what makes this testable without mutating the real environment.

For a shared team space, "who ran this and on what branch" is the difference between a
useful notification and noise. This is pure environment reading — no subprocess calls,
no `git` invocation.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ci.py`.

```python
from chatnotify import ci


def test_no_ci_environment_returns_undetected():
    info = ci.detect({})
    assert info.detected is False
    assert info.provider is None


def test_github_actions_is_fully_detected():
    info = ci.detect(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a1b2c3d4e5f6a7b8",
            "GITHUB_ACTOR": "dhruvil",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_RUN_ID": "12345",
        }
    )
    assert info.provider == "GitHub Actions"
    assert info.branch == "main"
    assert info.commit == "a1b2c3d4"
    assert info.actor == "dhruvil"
    assert info.build_url == "https://github.com/owner/repo/actions/runs/12345"


def test_github_pull_request_prefers_head_ref():
    info = ci.detect(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REF": "refs/pull/7/merge",
            "GITHUB_HEAD_REF": "feature/checkout",
        }
    )
    assert info.branch == "feature/checkout"


def test_gitlab_is_detected():
    info = ci.detect(
        {
            "GITLAB_CI": "true",
            "CI_COMMIT_REF_NAME": "develop",
            "CI_COMMIT_SHA": "0123456789abcdef",
            "GITLAB_USER_LOGIN": "asha",
            "CI_PIPELINE_URL": "https://gitlab.example/p/1",
        }
    )
    assert info.provider == "GitLab CI"
    assert info.branch == "develop"
    assert info.commit == "01234567"
    assert info.actor == "asha"
    assert info.build_url == "https://gitlab.example/p/1"


def test_jenkins_is_detected():
    info = ci.detect(
        {
            "JENKINS_URL": "https://ci.example/",
            "GIT_BRANCH": "origin/main",
            "GIT_COMMIT": "fedcba9876543210",
            "BUILD_URL": "https://ci.example/job/nightly/9/",
        }
    )
    assert info.provider == "Jenkins"
    assert info.branch == "main"
    assert info.commit == "fedcba98"
    assert info.build_url == "https://ci.example/job/nightly/9/"


def test_generic_ci_flag_is_detected_without_metadata():
    info = ci.detect({"CI": "true"})
    assert info.provider == "CI"
    assert info.branch is None
    assert info.build_url is None


def test_missing_repository_omits_build_url():
    info = ci.detect({"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "1"})
    assert info.build_url is None


def test_blank_values_become_none_not_empty_strings():
    info = ci.detect({"GITHUB_ACTIONS": "true", "GITHUB_SHA": "", "GITHUB_ACTOR": ""})
    assert info.commit is None
    assert info.actor is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_ci.py -v
```

Expected: `ImportError: cannot import name 'ci' from 'chatnotify'`.

- [ ] **Step 3: Write `src/chatnotify/ci.py`**

```python
"""Detect CI provider metadata from the environment. No subprocess calls."""

import os
from typing import Mapping, Optional

from .models import CiInfo

_SHORT_SHA = 8


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _short(value: Optional[str]) -> Optional[str]:
    cleaned = _clean(value)
    return cleaned[:_SHORT_SHA] if cleaned else None


def _branch_from_ref(ref: Optional[str]) -> Optional[str]:
    cleaned = _clean(ref)
    if not cleaned:
        return None
    for prefix in ("refs/heads/", "refs/tags/", "origin/"):
        if cleaned.startswith(prefix):
            return cleaned[len(prefix):]
    return cleaned


def detect(env: Optional[Mapping[str, str]] = None) -> CiInfo:
    env = os.environ if env is None else env

    if _clean(env.get("GITHUB_ACTIONS")):
        repository = _clean(env.get("GITHUB_REPOSITORY"))
        run_id = _clean(env.get("GITHUB_RUN_ID"))
        build_url = None
        if repository and run_id:
            build_url = "https://github.com/%s/actions/runs/%s" % (repository, run_id)
        return CiInfo(
            provider="GitHub Actions",
            branch=_clean(env.get("GITHUB_HEAD_REF")) or _branch_from_ref(env.get("GITHUB_REF")),
            commit=_short(env.get("GITHUB_SHA")),
            actor=_clean(env.get("GITHUB_ACTOR")),
            build_url=build_url,
        )

    if _clean(env.get("GITLAB_CI")):
        return CiInfo(
            provider="GitLab CI",
            branch=_branch_from_ref(env.get("CI_COMMIT_REF_NAME")),
            commit=_short(env.get("CI_COMMIT_SHA")),
            actor=_clean(env.get("GITLAB_USER_LOGIN")),
            build_url=_clean(env.get("CI_PIPELINE_URL")),
        )

    if _clean(env.get("JENKINS_URL")):
        return CiInfo(
            provider="Jenkins",
            branch=_branch_from_ref(env.get("GIT_BRANCH")),
            commit=_short(env.get("GIT_COMMIT")),
            actor=_clean(env.get("BUILD_USER_ID")),
            build_url=_clean(env.get("BUILD_URL")),
        )

    if _clean(env.get("CI")):
        return CiInfo(provider="CI")

    return CiInfo()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_ci.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/chatnotify/ci.py tests/test_ci.py
git commit -m "feat: detect CI provider metadata from environment"
```

---

## Task 8: Configuration cascade with provenance

**Files:**
- Create: `src/chatnotify/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `models.CARD`, `models.TEXT`.
- Produces:
  - `config.Config` — frozen dataclass with fields `project: str`, `environment: Optional[str]`, `webhook_url: Optional[str]`, `message_type: str`, `enabled: bool`, `only_on_failure: bool`, `quiet: bool`, `report_patterns: Optional[Tuple[str, ...]]`, `provenance: Dict[str, str]`.
  - `config.load(flags: Optional[Dict[str, Optional[str]]] = None, cwd: Optional[str] = None, env: Optional[Mapping[str, str]] = None) -> Config`
  - `config.machine_config_path(env: Optional[Mapping[str, str]] = None) -> str`
  - `config.DEFAULT_PROJECT = "Unknown Project"`

`flags` keys are exactly: `project`, `environment`, `webhook_url`, `message_type`,
`report`, `only_on_failure`, `quiet`. A `None` value means the flag was not passed.

**Precedence** (highest first): CLI flag, environment variable, `.env`, `.chatnotify.ini`,
machine config, built-in default. Every resolved value records which layer produced it in
`provenance`, keyed by field name — that is what makes six layers debuggable rather than
mystifying.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`.

```python
import os

import pytest

from chatnotify import config


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


@pytest.fixture
def repo(tmp_path):
    return str(tmp_path)


def test_default_project_when_nothing_configured(repo):
    result = config.load(cwd=repo, env={})
    assert result.project == config.DEFAULT_PROJECT
    assert result.provenance["project"] == "default"


def test_flag_beats_every_other_layer(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nproject = FromIni\n")
    write(os.path.join(repo, ".env"), "CHATNOTIFY_PROJECT=FromDotenv\n")
    result = config.load(
        flags={"project": "FromFlag"},
        cwd=repo,
        env={"CHATNOTIFY_PROJECT": "FromEnv"},
    )
    assert result.project == "FromFlag"
    assert result.provenance["project"] == "flag"


def test_env_beats_dotenv_and_ini(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nproject = FromIni\n")
    write(os.path.join(repo, ".env"), "CHATNOTIFY_PROJECT=FromDotenv\n")
    result = config.load(cwd=repo, env={"CHATNOTIFY_PROJECT": "FromEnv"})
    assert result.project == "FromEnv"
    assert result.provenance["project"] == "env: CHATNOTIFY_PROJECT"


def test_dotenv_beats_ini(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nproject = FromIni\n")
    write(os.path.join(repo, ".env"), "CHATNOTIFY_PROJECT=FromDotenv\n")
    result = config.load(cwd=repo, env={})
    assert result.project == "FromDotenv"
    assert result.provenance["project"] == ".env"


def test_repo_ini_is_used_when_no_higher_layer(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nproject = FromIni\n")
    result = config.load(cwd=repo, env={})
    assert result.project == "FromIni"
    assert result.provenance["project"] == ".chatnotify.ini"


def test_dotenv_handles_quotes_comments_and_blanks(repo):
    write(
        os.path.join(repo, ".env"),
        '# a comment\n\nCHATNOTIFY_PROJECT="Quoted Name"\nCHATNOTIFY_ENV=\'staging\'\n',
    )
    result = config.load(cwd=repo, env={})
    assert result.project == "Quoted Name"
    assert result.environment == "staging"


def test_values_are_trimmed(repo):
    result = config.load(cwd=repo, env={"CHATNOTIFY_PROJECT": "  Padded  "})
    assert result.project == "Padded"


def test_legacy_java_env_names_still_work(repo):
    result = config.load(
        cwd=repo,
        env={
            "PROJECT_NAME": "Legacy App",
            "GOOGLE_CHAT_WEBHOOK_URL": "https://chat.example/legacy",
            "ENVIRONMENT": "beta",
            "MESSAGE_TYPE": "TEXT",
        },
    )
    assert result.project == "Legacy App"
    assert result.webhook_url == "https://chat.example/legacy"
    assert result.environment == "beta"
    assert result.message_type == "TEXT"


def test_named_webhook_resolves_from_env(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nwebhook = qa-team\n")
    result = config.load(cwd=repo, env={"CHATNOTIFY_WEBHOOK_QA_TEAM": "https://chat.example/qa"})
    assert result.webhook_url == "https://chat.example/qa"
    assert result.provenance["webhook_url"] == "env: CHATNOTIFY_WEBHOOK_QA_TEAM"


def test_plain_webhook_url_beats_named_lookup(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nwebhook = qa-team\n")
    result = config.load(
        cwd=repo,
        env={
            "CHATNOTIFY_WEBHOOK_URL": "https://chat.example/direct",
            "CHATNOTIFY_WEBHOOK_QA_TEAM": "https://chat.example/qa",
        },
    )
    assert result.webhook_url == "https://chat.example/direct"


def test_message_type_is_uppercased_and_validated(repo):
    assert config.load(cwd=repo, env={"CHATNOTIFY_MESSAGE_TYPE": "text"}).message_type == "TEXT"
    assert config.load(cwd=repo, env={"CHATNOTIFY_MESSAGE_TYPE": "TEXTT"}).message_type == "CARD"


def test_invalid_message_type_records_fallback_provenance(repo):
    result = config.load(cwd=repo, env={"CHATNOTIFY_MESSAGE_TYPE": "nonsense"})
    assert "invalid" in result.provenance["message_type"]


def test_disabled_by_default_when_not_in_ci(repo):
    result = config.load(cwd=repo, env={})
    assert result.enabled is False
    assert result.provenance["enabled"] == "default (local)"


def test_enabled_automatically_in_ci(repo):
    result = config.load(cwd=repo, env={"CI": "true"})
    assert result.enabled is True
    assert result.provenance["enabled"] == "CI detected"


def test_explicit_enable_opts_in_locally(repo):
    result = config.load(cwd=repo, env={"CHATNOTIFY_ENABLED": "1"})
    assert result.enabled is True


def test_disabled_beats_enabled_and_ci(repo):
    result = config.load(
        cwd=repo, env={"CI": "true", "CHATNOTIFY_ENABLED": "1", "CHATNOTIFY_DISABLED": "1"}
    )
    assert result.enabled is False
    assert result.provenance["enabled"] == "env: CHATNOTIFY_DISABLED"


def test_report_patterns_split_on_commas(repo):
    result = config.load(flags={"report": "a/*.xml, b/**/*.xml"}, cwd=repo, env={})
    assert result.report_patterns == ("a/*.xml", "b/**/*.xml")


def test_report_patterns_default_to_none(repo):
    assert config.load(cwd=repo, env={}).report_patterns is None


def test_boolean_flags_are_respected(repo):
    result = config.load(flags={"only_on_failure": True, "quiet": True}, cwd=repo, env={})
    assert result.only_on_failure is True
    assert result.quiet is True


def test_machine_config_supplies_webhook(tmp_path, repo):
    machine = tmp_path / "cfg" / "chatnotify" / "config.ini"
    write(str(machine), "[chatnotify]\nwebhook_url = https://chat.example/machine\n")
    result = config.load(
        cwd=repo, env={"APPDATA": str(tmp_path / "cfg"), "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    )
    assert result.webhook_url == "https://chat.example/machine"
    assert result.provenance["webhook_url"] == "machine config"


def test_machine_config_named_webhooks_section(tmp_path, repo):
    machine = tmp_path / "cfg" / "chatnotify" / "config.ini"
    write(str(machine), "[webhooks]\nqa-team = https://chat.example/qa\n")
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nwebhook = qa-team\n")
    result = config.load(
        cwd=repo, env={"APPDATA": str(tmp_path / "cfg"), "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    )
    assert result.webhook_url == "https://chat.example/qa"


def test_malformed_ini_is_ignored_not_raised(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "this is not ini at all {{{")
    result = config.load(cwd=repo, env={})
    assert result.project == config.DEFAULT_PROJECT


def test_machine_config_path_uses_appdata_on_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    path = config.machine_config_path({"APPDATA": r"C:\Users\A\AppData\Roaming"})
    assert path.endswith(os.path.join("chatnotify", "config.ini"))
    assert "Roaming" in path
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_config.py -v
```

Expected: `ImportError: cannot import name 'config' from 'chatnotify'`.

- [ ] **Step 3: Write `src/chatnotify/config.py`**

```python
"""Six-layer configuration cascade. Every value records where it came from."""

import configparser
import os
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Tuple

from .models import CARD, TEXT

DEFAULT_PROJECT = "Unknown Project"
VALID_MESSAGE_TYPES = (CARD, TEXT)
_TRUTHY = ("1", "true", "yes", "on")

_ENV_KEYS = {
    "project": ("CHATNOTIFY_PROJECT", "PROJECT_NAME"),
    "environment": ("CHATNOTIFY_ENV", "ENVIRONMENT"),
    "webhook_url": ("CHATNOTIFY_WEBHOOK_URL", "GOOGLE_CHAT_WEBHOOK_URL"),
    "message_type": ("CHATNOTIFY_MESSAGE_TYPE", "MESSAGE_TYPE"),
}

_INI_KEYS = {
    "project": "project",
    "environment": "environment",
    "webhook_url": "webhook_url",
    "message_type": "message_type",
}


@dataclass(frozen=True)
class Config:
    project: str
    environment: Optional[str]
    webhook_url: Optional[str]
    message_type: str
    enabled: bool
    only_on_failure: bool
    quiet: bool
    report_patterns: Optional[Tuple[str, ...]]
    provenance: Dict[str, str] = field(default_factory=dict)


def _clean(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().strip('"').strip("'").strip()
    return text or None


def _truthy(value) -> bool:
    return _clean(value) is not None and str(value).strip().lower() in _TRUTHY


def machine_config_path(env: Optional[Mapping[str, str]] = None) -> str:
    env = os.environ if env is None else env
    if os.name == "nt":
        base = env.get("APPDATA") or os.path.expanduser("~")
    else:
        base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "chatnotify", "config.ini")


def _read_ini(path: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return configparser.ConfigParser()
    return parser


def _ini_get(parser: configparser.ConfigParser, section: str, option: str) -> Optional[str]:
    try:
        if parser.has_option(section, option):
            return _clean(parser.get(section, option))
    except configparser.Error:
        return None
    return None


def _read_dotenv(path: str) -> Dict[str, str]:
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, _, raw = stripped.partition("=")
                cleaned = _clean(raw)
                if cleaned is not None:
                    values[key.strip()] = cleaned
    except (OSError, UnicodeDecodeError):
        return {}
    return values


def _resolve_enabled(env: Mapping[str, str]) -> Tuple[bool, str]:
    if _truthy(env.get("CHATNOTIFY_DISABLED")):
        return False, "env: CHATNOTIFY_DISABLED"
    if _truthy(env.get("CHATNOTIFY_ENABLED")):
        return True, "env: CHATNOTIFY_ENABLED"
    if _clean(env.get("CI")):
        return True, "CI detected"
    return False, "default (local)"


def _resolve_webhook(
    layers, env: Mapping[str, str], repo_ini, machine_ini
) -> Tuple[Optional[str], str]:
    direct, source = layers("webhook_url")
    if direct:
        return direct, source

    name = _ini_get(repo_ini, "chatnotify", "webhook") or _clean(env.get("CHATNOTIFY_WEBHOOK_NAME"))
    if name:
        env_key = "CHATNOTIFY_WEBHOOK_" + name.upper().replace("-", "_").replace(" ", "_")
        from_env = _clean(env.get(env_key))
        if from_env:
            return from_env, "env: %s" % env_key
        from_machine = _ini_get(machine_ini, "webhooks", name)
        if from_machine:
            return from_machine, "machine config [webhooks]"
    return None, "unset"


def load(
    flags: Optional[Dict[str, object]] = None,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Config:
    flags = flags or {}
    cwd = os.getcwd() if cwd is None else cwd
    env = os.environ if env is None else env

    dotenv = _read_dotenv(os.path.join(cwd, ".env"))
    repo_ini = _read_ini(os.path.join(cwd, ".chatnotify.ini"))
    machine_ini = _read_ini(machine_config_path(env))

    def layers(name: str) -> Tuple[Optional[str], str]:
        from_flag = _clean(flags.get(name))
        if from_flag:
            return from_flag, "flag"
        for key in _ENV_KEYS.get(name, ()):
            found = _clean(env.get(key))
            if found:
                return found, "env: %s" % key
        for key in _ENV_KEYS.get(name, ()):
            found = _clean(dotenv.get(key))
            if found:
                return found, ".env"
        from_repo = _ini_get(repo_ini, "chatnotify", _INI_KEYS[name])
        if from_repo:
            return from_repo, ".chatnotify.ini"
        from_machine = _ini_get(machine_ini, "chatnotify", _INI_KEYS[name])
        if from_machine:
            return from_machine, "machine config"
        return None, "default"

    provenance = {}

    project, provenance["project"] = layers("project")
    environment, provenance["environment"] = layers("environment")
    webhook_url, provenance["webhook_url"] = _resolve_webhook(layers, env, repo_ini, machine_ini)

    raw_type, type_source = layers("message_type")
    if raw_type is None:
        message_type, type_source = CARD, "default"
    elif raw_type.upper() in VALID_MESSAGE_TYPES:
        message_type = raw_type.upper()
    else:
        message_type = CARD
        type_source = "default (invalid value %r from %s)" % (raw_type, type_source)
    provenance["message_type"] = type_source

    enabled, provenance["enabled"] = _resolve_enabled(env)

    raw_report = _clean(flags.get("report"))
    if raw_report:
        patterns = tuple(part.strip() for part in raw_report.split(",") if part.strip())
        provenance["report_patterns"] = "flag"
    else:
        patterns = None
        provenance["report_patterns"] = "auto-detect"

    return Config(
        project=project or DEFAULT_PROJECT,
        environment=environment,
        webhook_url=webhook_url,
        message_type=message_type,
        enabled=enabled,
        only_on_failure=bool(flags.get("only_on_failure")),
        quiet=bool(flags.get("quiet")),
        report_patterns=patterns,
        provenance=provenance,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_config.py -v
```

Expected: 23 passed.

- [ ] **Step 5: Commit**

```bash
git add src/chatnotify/config.py tests/test_config.py
git commit -m "feat: add six-layer config cascade with provenance tracking"
```

---

## Task 9: Command runner — exit codes, timing, interruption

**Files:**
- Create: `src/chatnotify/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `models.RunResult`.
- Produces: `runner.exec_command(argv: Sequence[str], grace_seconds: float = 5.0) -> RunResult`.

The child inherits the parent's stdout and stderr — no `subprocess.PIPE` — which gives
live, unbuffered pass-through for free and means the wrapped command's output is
byte-identical to running it directly. `shell=False` always, so nothing in a project name
or command can be shell-injected.

Exit-code conventions: `127` for a missing executable and `126` for one that exists but
cannot be run, matching POSIX shell behaviour; `130` for interruption.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_runner.py`.

```python
import sys

from chatnotify import runner


def python_command(code):
    return [sys.executable, "-c", code]


def test_successful_command_returns_zero():
    result = runner.exec_command(python_command("pass"))
    assert result.exit_code == 0
    assert result.interrupted is False


def test_failing_exit_code_is_passed_through_unchanged():
    result = runner.exec_command(python_command("import sys; sys.exit(7)"))
    assert result.exit_code == 7


def test_duration_is_measured():
    result = runner.exec_command(python_command("import time; time.sleep(0.2)"))
    assert result.duration_seconds >= 0.15


def test_missing_executable_returns_127():
    result = runner.exec_command(["definitely-not-a-real-binary-xyz"])
    assert result.exit_code == 127
    assert result.interrupted is False


def test_child_stdout_reaches_the_terminal(capfd):
    runner.exec_command(python_command("print('hello from child')"))
    assert "hello from child" in capfd.readouterr().out


def test_child_stderr_reaches_the_terminal(capfd):
    runner.exec_command(python_command("import sys; print('oops', file=sys.stderr)"))
    assert "oops" in capfd.readouterr().err


def test_keyboard_interrupt_marks_result_interrupted(monkeypatch):
    class FakeProcess:
        def __init__(self):
            self.terminated = False

        def wait(self, timeout=None):
            if not self.terminated:
                raise KeyboardInterrupt()
            return 130

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.terminated = True

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: FakeProcess())
    result = runner.exec_command(["anything"])
    assert result.interrupted is True
    assert result.exit_code == 130


def test_unkillable_child_is_force_killed(monkeypatch):
    events = []

    class StubbornProcess:
        def wait(self, timeout=None):
            if not events:
                raise KeyboardInterrupt()
            if events == ["terminate"]:
                events.append("timeout")
                raise runner.subprocess.TimeoutExpired(cmd="x", timeout=1)
            return 137

        def terminate(self):
            events.append("terminate")

        def kill(self):
            events.append("kill")

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: StubbornProcess())
    runner.exec_command(["anything"], grace_seconds=0.01)
    assert "kill" in events


def test_empty_argv_returns_127_without_raising():
    assert runner.exec_command([]).exit_code == 127
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_runner.py -v
```

Expected: `ImportError: cannot import name 'runner' from 'chatnotify'`.

- [ ] **Step 3: Write `src/chatnotify/runner.py`**

```python
"""Run the wrapped command. The child's stdio is inherited, its exit code untouched."""

import subprocess
import time
from typing import Sequence

from .models import RunResult

EXIT_NOT_FOUND = 127
EXIT_NOT_EXECUTABLE = 126
EXIT_INTERRUPTED = 130


def _stop(process, grace_seconds: float) -> None:
    try:
        process.terminate()
    except Exception:
        return
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait()
        except Exception:
            pass
    except Exception:
        pass


def exec_command(argv: Sequence[str], grace_seconds: float = 5.0) -> RunResult:
    if not argv:
        return RunResult(exit_code=EXIT_NOT_FOUND, duration_seconds=0.0)

    started = time.monotonic()
    try:
        process = subprocess.Popen(list(argv), shell=False)
    except FileNotFoundError:
        return RunResult(exit_code=EXIT_NOT_FOUND, duration_seconds=time.monotonic() - started)
    except (OSError, ValueError):
        return RunResult(
            exit_code=EXIT_NOT_EXECUTABLE, duration_seconds=time.monotonic() - started
        )

    interrupted = False
    try:
        exit_code = process.wait()
    except KeyboardInterrupt:
        interrupted = True
        _stop(process, grace_seconds)
        exit_code = EXIT_INTERRUPTED

    return RunResult(
        exit_code=exit_code,
        duration_seconds=time.monotonic() - started,
        interrupted=interrupted,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_runner.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/chatnotify/runner.py tests/test_runner.py
git commit -m "feat: run wrapped commands with transparent exit codes"
```

---

## Task 10: The `run` subcommand and the never-fatal guard

**Files:**
- Create: `src/chatnotify/cli.py`
- Create: `src/chatnotify/__main__.py`
- Test: `tests/test_cli_run.py`

**Interfaces:**
- Consumes: `config.load`, `ci.detect`, `render.start`, `render.finish`, `reports.collect`, `runner.exec_command`, `transport.post`, `models.resolve_status`, `models.PASSED`, `models.RunMeta`.
- Produces: `cli.split_argv(argv: Sequence[str]) -> Tuple[List[str], List[str]]`; `cli.build_parser() -> argparse.ArgumentParser`; `cli.main(argv: Optional[Sequence[str]] = None) -> int`; `cli.entrypoint() -> None` (calls `sys.exit`); `cli.EXIT_USAGE = 2`. Tasks 11 and 12 add `cli.doctor_command` and `cli.init_command` and register them in `build_parser`.

`argparse`'s `REMAINDER` is unreliable with interspersed options, so `--` is split off
`sys.argv` manually before parsing. Everything after the first `--` is the child command,
untouched and unparsed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_run.py`.

```python
import sys

from chatnotify import cli

PY = sys.executable


def base_env(webhook):
    return {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CHATNOTIFY_ENABLED": "1"}


def test_split_argv_separates_own_flags_from_command():
    own, command = cli.split_argv(["run", "--project", "X", "--", "pytest", "-v"])
    assert own == ["run", "--project", "X"]
    assert command == ["pytest", "-v"]


def test_split_argv_with_no_separator_yields_empty_command():
    own, command = cli.split_argv(["run", "--project", "X"])
    assert own == ["run", "--project", "X"]
    assert command == []


def test_split_argv_keeps_double_dash_inside_child_command():
    own, command = cli.split_argv(["run", "--", "pytest", "--", "-k", "x"])
    assert command == ["pytest", "--", "-k", "x"]


def test_run_without_command_returns_usage_error(capsys):
    assert cli.main(["run", "--project", "X"]) == cli.EXIT_USAGE
    assert "no command" in capsys.readouterr().err


def test_exit_code_of_child_is_returned(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    code = cli.main(["run", "--project", "X", "--", PY, "-c", "import sys; sys.exit(3)"])
    assert code == 3


def test_start_and_finish_cards_are_both_posted(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    cli.main(["run", "--project", "X", "--", PY, "-c", "pass"])
    assert len(webhook.requests) == 2
    assert webhook.requests[0]["body"]["cardsV2"][0]["card"]["header"]["subtitle"] == "Started"
    assert webhook.requests[1]["body"]["cardsV2"][0]["card"]["header"]["subtitle"] == "Passed"


def test_both_messages_share_one_thread_key(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    cli.main(["run", "--project", "X", "--", PY, "-c", "pass"])
    first = webhook.requests[0]["path"]
    second = webhook.requests[1]["path"]
    assert "threadKey=" in first
    assert first.split("threadKey=")[1] == second.split("threadKey=")[1]


def test_counts_from_report_appear_in_finish_card(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    report = tmp_path / "junit.xml"
    code = (
        "open(r'%s','w').write('<testsuite tests=\\'1\\'>"
        "<testcase classname=\\'c\\' name=\\'t\\'/></testsuite>')" % report
    )
    cli.main(["run", "--project", "X", "--", PY, "-c", code])
    rendered = str(webhook.requests[1]["body"])
    assert "Total Tests" in rendered


def test_unreachable_webhook_does_not_change_exit_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": "http://127.0.0.1:1/hook", "CHATNOTIFY_ENABLED": "1"},
    )
    monkeypatch.setattr("chatnotify.transport.time.sleep", lambda _: None)
    assert cli.main(["run", "--", PY, "-c", "import sys; sys.exit(4)"]) == 4


def test_missing_webhook_still_runs_the_command(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {"CHATNOTIFY_ENABLED": "1"})
    assert cli.main(["run", "--", PY, "-c", "import sys; sys.exit(5)"]) == 5
    assert "webhook" in capsys.readouterr().err.lower()


def test_disabled_posts_nothing_but_still_runs(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CHATNOTIFY_DISABLED": "1"},
    )
    assert cli.main(["run", "--", PY, "-c", "import sys; sys.exit(6)"]) == 6
    assert webhook.requests == []


def test_only_on_failure_suppresses_both_cards_when_passing(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    cli.main(["run", "--only-on-failure", "--", PY, "-c", "pass"])
    assert webhook.requests == []


def test_only_on_failure_posts_finish_card_when_failing(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", base_env(webhook))
    cli.main(["run", "--only-on-failure", "--", PY, "-c", "import sys; sys.exit(1)"])
    assert len(webhook.requests) == 1
    assert webhook.requests[0]["body"]["cardsV2"][0]["card"]["header"]["subtitle"] == "Failed"


def test_version_flag_prints_version(capsys):
    try:
        cli.main(["--version"])
    except SystemExit:
        pass
    assert "1.0.0" in capsys.readouterr().out


def test_entrypoint_exits_two_when_crash_precedes_child(monkeypatch, capsys):
    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "main", explode)
    try:
        cli.entrypoint()
    except SystemExit as exit_signal:
        assert exit_signal.code == cli.EXIT_USAGE
    assert "boom" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_cli_run.py -v
```

Expected: `ImportError: cannot import name 'cli' from 'chatnotify'`.

- [ ] **Step 3: Write `src/chatnotify/cli.py`**

```python
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
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        if _child_exit_code is not None:
            sys.exit(_child_exit_code)
        sys.exit(EXIT_USAGE)
```

`doctor_command` and `init_command` do not exist yet, so `main` will raise
`NameError` for those subcommands until Tasks 11 and 12 land. That is expected —
the `run` tests do not reach those branches.

- [ ] **Step 4: Write `src/chatnotify/__main__.py`**

```python
from .cli import entrypoint

entrypoint()
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_cli_run.py -v
```

Expected: 15 passed.

- [ ] **Step 6: Commit**

```bash
git add src/chatnotify/cli.py src/chatnotify/__main__.py tests/test_cli_run.py
git commit -m "feat: add run subcommand with exit-code transparency"
```

---

## Task 11: The `doctor` subcommand

**Files:**
- Modify: `src/chatnotify/cli.py` (add `doctor_command`)
- Test: `tests/test_cli_doctor.py`

**Interfaces:**
- Consumes: `config.load`, `config.machine_config_path`, `transport.post`, `render.start`, `models.RunMeta`, `ci.detect`.
- Produces: `cli.doctor_command(args: argparse.Namespace) -> int` — returns 0 when a test card was delivered, 1 otherwise.

Six config layers are only defensible if their outcome is inspectable. This command is
that mitigation: it prints each resolved value beside the layer that produced it, then
proves the webhook works.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_doctor.py`.

```python
from chatnotify import cli


def test_doctor_reports_provenance_for_each_value(tmp_path, webhook, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".chatnotify.ini").write_text("[chatnotify]\nproject = FromIni\n", encoding="utf-8")
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CHATNOTIFY_ENV": "staging", "CI": "true"},
    )
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "FromIni" in out
    assert ".chatnotify.ini" in out
    assert "staging" in out
    assert "env: CHATNOTIFY_ENV" in out
    assert "CI detected" in out


def test_doctor_sends_a_test_card(tmp_path, webhook, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CI": "true"},
    )
    cli.main(["doctor"])
    assert len(webhook.requests) == 1


def test_doctor_never_prints_the_webhook_url(tmp_path, webhook, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ",
        {"CHATNOTIFY_WEBHOOK_URL": webhook.url, "CI": "true"},
    )
    cli.main(["doctor"])
    captured = capsys.readouterr()
    assert "SECRET123" not in captured.out
    assert "SECRET123" not in captured.err


def test_doctor_returns_one_when_no_webhook_configured(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    assert cli.main(["doctor"]) == 1
    assert "not configured" in capsys.readouterr().out


def test_doctor_returns_one_when_webhook_unreachable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "chatnotify.config.os.environ", {"CHATNOTIFY_WEBHOOK_URL": "http://127.0.0.1:1/h"}
    )
    monkeypatch.setattr("chatnotify.transport.time.sleep", lambda _: None)
    assert cli.main(["doctor"]) == 1


def test_doctor_prints_version_and_machine_config_path(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chatnotify.config.os.environ", {})
    cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "1.0.0" in out
    assert "config.ini" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_cli_doctor.py -v
```

Expected: `NameError: name 'doctor_command' is not defined`.

- [ ] **Step 3: Add `doctor_command` to `src/chatnotify/cli.py`**

Insert above `def main(`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_cli_doctor.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/chatnotify/cli.py tests/test_cli_doctor.py
git commit -m "feat: add doctor subcommand reporting config provenance"
```

---

## Task 12: The `init` subcommand

**Files:**
- Modify: `src/chatnotify/cli.py` (add `init_command`)
- Test: `tests/test_cli_init.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `cli.init_command(args: argparse.Namespace) -> int` — returns 0 on success, 1 if `.chatnotify.ini` already exists.

Per-repo friction is what kills team-wide adoption, so onboarding a repo is one command.
It also appends `.env` to `.gitignore`, which closes defect 14 from the Java library by
construction rather than by documentation.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_init.py`.

```python
import os

from chatnotify import cli


def test_init_writes_config_with_directory_name(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / "payments-api"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    assert cli.main(["init"]) == 0
    content = (project_dir / ".chatnotify.ini").read_text(encoding="utf-8")
    assert "[chatnotify]" in content
    assert "project = payments-api" in content
    assert "CHATNOTIFY_WEBHOOK_URL" in capsys.readouterr().out


def test_init_never_writes_a_webhook_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["init"])
    content = (tmp_path / ".chatnotify.ini").read_text(encoding="utf-8")
    assert "https://" not in content


def test_init_creates_gitignore_with_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["init"])
    assert ".env" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_init_appends_dotenv_to_existing_gitignore(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("target/\n", encoding="utf-8")
    cli.main(["init"])
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "target/" in content
    assert ".env" in content


def test_init_does_not_duplicate_dotenv_entry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    cli.main(["init"])
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert content.count(".env") == 1


def test_init_refuses_to_overwrite_existing_config(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".chatnotify.ini").write_text("[chatnotify]\nproject = Keep Me\n", encoding="utf-8")
    assert cli.main(["init"]) == 1
    assert "Keep Me" in (tmp_path / ".chatnotify.ini").read_text(encoding="utf-8")
    assert "already exists" in capsys.readouterr().err


def test_init_honours_project_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["init"])
    os.remove(str(tmp_path / ".chatnotify.ini"))
    parser = cli.build_parser()
    args = parser.parse_args(["init"])
    args.project = "Explicit Name"
    cli.init_command(args)
    content = (tmp_path / ".chatnotify.ini").read_text(encoding="utf-8")
    assert "project = Explicit Name" in content
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_cli_init.py -v
```

Expected: `NameError: name 'init_command' is not defined`.

- [ ] **Step 3: Add `init_command` to `src/chatnotify/cli.py`**

Insert above `def main(`:

```python
_INIT_TEMPLATE = """; chatnotify repository config - safe to commit, contains no secrets.
; Set the webhook URL in your environment instead:
;   CHATNOTIFY_WEBHOOK_URL=https://chat.googleapis.com/...
[chatnotify]
project = %s
message_type = CARD
"""


def _ensure_gitignored(path: str, entry: str) -> None:
    existing = ""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                existing = handle.read()
        except (OSError, UnicodeDecodeError):
            return
    if entry in existing.split():
        return
    separator = "" if (not existing or existing.endswith("\n")) else "\n"
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("%s%s\n" % (separator, entry))
    except OSError:
        pass


def init_command(args: argparse.Namespace) -> int:
    target = os.path.join(os.getcwd(), ".chatnotify.ini")
    if os.path.exists(target):
        print("chatnotify: .chatnotify.ini already exists; not overwriting", file=sys.stderr)
        return 1

    project = getattr(args, "project", None) or os.path.basename(os.path.abspath(os.getcwd()))
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(_INIT_TEMPLATE % project)

    _ensure_gitignored(os.path.join(os.getcwd(), ".gitignore"), ".env")

    print("Created .chatnotify.ini with project = %s" % project)
    print("Added .env to .gitignore")
    print("")
    print("Next: set your webhook URL, then verify with `chatnotify doctor`")
    print("  CHATNOTIFY_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/...")
    return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_cli_init.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/chatnotify/cli.py tests/test_cli_init.py
git commit -m "feat: add init subcommand for one-command repo onboarding"
```

---

## Task 13: End-to-end verification, packaging, and CI

**Files:**
- Create: `tests/test_e2e.py`
- Create: `README.md`
- Create: `.github/workflows/ci.yml`
- Test: `tests/test_e2e.py`

**Interfaces:**
- Consumes: the installed `chatnotify` console script and `python -m chatnotify`.
- Produces: no new API. This task proves the assembled tool works against a real pytest run.

Every prior task tested a module in isolation. This one runs the actual CLI as a
subprocess against a real test suite and a real HTTP server — the only test that would
catch a wiring mistake between correctly-working parts.

- [ ] **Step 1: Write the end-to-end test**

Create `tests/test_e2e.py`.

```python
import json
import os
import subprocess
import sys

SUITE = """
def test_passes():
    assert True


def test_also_passes():
    assert True


def test_fails():
    assert 1 == 2


def test_skipped():
    import pytest
    pytest.skip("not ready")
"""


def run_cli(cwd, env, *args):
    command = [sys.executable, "-m", "chatnotify"] + list(args)
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)


def test_real_pytest_run_produces_accurate_cards(tmp_path, webhook):
    (tmp_path / "test_sample.py").write_text(SUITE, encoding="utf-8")
    env = dict(os.environ)
    env["CHATNOTIFY_WEBHOOK_URL"] = webhook.url
    env["CHATNOTIFY_ENABLED"] = "1"
    env["CHATNOTIFY_PROJECT"] = "E2E Suite"

    completed = run_cli(
        str(tmp_path),
        env,
        "run",
        "--",
        sys.executable,
        "-m",
        "pytest",
        "test_sample.py",
        "--junitxml=junit.xml",
    )

    assert completed.returncode == 1, completed.stderr
    assert len(webhook.requests) == 2

    start = webhook.requests[0]["body"]["cardsV2"][0]["card"]
    assert start["header"]["title"] == "E2E Suite"
    assert start["header"]["subtitle"] == "Started"

    finish = json.dumps(webhook.requests[1]["body"])
    assert '"subtitle": "Failed"' in finish
    assert '"topLabel": "Total Tests", "text": "4"' in finish or '"text": "4"' in finish
    assert "test_fails" in finish


def test_plain_script_reports_exit_code_only(tmp_path, webhook):
    (tmp_path / "job.py").write_text("import sys; sys.exit(0)", encoding="utf-8")
    env = dict(os.environ)
    env["CHATNOTIFY_WEBHOOK_URL"] = webhook.url
    env["CHATNOTIFY_ENABLED"] = "1"

    completed = run_cli(str(tmp_path), env, "run", "--project", "ETL", "--", sys.executable, "job.py")

    assert completed.returncode == 0
    finish = json.dumps(webhook.requests[1]["body"])
    assert '"subtitle": "Passed"' in finish
    assert "Exit Code" in finish
    assert "Total Tests" not in finish


def test_stale_report_is_not_reported_as_current(tmp_path, webhook):
    stale = tmp_path / "junit.xml"
    stale.write_text(
        '<testsuite tests="9"><testcase classname="old" name="stale"/></testsuite>',
        encoding="utf-8",
    )
    os.utime(str(stale), (0, 0))
    (tmp_path / "job.py").write_text("pass", encoding="utf-8")

    env = dict(os.environ)
    env["CHATNOTIFY_WEBHOOK_URL"] = webhook.url
    env["CHATNOTIFY_ENABLED"] = "1"

    run_cli(str(tmp_path), env, "run", "--project", "Stale", "--", sys.executable, "job.py")

    finish = json.dumps(webhook.requests[1]["body"])
    assert "stale" not in finish
    assert "Total Tests" not in finish


def test_child_output_is_not_swallowed(tmp_path):
    (tmp_path / "loud.py").write_text("print('CHILD SPEAKING')", encoding="utf-8")
    env = dict(os.environ)
    env["CHATNOTIFY_DISABLED"] = "1"
    completed = run_cli(str(tmp_path), env, "run", "--", sys.executable, "loud.py")
    assert "CHILD SPEAKING" in completed.stdout
```

- [ ] **Step 2: Run the end-to-end tests**

```bash
python -m pytest tests/test_e2e.py -v
```

Expected: 4 passed. If the `Total Tests` assertion fails on key ordering, print
`webhook.requests[1]["body"]` and assert on the parsed dict rather than the JSON string.

- [ ] **Step 3: Run the whole suite**

```bash
python -m pytest -v
```

Expected: 111 passed.

- [ ] **Step 4: Write `README.md`**

```markdown
# chatnotify

Post Google Chat notifications when any test suite or script starts and finishes.
Works with TestNG, JUnit, pytest, Jest, Mocha, Playwright, Cypress, and plain scripts —
one tool, no per-framework plugins.

## Install

    pip install "git+https://github.com/DhruvilDesai1/chatnotify@v1.0.0"

No runtime dependencies. Python 3.8+.

## Quickstart

    cd your-repo
    chatnotify init
    export CHATNOTIFY_WEBHOOK_URL="https://chat.googleapis.com/v1/spaces/..."
    chatnotify doctor

Then wrap any command:

    chatnotify run -- pytest tests/ --junitxml=junit.xml
    chatnotify run -- npx playwright test
    chatnotify run -- mvn test
    chatnotify run -- python etl.py

`chatnotify run` exits with exactly the code your command exited with, streams its
output unchanged, and can never fail your build — an unreachable or misconfigured
webhook is logged to stderr and ignored.

## Where counts come from

Pass/fail counts are read from JUnit XML, which every supported runner can emit:

| Runner | Flag |
|---|---|
| pytest | `--junitxml=junit.xml` |
| Maven Surefire | emitted automatically to `target/surefire-reports/` |
| Jest | `--reporters=default --reporters=jest-junit` |
| Mocha | `--reporter mocha-junit-reporter` |
| Playwright | `--reporter=junit` |
| Cypress | `--reporter junit` |

Common locations are auto-detected. Use `--report "path/**/*.xml"` to be explicit.
A report older than the current run is ignored, so stale results are never reported
as current. With no report at all, the finish card shows duration and exit code —
correct behaviour for plain scripts.

## Configuration

Highest priority first:

1. CLI flag — `--project`, `--env`, `--message-type`, `--report`
2. Environment variable — `CHATNOTIFY_WEBHOOK_URL`, `CHATNOTIFY_PROJECT`, `CHATNOTIFY_ENV`
3. `.env` in the repo root
4. `.chatnotify.ini` in the repo root (committed, no secrets)
5. Machine config — `%APPDATA%\chatnotify\config.ini` or `~/.config/chatnotify/config.ini`
6. Built-in defaults

`chatnotify doctor` prints every value with the layer it came from.

`PROJECT_NAME`, `ENVIRONMENT`, `MESSAGE_TYPE`, and `GOOGLE_CHAT_WEBHOOK_URL` are
accepted as legacy aliases, so `.env` files from `GoogleChatUtilityLib` keep working.

## Enablement

Notifications are **on in CI, off locally** by default (detected via `CI`), so local
test runs do not flood a shared space.

- `CHATNOTIFY_ENABLED=1` — opt in locally
- `CHATNOTIFY_DISABLED=1` — silence everywhere, overrides everything
- `--only-on-failure` — send the finish card only when the run failed
- `--quiet` — silence chatnotify's own stderr warnings (does not stop posting)

## Advanced: named webhooks

For multiple spaces, reference a webhook by name so the committed config stays
identical for everyone:

    # .chatnotify.ini
    [chatnotify]
    project = Payments API
    webhook = qa-team

Each machine or CI runner resolves the name via `CHATNOTIFY_WEBHOOK_QA_TEAM`, or a
`[webhooks]` section in its machine config.

## No pip on the runner?

Each release attaches a single-file `chatnotify.pyz`:

    python chatnotify.pyz run -- pytest tests/
```

- [ ] **Step 5: Write `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: python -m pytest -v

  zipapp:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Build single-file zipapp
        run: |
          python -m zipapp src/chatnotify -m "chatnotify.cli:entrypoint" -p "/usr/bin/env python3" -o chatnotify.pyz
          python chatnotify.pyz --version
      - uses: actions/upload-artifact@v4
        with:
          name: chatnotify-pyz
          path: chatnotify.pyz
```

- [ ] **Step 6: Verify the zipapp build locally**

```bash
python -m zipapp src/chatnotify -m "chatnotify.cli:entrypoint" -o chatnotify.pyz && python chatnotify.pyz --version
```

Expected: `1.0.0`. The `src/chatnotify` directory is zipped as the package root, so the
relative imports inside the modules resolve.

- [ ] **Step 7: Confirm the zero-dependency constraint mechanically**

```bash
grep -rnE "^(import|from) " src/chatnotify/ | grep -vE "(argparse|configparser|dataclasses|datetime|glob|html|json|os|subprocess|sys|time|traceback|typing|urllib|uuid|xml|from \.)"
```

Expected: no output. Any line printed is a third-party import and a constraint violation.

- [ ] **Step 8: Commit and tag**

```bash
git add tests/test_e2e.py README.md .github/workflows/ci.yml
git commit -m "test: add end-to-end verification, README, and CI matrix"
git tag v1.0.0
```

---

## Self-Review Notes

Checked against the spec, section by section:

| Spec section | Covered by |
|---|---|
| 4 — module boundaries, data flow, 3 invariants | Tasks 1, 2, 9, 10; invariants tested in `test_models.py`, `test_transport.py`, `test_cli_run.py` |
| 5 — CLI surface, report discovery, staleness | Tasks 4, 10, 11, 12 |
| 6 — six-layer cascade, provenance, named webhooks, enablement | Task 8, exposed by Task 11 |
| 7 — start card, finish card, threading, truncation, TEXT mode | Tasks 5, 6; threading asserted in Task 10 |
| 8 — every failure-mode row | Task 2 (webhook errors, retries, timeout), Task 3 (malformed XML), Task 4 (stale/missing reports), Task 6 (truncation), Task 9 (127, interruption), Task 10 (no webhook, crash guard) |
| 9 — testing strategy, CI matrix | Every task's test file; matrix in Task 13 |
| 11 — pip-from-tag and zipapp distribution | Task 13 |
| 13 — success criteria 1-6 | Criteria 1 and 5 in Task 13's e2e tests; 2 and 3 in Tasks 2 and 10; 4 in Task 12; 6 in Task 13's matrix |

Spec section 10 (the Java `v1.1.0` patch) is deliberately absent — it is an independent
subsystem in a different language and repository, planned separately in
`2026-09-07-google-chat-utility-lib-v1.1.0.md`.

Type consistency verified across tasks: `TestCounts.failed_names` is a `Tuple[str, ...]`
everywhere; `reports.collect` and `render.finish` agree that `None` means "no counts";
`RunResult.duration_seconds` is a float consumed only by `render.format_duration`;
`resolve_status` is the single definition of pass/fail, called by `render.finish` and
`cli.run_command` and nowhere else.

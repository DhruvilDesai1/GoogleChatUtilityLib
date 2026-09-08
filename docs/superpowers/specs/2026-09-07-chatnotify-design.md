# chatnotify — Cross-Language Test Run Notifier

**Date:** 2026-09-07
**Status:** Approved design, pending implementation plan
**Supersedes:** `GoogleChatUtilityLib` (TestNG-only Java library)

## 1. Problem

`GoogleChatUtilityLib` sends Google Chat notifications when a TestNG suite starts
and finishes. It works, but it only works for TestNG. The team's automation spans
four categories of runnable thing:

- Java: TestNG / JUnit / Maven Surefire
- Python: pytest
- JavaScript: Jest, Mocha, Playwright, Cypress
- Plain scripts with no test framework at all (`python etl.py`, `node job.js`, shell)

The goal is one utility covering all four, reporting start, end, and pass/fail
counts, usable across every repo owned by the author and their team.

The existing library also carries defects serious enough that it should not be
spread further in its current form (Section 2).

## 2. Defects in the current Java library

### Will break production

1. **A failed webhook can abort the entire test suite.**
   `GoogleChatNotifier.java:70` calls `.then().statusCode(200)`, which throws
   `java.lang.AssertionError`. `AssertionError` extends `Error`, not `Exception`,
   so the `catch (Exception e)` on line 73 never fires. A 404, 403, or 429 from
   Chat propagates out of `sendNotification` → `onStart` → TestNG, aborting the
   run. A notification tool that can fail the build is worse than no tool.
2. **No HTTP timeout.** RestAssured is used with default config, which sets
   neither connect nor socket timeout. A hanging Chat endpoint hangs the suite
   indefinitely at `onStart`.
3. **Unbounded payload.** `SuiteListener.java:60-76` appends every test class name
   into one card. A large suite exceeds Google Chat's payload limit, returns 400,
   and triggers defect 1 — aborting the run.
4. **No retry.** A transient 429 or 503 silently loses the notification.

### Correctness

5. **Retried tests are double-counted.** With an `IRetryAnalyzer`, a test that
   fails then passes appears in both `getFailedTests()` and `getPassedTests()`,
   so totals exceed reality. `getFailedButWithinSuccessPercentageTests()` is
   never counted.
6. **Static mutable config, unsynchronized.** `GoogleChatConfig` is global static
   state; parallel or sequential suites in one JVM bleed configuration.
7. **`.env` re-read from disk on every lookup** — four `Dotenv.configure().load()`
   calls per notification, none cached.
8. **Config unvalidated and untrimmed.** `messageType=TEXTT` falls through to
   CARD silently; a trailing space in `.env` breaks matching.

### Adoption risk

9. **RestAssured for a single POST.** Drags in Groovy, Hamcrest, and a large
   transitive tree. Embedded in every project it will collide with consumers
   using a different RestAssured version.
10. **`org.json` has a non-OSI license.** The "JSON License" and its
    "Good, not Evil" clause is banned at many organisations and by Apache.
11. **Java 21 forced on consumers.** `source/target 21` excludes any repo on
    JDK 17 or 11.
12. **`extends BaseTest` burns the single inheritance slot.** Most suites already
    have their own base class. TestNG's `ServiceLoader` mechanism
    (`META-INF/services/org.testng.ITestNGListener`) registers a listener with
    zero consumer code and no `static {}` block.
13. **`pom.xml` says `1.0.0` while tags are at `v1.0.1`.**
14. **README instructs users to put a webhook secret in `.env`** without a
    gitignore warning.
15. **No tests and no CI.**

## 3. Decisions taken

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | Single CLI wrapper | One codebase serves all four categories. JUnit XML is the common denominator across every runner in use, so all four JS frameworks come free with no framework-specific code. Only option that handles plain scripts. |
| Implementation language | Python 3.8+, stdlib only | Already in the stack; zero dependencies means it can never conflict with a consuming project — the direct lesson of defects 9 and 10; stdlib-only permits single-file distribution. |
| Config format | INI via `configparser` | `tomllib` is stdlib only in 3.11+; TOML would require a third-party parser. |
| Webhook count | One, documented; named webhooks supported | Team aims for a single space but wants freedom over where the URL is set. Name resolution is ~30 lines and stays in advanced docs. |
| Existing Java library | Patch `v1.1.0`, then retire | Bounded work protecting anything already depending on `v1.0.1`; no orphaned consumers. |
| Distribution | pip from git tag, plus `zipapp` | Preserves the tag-based release workflow already in use with JitPack. |

Rejected: three native per-language packages (six-plus integrations to build and
maintain, and no story for plain scripts); a hybrid CLI-plus-listener (two card
renderers to keep in sync); a central webhook service (needs hosting and uptime).

## 4. Architecture

Python package `chatnotify`. Six modules, each with one responsibility. Only
three touch the outside world.

| Module | Responsibility | I/O |
|---|---|---|
| `cli.py` | Argument parsing, subcommand dispatch, exit-code passthrough | none |
| `config.py` | Resolve settings across the cascade into a frozen `Config`, recording each value's provenance | files, env |
| `runner.py` | Execute the wrapped command, time it, capture exit code, forward signals | subprocess |
| `reports.py` | Discover and parse JUnit XML into `TestCounts` | files |
| `render.py` | `(RunMeta, RunResult, TestCounts) -> payload dict` | **pure** |
| `transport.py` | POST with timeout and retry; never raises | network |

`render.py` is a pure function so the card layout is fully testable against
golden JSON fixtures with no network or filesystem. It is also the single seam
where a future Slack or Teams backend would attach.

### Data flow

```
chatnotify run --project X -- pytest tests/
  |
  |- config.load()                              -> Config
  |- render.start(meta)          -> payload     -> transport.post()
  |- runner.exec(command)                       -> RunResult(exit_code, duration, started_at)
  |- reports.collect(paths, since=started_at)   -> TestCounts | None
  |- render.finish(meta, result, counts)        -> transport.post()
  `- sys.exit(result.exit_code)                    the child's code, unchanged
```

### Invariants

1. **Exit-code transparency.** `chatnotify run -- pytest tests/` exits with
   exactly what `pytest` exited with. Stdout and stderr stream through live and
   unbuffered. Wrapping a command must never change whether CI passes.
2. **Notification failure is never fatal.** `transport.post()` catches
   `BaseException`, writes to stderr, and returns — except `KeyboardInterrupt` and
   `SystemExit`, which are re-raised. The rule exists so a *webhook* problem cannot
   fail a build; a user asking the process to stop is not a webhook problem, and
   swallowing Ctrl-C would leave the process unresponsive for up to ~30s during retries. A top-level guard in `cli.py`
   does the same for the whole program: a bug in `chatnotify` exits with the
   child's code, not its own.
3. **Exit code is authoritative for pass/fail.** Status is `FAILED` if
   `exit_code != 0` **or** `failed > 0` — never from counts alone. A pytest
   collection error, an OOM kill, or a crash before any test runs all yield zero
   failures and a non-zero exit. Reporting that as "Passed" would be the worst
   possible defect in this tool.

## 5. CLI surface

```bash
chatnotify run --project "Payments API" -- pytest tests/ --junitxml=out.xml
chatnotify run --project "Web E2E" --report "test-results/**/*.xml" -- npx playwright test
chatnotify run --project "Nightly ETL" -- python etl.py
chatnotify init
chatnotify doctor
chatnotify --version
```

- `run` — the entire tool. Everything else is setup and diagnosis.
- `init` — writes `.chatnotify.ini`, guesses the project name from the git remote
  or directory, appends `.env` to `.gitignore` if absent, prints the env var to
  set. Onboarding a repo becomes one command; per-repo friction is what kills
  team-wide adoption.
- `doctor` — prints every resolved value with its provenance, then sends a test
  card.

Flags: `--project`, `--env`, `--webhook-url`, `--message-type {CARD,TEXT}`,
`--report <glob>`, `--only-on-failure`, `--quiet`.

Separate `start` / `finish` subcommands for split CI jobs are **not** in scope.
`run` covers every case described; that gets added only when a real multi-job
pipeline needs it.

### Report discovery

With `--report <glob>`, that glob is authoritative. Without it, common locations
are auto-detected: `target/surefire-reports/*.xml`, `junit.xml`,
`test-results/**/*.xml`, `reports/**/*.xml`.

**Auto-detected files count only if modified after the run started.** Otherwise a
stale report from a previous run is parsed and reported as the current result —
a silent, confidence-destroying defect. When no report is found, the finish card
carries duration and exit code only, which is the correct behaviour for plain
scripts.

When auto-detection matches multiple distinct report sets, the newest set is used
and the choice is printed to stderr so it is visible.

## 6. Configuration

Resolution order, highest priority first:

| # | Source | Example |
|---|---|---|
| 1 | CLI flag | `--project "Payments API"` |
| 2 | Environment variable | `CHATNOTIFY_WEBHOOK_URL`, `CHATNOTIFY_PROJECT` |
| 3 | `.env` in repo root | `CHATNOTIFY_PROJECT=Payments API` |
| 4 | `.chatnotify.ini` in repo root | committed, contains no secrets |
| 5 | Machine config | `%APPDATA%\chatnotify\config.ini` (Windows) or `~/.config/chatnotify/config.ini` |
| 6 | Built-in default | `message_type = CARD` |

Six layers is justified by the requirement that the team be able to set config
"in env or wherever they feel like". The cost is debuggability, mitigated by
`doctor` reporting the source of every value:

```
$ chatnotify doctor
project       Payments API      (.chatnotify.ini)
environment   staging           (env: CHATNOTIFY_ENV)
webhook_url   https://chat.g... (machine config)   reachable
message_type  CARD              (default)
enabled       yes               (CI detected)
version       chatnotify 1.0.0
-> test card sent successfully
```

### Webhook resolution

1. `--webhook-url` flag
2. `CHATNOTIFY_WEBHOOK_URL` — the documented default path
3. If the repo declares `webhook = <name>`: `CHATNOTIFY_WEBHOOK_<NAME_UPPER>`,
   then machine config `[webhooks] <name> = <url>`
4. Machine config `[chatnotify] webhook_url = <url>`
5. `GOOGLE_CHAT_WEBHOOK_URL` — legacy alias

`PROJECT_NAME`, `ENVIRONMENT`, and `MESSAGE_TYPE` are likewise accepted as legacy
aliases, so `.env` files written for the Java library keep working untouched.

Committed repo config never contains a URL:

```ini
# .chatnotify.ini
[chatnotify]
project = Payments API
webhook = qa-team
message_type = CARD
```

### Enablement

Default **enabled in CI, disabled locally**, detected via the `CI` env var. If
every teammate's local `pytest` run posted to the team space, the space would be
unusable within a day and the tool would be removed. Opt in locally rather than
opt out.

- `CHATNOTIFY_ENABLED=1` — opt in from a local machine, overriding the default
- `CHATNOTIFY_DISABLED=1` — silence entirely, overriding everything including CI
  detection. Takes precedence over `CHATNOTIFY_ENABLED`.
- `--only-on-failure` — suppress the start card and send the finish card only
  when the run failed

When notifications are disabled, `run` still executes the wrapped command
normally and still exits with its code. Disabling suppresses posting, nothing
else.

`--quiet` is unrelated to enablement: it silences `chatnotify`'s own stderr
diagnostics (the "no webhook configured" and "webhook returned 404" warnings)
without changing whether cards are posted. The wrapped command's own output is
never suppressed by it.

## 7. Card content

**Start card.** Project name as header. Start time, the command being run, and
environment *only if set* (preserving current behaviour). When CI is detected:
branch, commit, triggering actor, and a **View build** button
(`buttonList` / `openLink`).

**Finish card.** Status in the subtitle — **Passed** or **Failed** — with:

- Duration (absent from the current library entirely)
- Total / Passed / Failed / Skipped
- Failed test names, first 10, then "and N more"
- Exit code, always — the only signal plain scripts produce
- **View build** button when CI is detected
- `chatnotify vX.Y.Z` in the footer, so a card of unexpected shape is traceable
  to the version that produced it

Failed test names come from the same parse as the counts: JUnit XML `<testcase>`
elements carry `<failure>` children, so this works in every language at no extra
cost. It closes gap 9 in the current library.

**Threading.** Start and finish are posted with
`&threadKey=<run_id>&messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD`, so
each run is one thread rather than two loose messages. In a shared space with
many projects posting, this is the difference between readable and chaotic.
Requires the space to be in threaded mode; the `messageReplyOption` value makes
it fall back to a new message otherwise.

**Truncation.** Every list has a hard cap with an "and N more" suffix, applied in
`render.py`. Because the renderer is pure, truncation is fixture-tested, so an
oversized payload cannot silently 400 in production. This is the fix for defect 3.

`TEXT` mode remains supported for plain-message use.

## 8. Failure handling

| Failure | Response |
|---|---|
| No webhook configured | One stderr warning, run the command anyway, exit with child's code |
| Webhook 403 / 404 | stderr warning, continue |
| Webhook 429 / 5xx | 2 retries, exponential backoff (1s, 4s), then give up quietly |
| Network hang | 5s connect / 10s read timeout, then give up |
| Malformed JUnit XML | Log, treat as no counts, still send the finish card |
| No report found | Finish card with duration and exit code only |
| Report older than run start | Ignored as stale |
| Payload too large | Truncated in the renderer before send |
| Command not found | Exit 127, finish card reports it |
| Ctrl-C / SIGTERM | Forward to child, wait, send card marked **Interrupted**, exit 130 |
| `chatnotify` itself crashes | Top-level guard: traceback to stderr, exit with the child's code |

The webhook URL is never logged, at any verbosity.

## 9. Testing

| Module | Approach |
|---|---|
| `render.py` | Golden fixtures — exact JSON comparison against files in `tests/fixtures/` |
| `reports.py` | Real XML samples generated once from actual runs of Surefire/TestNG, pytest, jest-junit, mocha-junit-reporter, and Playwright, then committed |
| `config.py` | Cascade tests asserting both precedence and reported provenance |
| `runner.py` | Exit-code passthrough, signal forwarding, live output streaming |
| `transport.py` | Local `http.server` stub asserting the never-raises contract against 200, 404, 429, timeout, and connection-refused |

Committing real report files from each runner is what makes the parser correct
against the actual formats rather than against assumptions about them. One
end-to-end smoke test wraps a genuine `pytest` run and asserts on the payload
received by the stub server.

No third-party mocking library: the HTTP stub is stdlib `http.server`.

CI matrix: Python 3.8 through 3.13, across ubuntu, windows, and macos. Windows is
in the matrix from day one — the team runs Windows, and a tool that is flaky
there will not be adopted. Windows specifics under test: `shell=False` argv
handling, absence of POSIX signal semantics, glob path separators, CRLF output.

## 10. Java v1.1.0 patch

Deliberately minimal — only what protects existing consumers of `v1.0.1`:

1. `catch (Throwable)` in `sendNotification` (defect 1)
2. Explicit connect and socket timeouts (defect 2)
3. Cap the test-file list (defect 3)
4. Bump `pom.xml` to `1.1.0` (defect 13)
5. README: gitignore warning, and a note that the library is superseded by
   `chatnotify` (defect 14)

Not fixed: RestAssured and `org.json` removal (9, 10), the Java 21 floor (11),
ServiceLoader registration (12), retry double-counting (5), static config (6),
`.env` caching (7), config validation (8), tests and CI (15). These matter only
if the library has a future, and it does not.

## 11. Distribution

```bash
pip install "git+https://github.com/DhruvilDesai1/chatnotify@v1.0.0"
```

Tag-based, matching the JitPack workflow already in use. A `zipapp` build
(`python -m zipapp`, stdlib) produces a single `chatnotify.pyz` attached to each
GitHub Release — the escape hatch for a runner without pip.

Semantic versioning. Any change to card layout is at minimum a minor bump, since
golden fixtures and the footer version change with it.

## 12. Out of scope

Named explicitly, because "covers everything" is how a small tool becomes
unmaintainable:

| Not building | Why |
|---|---|
| Slack / Teams / Discord backends | No stated need. The pure-renderer boundary means one is addable later without redesign. |
| History store, dashboards, trend charts | A different product. CI already retains reports. |
| Per-test streaming or real-time progress | Impossible from a command wrapper. |
| Flake detection, retry analytics | Requires cross-run state, therefore storage, therefore a service. |
| Screenshot / artifact upload | Link to the build instead: one `openLink` button, no infrastructure. |
| Split `start` / `finish` subcommands | Until a real multi-job pipeline requires it. |
| Java library modernisation | The library is being retired, not developed. |

## 13. Success criteria

1. A TestNG, pytest, Jest, Mocha, Playwright, Cypress, and plain-script repo each
   produce correct start and finish cards with accurate counts, verified against
   real runs.
2. Wrapping a command never changes its exit code, its output, or whether CI
   passes — verified by test for every failure mode in Section 8.
3. A misconfigured, unreachable, or rate-limited webhook cannot fail a build.
4. Onboarding a new repo takes one `chatnotify init` plus one env var.
5. A stale report is never reported as a current result.
6. The full test suite passes on Python 3.8–3.13 across ubuntu, windows, macos.

# chatnotify

Post a Google Chat notification when any test suite or script starts and finishes.

One tool for TestNG, JUnit, pytest, Jest, Mocha, Playwright, Cypress, and plain
scripts — no per-framework plugins, because counts come from JUnit XML, which all
of them can emit.

[![ci](https://github.com/DhruvilDesai1/GoogleChatUtilityLib/actions/workflows/ci.yml/badge.svg)](https://github.com/DhruvilDesai1/GoogleChatUtilityLib/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

```bash
chatnotify run -- pytest tests/ --junitxml=junit.xml
```

Your Chat space gets a card when the run starts, and a second card in the same
thread when it ends:

```
┌──────────────────────────────────────────┐
│  Payments API                            │
│  Failed                                  │
│                                          │
│  Duration        3m 12s                  │
│  Total Tests     48                      │
│  Exit Code       1                       │
│                                          │
│  Results                                 │
│  ✅ Passed       45                      │
│  ❌ Failed       2                       │
│  ⚠️  Skipped      1                       │
│                                          │
│  Failures                                │
│  tests.test_cart.test_add_discount       │
│  tests.test_cart.test_remove_item        │
│                                          │
│  [ View build ]                          │
│  chatnotify v2.0.1                       │
└──────────────────────────────────────────┘
```

In CI the card also carries the branch, the commit, who triggered the run, and a
**View build** link back to the job.

`chatnotify run` exits with exactly the code your command exited with, and streams
its output through unchanged. An unreachable or misconfigured webhook is logged to
stderr and does not block your command.

## Requirements

- Python 3.9 or newer
- No runtime dependencies at all — everything it uses is in the standard library
- Works on Linux, macOS, and Windows

## Install

```bash
pip install "git+https://github.com/DhruvilDesai1/GoogleChatUtilityLib@v2.0.1"
```

No pip on the runner? See [Single-file install](#single-file-install-no-pip).

> **`v2.0.0` has been withdrawn.** Google Chat rejected every finish card in that
> release because of an invalid field on the card, so its tag and release were removed
> and it can no longer be installed. `v2.0.1` fixes it. If you installed `v2.0.0` before
> it was withdrawn, reinstall at `v2.0.1`.

## Step 1: get a webhook URL

A webhook URL is what lets `chatnotify` post into a space. You create one per space,
in Google Chat:

1. Open the Google Chat space you want notifications in
2. Click the space name at the top, then **Apps & integrations**
3. Click **Manage webhooks** (or **Add webhooks** if the space has none yet)
4. Give it a name — `chatnotify` is a reasonable one — and optionally an avatar URL
5. Click **Save**, then copy the URL

It looks like `https://chat.googleapis.com/v1/spaces/AAAA.../messages?key=...&token=...`.

> **Treat this URL as a credential.** Anyone who has it can post to your space.
> Keep it in your environment or your machine config, never in a committed file.
> You need *Space manager* permission to create one, and webhooks are unavailable
> in direct messages and in some Workspace configurations — ask your admin if the
> menu item is missing.

## Step 2: set up a repository

```bash
cd your-repo
chatnotify init
export CHATNOTIFY_WEBHOOK_URL="https://chat.googleapis.com/v1/spaces/..."
chatnotify doctor
```

`init` writes a committable `.chatnotify.ini` holding your project name, and adds
`.env` to `.gitignore` so a webhook URL cannot be committed by accident.
`doctor` prints where every setting came from and sends a test card, so you know
the whole path works before wiring it into CI.

On Windows PowerShell, set the variable this way instead:

```powershell
$env:CHATNOTIFY_WEBHOOK_URL = "https://chat.googleapis.com/v1/spaces/..."
```

> **Notifications are off on your own machine by default.** This is deliberate — if
> every developer's local test run posted to a shared space, the space would be
> unusable within a day. `doctor` always sends its test card, but
> `chatnotify run` stays silent locally until you opt in:
>
> ```bash
> export CHATNOTIFY_ENABLED=1
> ```
>
> In CI nothing is needed: the `CI` environment variable is set by every major CI
> provider, and `chatnotify` enables itself when it sees it. So if a local
> `chatnotify run` seems to do nothing, that is the expected behaviour, not a bug —
> run `chatnotify doctor` and look at the `enabled` line.

## Step 3: wrap your command

```bash
chatnotify run -- pytest tests/ --junitxml=junit.xml
chatnotify run -- mvn verify
chatnotify run -- python etl.py
```

Everything after `--` is your command, passed through untouched.

## Getting pass/fail counts

Counts are read from a JUnit XML report. Your test runner has to write one, and
`chatnotify` has to be able to find it. These invocations do both — each writes to a
location that is auto-detected, so no `--report` flag is needed:

| Runner | Command |
|---|---|
| **pytest** | `pytest --junitxml=junit.xml` |
| **Maven** (Surefire/Failsafe) | `mvn verify` — writes `target/surefire-reports/` automatically |
| **Gradle** | `gradle test` — writes `build/test-results/` automatically |
| **Jest** | `npm i -D jest-junit` then `jest --reporters=default --reporters=jest-junit` |
| **Mocha** | `npm i -D mocha-junit-reporter` then<br>`mocha --reporter mocha-junit-reporter --reporter-options mochaFile=test-results/mocha.xml` |
| **Playwright** | `PLAYWRIGHT_JUNIT_OUTPUT_NAME=test-results/junit.xml playwright test --reporter=junit` |
| **Cypress** | `cypress run --reporter junit --reporter-options "mochaFile=test-results/[hash].xml"` |

A few of these have sharp edges worth knowing about:

- **Jest and Mocha** need their reporter installed as a separate npm package. Without
  it you get `Cannot find module`, not a report.
- **Playwright's** `--reporter=junit` writes to **stdout** unless you set
  `PLAYWRIGHT_JUNIT_OUTPUT_NAME` (or `outputFile` in your config). Without it there is
  no file to read.
- **Cypress** needs the `[hash]` token in `mochaFile`. Without it every spec
  overwrites the same file and you get only the last spec's results.
- **Mocha's** default output is `./test-results.xml` — a *file* at the repo root, which
  is **not** one of the auto-detected locations. Write it into `test-results/` as shown,
  or pass `--report test-results.xml`.

**With no report at all**, the finish card still shows duration and exit code. That
is the correct behaviour for a plain script, and it is why `chatnotify run -- python
etl.py` is useful on its own.

### Where it looks

Auto-detection checks these, and uses whichever set contains the newest file:

```
target/surefire-reports/*.xml      target/failsafe-reports/*.xml
build/test-results/**/*.xml        test-results/**/*.xml
reports/**/*.xml                   junit.xml
```

Grouping them into sets matters: if one run writes its report to two of these
locations, the counts are taken from one set, not summed twice.

To point at something else, use `--report` with one or more comma-separated globs:

```bash
chatnotify run --report "out/**/*.xml,extra.xml" -- ./run-tests.sh
```

**A report older than the current run is ignored**, whether auto-detected or named
with `--report`, and so is one dated in the future. Reporting yesterday's numbers as
today's is the one failure mode that would make every notification untrustworthy, so
`chatnotify` says nothing rather than guessing. When it skips reports for this reason
it tells you on stderr.

## Configuration

Every setting resolves through these layers, highest priority first:

| | Source | Example |
|---|---|---|
| 1 | Command-line flag | `--project "Payments API"` |
| 2 | Environment variable | `CHATNOTIFY_PROJECT=Payments API` |
| 3 | `.env` in the repo root | `CHATNOTIFY_PROJECT=Payments API` |
| 4 | `.chatnotify.ini` in the repo root | `project = Payments API` |
| 5 | Machine config | `%APPDATA%\chatnotify\config.ini` or `~/.config/chatnotify/config.ini` |
| 6 | Built-in default | `Unknown Project` |

Run `chatnotify doctor` to see which layer won for each setting — that is the fastest
way to answer "why is it using that value?".

### Settings

| Flag | Environment variable | `.chatnotify.ini` key | Meaning |
|---|---|---|---|
| `--project` | `CHATNOTIFY_PROJECT` | `project` | Name in the card header |
| `--env` | `CHATNOTIFY_ENV` | `environment` | Shown only if set |
| `--webhook-url` | `CHATNOTIFY_WEBHOOK_URL` | — | Never put this in a committed file |
| `--message-type` | `CHATNOTIFY_MESSAGE_TYPE` | `message_type` | `CARD` (default) or `TEXT` |
| `--report` | — | — | Report globs, comma-separated |
| `--only-on-failure` | — | — | Send the finish card only when the run failed |
| `--quiet` | — | — | Silence chatnotify's own stderr notes |

`--project`, `--env`, `--webhook-url`, `--message-type` and `--quiet` work on all three
subcommands, so you can check a webhook before committing anything:

```bash
chatnotify doctor --webhook-url "https://chat.googleapis.com/v1/spaces/..."
```

`--report` and `--only-on-failure` apply to `run` only, and `init` uses just
`--project`.

`PROJECT_NAME`, `ENVIRONMENT`, `MESSAGE_TYPE`, and `GOOGLE_CHAT_WEBHOOK_URL` are
accepted as legacy aliases, so `.env` files written for the old Java library keep
working unchanged.

Anything in your command that looks like a credential — a `--token`, an `--api-key`, a
`key=` query parameter, or your webhook URL — is replaced with `***` before the command
is shown on the card.

### Enabling and silencing

| Variable | Effect |
|---|---|
| `CI` (set by your CI provider) | Enables notifications |
| `CHATNOTIFY_ENABLED=1` | Opt in on a local machine |
| `CHATNOTIFY_DISABLED=1` | Silence everywhere — beats both of the above |

Disabling only stops posting. Your command still runs and still returns its own exit
code.

### Multiple spaces

To notify different spaces from different repositories, reference a webhook by
*name*, so the committed file stays identical for everyone and holds no secret:

```ini
# .chatnotify.ini — safe to commit
[chatnotify]
project = Payments API
webhook = qa-team
```

Each machine or CI runner then resolves that name from `CHATNOTIFY_WEBHOOK_QA_TEAM`,
or from a `[webhooks]` section in its machine config:

```ini
# ~/.config/chatnotify/config.ini — never committed
[webhooks]
qa-team = https://chat.googleapis.com/v1/spaces/...
```

Any punctuation in a name becomes an underscore, so `qa.team` and `qa-team` both
resolve from `CHATNOTIFY_WEBHOOK_QA_TEAM`.

## Troubleshooting

**Start with `chatnotify doctor`.** It prints every resolved value with the layer it
came from, then sends a test card. Most problems are visible in its output.

| Symptom | Likely cause |
|---|---|
| Nothing posts locally | Off by default — set `CHATNOTIFY_ENABLED=1`, or check the `enabled` line in `doctor` |
| Nothing posts anywhere | `CHATNOTIFY_DISABLED` is set somewhere, or no webhook is configured |
| Card arrives with no test counts | No report was found, or it was skipped as stale — check chatnotify's stderr notes |
| Counts are missing after adding a reporter | The report is in a location that is not auto-detected; pass `--report` |
| Config in a file is ignored | Check `doctor`'s provenance column — it names the layer each value came from, so you can see which file won |
| A value with a `%` or a quote in it | Handled literally; no escaping needed in `.chatnotify.ini` or `.env` |
| `doctor` says the webhook could not be delivered | Wrong or revoked URL, or the space no longer exists. Recreate the webhook |
| `command not found` / exit 127 | The executable is not on `PATH` in that shell |

## Known limitations

- **Two `chatnotify run` invocations in the same directory at the same time** cannot
  reliably tell whose report is whose. Auto-detection takes a brief advisory lock
  (`.chatnotify.lock`, removed when the run ends and reclaimed if left behind by a
  crash); the second run says so on stderr and reports no counts rather than reporting
  the wrong ones. Pass `--report` with distinct paths to run them concurrently anyway,
  or use separate directories.
- **Only per-suite totals**, never per-test progress. A command wrapper cannot see
  inside your runner; counts come from the report file written when it finishes.
- **Google Chat only.** The rendering layer is isolated, so another backend is a
  contained change, but none exists today.

## Single-file install (no pip)

Every GitHub release attaches `chatnotify.pyz`, a self-contained file built with
`zipapp`. It needs only a Python interpreter:

```bash
python chatnotify.pyz run -- pytest tests/
```

## Development

```bash
git clone https://github.com/DhruvilDesai1/GoogleChatUtilityLib.git
cd GoogleChatUtilityLib
pip install -e ".[dev]"
python -m pytest -v
```

The only development dependency is pytest. Tests run against a local stub HTTP server,
so nothing reaches the network. CI runs the suite on Python 3.9–3.13 across Linux,
Windows, and macOS.

Module layout, if you are changing something:

| File | Responsibility |
|---|---|
| `cli.py` | Argument parsing, subcommands, wiring — the only module that knows about the others |
| `config.py` | The six-layer cascade, and recording where each value came from |
| `runner.py` | Running the wrapped command, timing it, forwarding signals |
| `reports.py` | Finding and parsing JUnit XML |
| `render.py` | Building the Chat payload — a pure function, no I/O |
| `transport.py` | Posting it, with timeout and retry; never raises |
| `models.py` | Shared frozen dataclasses, and the single definition of pass/fail |

## The retired Java library

Versions `1.0.0` through `1.1.0` of this repository were `GoogleChatUtilityLib`, a
TestNG-only Java listener. `chatnotify` supersedes it, but those versions remain
buildable from their tags via JitPack:

JitPack artifacts are not on Maven Central, so you need the repository as well as the
dependency:

```xml
<repositories>
    <repository>
        <id>jitpack.io</id>
        <url>https://jitpack.io</url>
    </repository>
</repositories>

<dependency>
    <groupId>com.github.DhruvilDesai1</groupId>
    <artifactId>GoogleChatUtilityLib</artifactId>
    <version>v1.1.0</version>
</dependency>
```

If you are on `v1.0.1` or earlier, upgrade to `v1.1.0` — in earlier versions an
unreachable webhook throws an `AssertionError` that escapes the listener and aborts
the whole test suite.

> **JitPack serves only the `1.x` tags.** From `v2.0.0` this repository is a Python
> project with no `pom.xml`, so asking JitPack for `v2.0.0` fails with
> *"No build file found"* — that is expected, not a broken release. Pin `v1.1.0`
> explicitly rather than using a floating version, and install the `2.x` line with `pip`.

## License

MIT — see [LICENSE](LICENSE).

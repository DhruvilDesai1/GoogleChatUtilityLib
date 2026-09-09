# chatnotify

Post Google Chat notifications when any test suite or script starts and finishes.
Works with TestNG, JUnit, pytest, Jest, Mocha, Playwright, Cypress, and plain scripts —
one tool, no per-framework plugins.

## Install

    pip install "git+https://github.com/DhruvilDesai1/GoogleChatUtilityLib@v2.0.0"

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

1. CLI flag — `--project`, `--env`, `--message-type`, `--report`, `--webhook-url`
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

## The retired Java library

Versions `1.0.0` through `1.1.0` of this repository were `GoogleChatUtilityLib`, a
TestNG-only Java listener. It is superseded by `chatnotify` but remains buildable from
its tags via JitPack:

```xml
<dependency>
    <groupId>com.github.DhruvilDesai1</groupId>
    <artifactId>GoogleChatUtilityLib</artifactId>
    <version>v1.1.0</version>
</dependency>
```

If you are on `v1.0.1` or earlier, upgrade to `v1.1.0` — earlier versions can abort your
test suite when the webhook is unreachable.

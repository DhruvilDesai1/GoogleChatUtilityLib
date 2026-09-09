# Release Details

## Tag version
`v2.0.0`

## Release Title
`v2.0.0 - chatnotify: a complete rewrite in Python`

## Description
**chatnotify** is a complete rewrite of this project: from a TestNG-only Java library to a
stdlib-only Python CLI that wraps any command, in any language, and posts Google Chat
notifications around it.

### Breaking
The Java library is **removed from `main`**. It remains buildable via JitPack at tags
`v1.0.0`, `v1.0.1`, and `v1.1.0`. Java users should stay on `v1.1.0` — that tag is
unaffected by this release and continues to work exactly as it does today.

### Installation
```bash
pip install "git+https://github.com/DhruvilDesai1/GoogleChatUtilityLib@v2.0.0"
```
Requires Python **3.9+**. Zero runtime dependencies.

### What it covers
TestNG/Surefire, JUnit, pytest, Jest, Mocha, Playwright, Cypress, and plain scripts — all
through one JUnit-XML parser, with no framework-specific code.

### Commands
- `chatnotify run -- <any command>` - run a command and notify around it
- `chatnotify init` - create `.chatnotify.ini` in the current repository
- `chatnotify doctor` - show resolved config and send a test card

### Key guarantees
- `chatnotify run` always exits with exactly the wrapped command's exit code.
- A webhook problem (unreachable, misconfigured, timing out) never blocks or fails your
  command.

### Enablement
Notifications default to **on in CI, off locally**, so local runs never flood a shared
space.

---

# Previous release (Java)

The sections below document `v1.1.0`, the final release of the Java `GoogleChatUtilityLib`
TestNG listener, which predates the `chatnotify` rewrite above.

## Tag version
`v1.1.0`

## Release Title
`v1.1.0 - Reliability Patch (final release)`

## Description
**Google Chat Utility Lib** - final release of the Java TestNG library. From `v2.0.0` this
project ships `chatnotify`, a command-line tool covering TestNG, JUnit, pytest, Jest,
Mocha, Playwright, Cypress, and plain scripts with one tool.

Upgrade to `v1.1.0` if you are on `v1.0.1` or earlier.

### Fixes
- **A failed webhook can no longer abort your test suite.** `.then().statusCode(200)`
  throws `AssertionError`, which extends `Error` and so was never caught by the previous
  `catch (Exception)`. A 403, 404, or 429 from Google Chat propagated out of the suite
  listener and aborted the run.
- **Explicit HTTP timeouts** (5s connect, 10s socket). Previously a hanging Chat endpoint
  hung the suite indefinitely.
- **Test-class lists are capped at 20** with an "...and N more" note, so a large suite no
  longer builds a payload that Google Chat rejects.
- **POM version corrected** to match the release tag.
- **README** now warns that `.env` must be gitignored before a webhook URL is stored in it.

### Not changed
Public API is identical. Upgrading is a one-line version change, and cards render exactly
as before for a working webhook.

### Installation
```xml
<dependency>
    <groupId>com.github.DhruvilDesai1</groupId>
    <artifactId>GoogleChatUtilityLib</artifactId>
    <version>v1.1.0</version>
</dependency>
```

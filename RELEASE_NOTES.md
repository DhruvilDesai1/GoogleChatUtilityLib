# Release Details

## Tag version
`v1.1.0`

## Release Title
`v1.1.0 - Reliability Patch (final release)`

## Description
**Google Chat Utility Lib** - final release of the Java TestNG library. From `v2.0.0` this
project ships `chatnotify`, a command-line tool covering TestNG, pytest, Jest, Mocha,
Playwright, Cypress, and plain scripts with one tool.

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

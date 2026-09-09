# GoogleChatUtilityLib v1.1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a minimal patch release that stops the library from being able to fail a consumer's build, then mark it superseded.

**Architecture:** No restructuring. Three defensive fixes inside the two existing classes, plus version and documentation changes. The library is being retired in favour of `chatnotify`, so this is triage for existing consumers of `v1.0.1`, not development.

**Tech Stack:** Java 21, Maven, TestNG 7.11 (`provided`), RestAssured 5.5.6, org.json.

**Spec:** `docs/superpowers/specs/2026-09-07-chatnotify-design.md` section 10.

**Project root:** the repository root.

## Global Constraints

- **Fix only defects 1, 2, 3, 13, and 14 from the spec.** Defects 5, 6, 7, 8, 9, 10, 11, 12, and 15 are explicitly out of scope. Do not remove RestAssured, do not remove `org.json`, do not lower the Java 21 floor, do not add `ServiceLoader` registration, do not restructure the config cascade. Those only matter if the library has a future, and it does not.
- **No behaviour change for a working webhook.** A consumer on a correctly configured `v1.0.1` must see identical cards after upgrading.
- **No new runtime dependencies.** Timeouts are configured through RestAssured's existing `HttpClientConfig`.
- **Existing public API stays intact.** `BaseTest`, `GoogleChatConfig`, and the `GoogleChatNotifier` static methods keep their signatures; consumers must upgrade by changing one version number.

### One deliberate deviation from the spec

Spec section 10 lists "tests and CI (15)" as not fixed. This plan adds **one** test class,
`src/test/java/com/teamninja/utilities/GoogleChatNotifierTest.java`, solely to verify the
critical fix in Task 1. Shipping a patch whose entire purpose is "this can no longer throw"
without a test proving it cannot throw would be indefensible. This is verification of the
patch, not the general test coverage that defect 15 describes — no test is added for any
other class, and no CI workflow is created.

## File Structure

| File | Change |
|---|---|
| `src/main/java/com/teamninja/utilities/GoogleChatNotifier.java` | `catch (Throwable)`, HTTP timeouts (defects 1, 2) |
| `src/main/java/com/teamninja/utilities/SuiteListener.java` | Cap the test-class list (defect 3) |
| `src/test/java/com/teamninja/utilities/GoogleChatNotifierTest.java` | **New** — proves the fix |
| `pom.xml` | Version `1.0.0` → `1.1.0` (defect 13) |
| `README.md` | Superseded notice, gitignore warning (defect 14) |
| `RELEASE_NOTES.md` | `v1.1.0` entry |

---

## Task 1: Stop a failed webhook from aborting the suite

**Files:**
- Modify: `src/main/java/com/teamninja/utilities/GoogleChatNotifier.java:57-76`
- Test: `src/test/java/com/teamninja/utilities/GoogleChatNotifierTest.java`

**Interfaces:**
- Consumes: nothing new.
- Produces: no API change. `GoogleChatNotifier.sendNotification(String)` keeps its signature and becomes total — it returns normally for every input.

This is the defect that matters. `.then().statusCode(200)` throws `java.lang.AssertionError`,
which extends `Error`, not `Exception` — so the existing `catch (Exception e)` never fires and
a 404, 403, or 429 from Chat propagates out through `onStart` and aborts the consumer's run.

- [ ] **Step 1: Write the failing test**

Create `src/test/java/com/teamninja/utilities/GoogleChatNotifierTest.java`. Port `9` on
localhost is the reliable "connection refused" target; `example.invalid` is reserved by
RFC 6761 and never resolves, which exercises the DNS-failure path.

```java
package com.teamninja.utilities;

import org.testng.annotations.AfterMethod;
import org.testng.annotations.Test;

public class GoogleChatNotifierTest {

    @AfterMethod
    public void resetConfig() {
        GoogleChatConfig.setWebhookUrl(null);
        GoogleChatConfig.setMessageType(null);
    }

    @Test
    public void unreachableWebhookDoesNotThrow() {
        GoogleChatConfig.setWebhookUrl("http://127.0.0.1:9/webhook");
        GoogleChatNotifier.sendNotification("{\"text\":\"hi\"}");
    }

    @Test
    public void unresolvableHostDoesNotThrow() {
        GoogleChatConfig.setWebhookUrl("https://example.invalid/webhook");
        GoogleChatNotifier.sendNotification("{\"text\":\"hi\"}");
    }

    @Test
    public void missingWebhookDoesNotThrow() {
        GoogleChatConfig.setWebhookUrl(null);
        GoogleChatNotifier.sendNotification("{\"text\":\"hi\"}");
    }

    @Test
    public void startNotificationSurvivesUnreachableWebhook() {
        GoogleChatConfig.setWebhookUrl("http://127.0.0.1:9/webhook");
        GoogleChatNotifier.sendStartNotification("Proj", "Suite", "- A\n- B\n", "staging");
    }

    @Test
    public void finishNotificationSurvivesUnreachableWebhook() {
        GoogleChatConfig.setWebhookUrl("http://127.0.0.1:9/webhook");
        GoogleChatNotifier.sendFinishNotification("Proj", "Suite", 3, 1, 0, "staging");
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
mvn -q test -Dtest=GoogleChatNotifierTest
```

Expected: failures on the four tests that set a webhook URL, reported as
`java.lang.AssertionError` escaping `sendNotification` (or a socket exception on the
connection-refused path). `missingWebhookDoesNotThrow` passes already — the null-URL guard
on line 59 works today.

- [ ] **Step 3: Change the catch clause**

In `GoogleChatNotifier.java`, replace the `catch (Exception e)` block inside
`sendNotification` (line 73) with:

```java
                } catch (Throwable t) {
                        System.err.println("Failed to send Google Chat notification: " + t);
                }
```

`Throwable` rather than `Exception` is the whole fix: it is the only clause that catches
`AssertionError`. Logging `t` rather than `t.getMessage()` keeps the type name visible,
since `AssertionError.getMessage()` alone reads confusingly in a build log.

- [ ] **Step 4: Run the test to verify it passes**

```bash
mvn -q test -Dtest=GoogleChatNotifierTest
```

Expected: 5 tests pass. Each prints a "Failed to send Google Chat notification" line to
stderr — that is the intended behaviour, not a failure.

- [ ] **Step 5: Commit**

```bash
git add src/main/java/com/teamninja/utilities/GoogleChatNotifier.java src/test/java/com/teamninja/utilities/GoogleChatNotifierTest.java
git commit -m "fix: catch Throwable so a failed webhook cannot abort the suite"
```

---

## Task 2: Add HTTP timeouts

**Files:**
- Modify: `src/main/java/com/teamninja/utilities/GoogleChatNotifier.java:1-11,57-76`
- Test: `src/test/java/com/teamninja/utilities/GoogleChatNotifierTest.java` (add one test)

**Interfaces:**
- Consumes: `io.restassured.config.RestAssuredConfig`, `io.restassured.config.HttpClientConfig`.
- Produces: private constants `CONNECT_TIMEOUT_MS = 5000` and `SOCKET_TIMEOUT_MS = 10000`, and private static method `RestAssuredConfig timeoutConfig()`.

RestAssured is used with default configuration today, which sets neither connect nor socket
timeout. A Chat endpoint that accepts a connection and then never responds hangs `onStart`
forever, and the suite hangs with it.

- [ ] **Step 1: Write the failing test**

Append to `GoogleChatNotifierTest.java`:

```java
    @Test(timeOut = 30000)
    public void unroutableHostFailsWithinTimeout() {
        // 10.255.255.1 is a non-routable RFC 1918 address: packets are dropped
        // rather than refused, so this hangs until a connect timeout applies.
        GoogleChatConfig.setWebhookUrl("http://10.255.255.1/webhook");
        GoogleChatNotifier.sendNotification("{\"text\":\"hi\"}");
    }
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
mvn -q test -Dtest=GoogleChatNotifierTest#unroutableHostFailsWithinTimeout
```

Expected: TestNG reports the method timed out after 30000 ms. On some networks the OS
imposes its own connect timeout below 30s and this passes without the fix — if so, note it
and proceed; Steps 3 and 4 still make the timeout explicit rather than platform-dependent.

- [ ] **Step 3: Add the timeout configuration**

Add these imports to the existing block at the top of `GoogleChatNotifier.java`:

```java
import io.restassured.config.HttpClientConfig;
import io.restassured.config.RestAssuredConfig;
```

Add these members immediately after the `public class GoogleChatNotifier {` line:

```java
        private static final int CONNECT_TIMEOUT_MS = 5000;
        private static final int SOCKET_TIMEOUT_MS = 10000;

        private static RestAssuredConfig timeoutConfig() {
                return RestAssuredConfig.config().httpClient(
                                HttpClientConfig.httpClientConfig()
                                                .setParam("http.connection.timeout", CONNECT_TIMEOUT_MS)
                                                .setParam("http.socket.timeout", SOCKET_TIMEOUT_MS));
        }
```

Then in `sendNotification`, insert `.config(timeoutConfig())` into the request chain so it
reads:

```java
                        RestAssured.given()
                                        .config(timeoutConfig())
                                        .contentType(ContentType.JSON)
                                        .body(jsonPayload)
                                        .post(webhookUrl)
                                        .then()
                                        .statusCode(200);
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
mvn -q test -Dtest=GoogleChatNotifierTest
```

Expected: 6 tests pass, and `unroutableHostFailsWithinTimeout` completes in roughly 5
seconds rather than hanging.

- [ ] **Step 5: Commit**

```bash
git add src/main/java/com/teamninja/utilities/GoogleChatNotifier.java src/test/java/com/teamninja/utilities/GoogleChatNotifierTest.java
git commit -m "fix: set explicit connect and socket timeouts"
```

---

## Task 3: Cap the test-class list

**Files:**
- Modify: `src/main/java/com/teamninja/utilities/SuiteListener.java:58-82`
- Test: `src/test/java/com/teamninja/utilities/SuiteListenerTest.java`

**Interfaces:**
- Consumes: nothing new.
- Produces: package-private static method `String formatTestFiles(java.util.List<String> classNames)` on `SuiteListener`, and private constant `MAX_LISTED_CLASSES = 20`. Extracting the formatting into a method is what makes the cap testable without constructing a TestNG `ISuite`.

A suite with hundreds of classes builds a payload that exceeds Google Chat's limit, gets a
400 back, and — before Task 1 — aborted the run. Task 1 stops the abort; this stops the
notification from being lost in the first place.

- [ ] **Step 1: Write the failing test**

Create `src/test/java/com/teamninja/utilities/SuiteListenerTest.java`.

```java
package com.teamninja.utilities;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.testng.Assert;
import org.testng.annotations.Test;

public class SuiteListenerTest {

    @Test
    public void shortListIsUnchanged() {
        String formatted = SuiteListener.formatTestFiles(Arrays.asList("a.B", "c.D"));
        Assert.assertEquals(formatted, "- a.B\n- c.D\n");
    }

    @Test
    public void emptyListProducesEmptyString() {
        Assert.assertEquals(SuiteListener.formatTestFiles(new ArrayList<>()), "");
    }

    @Test
    public void longListIsCappedWithRemainderNote() {
        List<String> names = new ArrayList<>();
        for (int i = 0; i < 50; i++) {
            names.add("pkg.Test" + i);
        }
        String formatted = SuiteListener.formatTestFiles(names);
        Assert.assertEquals(countOccurrences(formatted, "- pkg.Test"), 20);
        Assert.assertTrue(formatted.contains("...and 30 more"),
                "expected a remainder note, got: " + formatted);
    }

    @Test
    public void listAtExactlyTheCapHasNoRemainderNote() {
        List<String> names = new ArrayList<>();
        for (int i = 0; i < 20; i++) {
            names.add("pkg.Test" + i);
        }
        Assert.assertFalse(SuiteListener.formatTestFiles(names).contains("more"));
    }

    private static int countOccurrences(String haystack, String needle) {
        int count = 0;
        int index = haystack.indexOf(needle);
        while (index >= 0) {
            count++;
            index = haystack.indexOf(needle, index + needle.length());
        }
        return count;
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
mvn -q test -Dtest=SuiteListenerTest
```

Expected: compilation failure — `cannot find symbol: method formatTestFiles`.

- [ ] **Step 3: Add the formatter and use it**

Add these imports to `SuiteListener.java`:

```java
import java.util.ArrayList;
import java.util.List;
```

Add this constant and method to the class:

```java
    private static final int MAX_LISTED_CLASSES = 20;

    static String formatTestFiles(List<String> classNames) {
        StringBuilder builder = new StringBuilder();
        int listed = Math.min(classNames.size(), MAX_LISTED_CLASSES);
        for (int i = 0; i < listed; i++) {
            builder.append("- ").append(classNames.get(i)).append("\n");
        }
        int remaining = classNames.size() - listed;
        if (remaining > 0) {
            builder.append("...and ").append(remaining).append(" more\n");
        }
        return builder.toString();
    }
```

Replace the body of `onStart` (lines 59-81) with a version that collects names into a list
and formats once:

```java
    @Override
    public void onStart(ISuite suite) {
        List<String> classNames = new ArrayList<>();

        suite.getXmlSuite().getTests().forEach(test -> {
            test.getXmlClasses().forEach(cls -> classNames.add(cls.getName()));
        });

        // If no classes found in XML (e.g. running from IDE context), try to get from
        // methods
        if (classNames.isEmpty()) {
            suite.getAllMethods().stream()
                    .map(m -> m.getTestClass().getName())
                    .distinct()
                    .forEach(classNames::add);
        }

        String projectName = getProjectName();
        String environment = getEnvironment();

        GoogleChatNotifier.sendStartNotification(projectName, suite.getName(),
                formatTestFiles(classNames), environment);
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
mvn -q test
```

Expected: 10 tests pass across both test classes.

- [ ] **Step 5: Commit**

```bash
git add src/main/java/com/teamninja/utilities/SuiteListener.java src/test/java/com/teamninja/utilities/SuiteListenerTest.java
git commit -m "fix: cap the test-class list to keep payloads within Chat limits"
```

---

## Task 4: Version bump, superseded notice, and release

**Files:**
- Modify: `pom.xml:9`
- Modify: `README.md`
- Modify: `RELEASE_NOTES.md`

**Interfaces:**
- Consumes: nothing.
- Produces: no code. Version `1.1.0` and the documentation that tells consumers where the project went.

- [ ] **Step 1: Bump the version in `pom.xml`**

Change line 9 from `<version>1.0.0</version>` to:

```xml
    <version>1.1.0</version>
```

This closes defect 13 — the POM has said `1.0.0` since the `v1.0.1` tag was cut. JitPack
resolves by tag so consumers were unaffected, but the mismatch is misleading.

- [ ] **Step 2: Verify the build still installs**

```bash
mvn -q clean install -DskipTests && ls target/google-chat-notifier-1.1.0.jar
```

Expected: the JAR exists at the new version.

- [ ] **Step 3: Add the superseded notice and gitignore warning to `README.md`**

Insert immediately after the JitPack badge line:

```markdown
> **This library is superseded.** It only supports TestNG. For Java, Python, JavaScript,
> and plain scripts from one tool, use
> [chatnotify](https://github.com/DhruvilDesai1/chatnotify) instead. `v1.1.0` is a
> maintenance release for existing consumers — upgrade to it if you are on `v1.0.1`,
> because earlier versions can abort your test suite when the webhook is unreachable.
```

Then in the `### C. Environment Variables / .env` section, immediately after the `.env`
code block, add:

```markdown
> **Add `.env` to your `.gitignore` before saving a webhook URL in it.** A Google Chat
> webhook URL is a credential: anyone holding it can post to your space. Committing one
> to a repository leaks it.
```

- [ ] **Step 4: Update the version in the README install snippet**

In the Maven dependency block, change `<version>v1.0.1</version>` to:

```xml
    <version>v1.1.0</version>
```

- [ ] **Step 5: Replace the contents of `RELEASE_NOTES.md`**

```markdown
# Release Details

## Tag version
`v1.1.0`

## Release Title
`v1.1.0 - Reliability Patch (final release)`

## Description
**Google Chat Utility Lib** - final maintenance release. This library is superseded by
[chatnotify](https://github.com/DhruvilDesai1/chatnotify), which covers TestNG, pytest,
Jest, Mocha, Playwright, Cypress, and plain scripts with one tool.

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
```

- [ ] **Step 6: Run the full build one final time**

```bash
mvn -q clean test
```

Expected: 10 tests pass, build succeeds.

- [ ] **Step 7: Commit and tag**

```bash
git add pom.xml README.md RELEASE_NOTES.md
git commit -m "chore: release v1.1.0 and mark library superseded"
git tag v1.1.0
```

- [ ] **Step 8: Confirm JitPack can build the tag**

Push the tag, then check that JitPack resolves it:

```bash
git push origin main --tags
```

Then open `https://jitpack.io/#DhruvilDesai1/GoogleChatUtilityLib/v1.1.0` and confirm the
build succeeds. `jitpack.yml` already pins `openjdk21` and Maven 3.9.9, so no change is
needed there.

---

## Self-Review Notes

Spec section 10 lists five items; each maps to a task:

| Spec item | Task |
|---|---|
| 1. `catch (Throwable)` in `sendNotification` (defect 1) | Task 1 |
| 2. Explicit connect and socket timeouts (defect 2) | Task 2 |
| 3. Cap the test-file list (defect 3) | Task 3 |
| 4. Bump `pom.xml` to `1.1.0` (defect 13) | Task 4 |
| 5. README gitignore warning and superseded note (defect 14) | Task 4 |

Out-of-scope defects confirmed untouched by this plan: 5 (retry double-counting), 6 (static
config), 7 (`.env` caching), 8 (config validation), 9 (RestAssured), 10 (`org.json`), 11
(Java 21 floor), 12 (`ServiceLoader`), 15 (general tests and CI — two test classes are
added to verify Tasks 1-3 only, and no CI workflow is created).

Type consistency verified: `SuiteListener.formatTestFiles(List<String>)` is the only new
signature, called from `onStart` and from `SuiteListenerTest`; `GoogleChatNotifier`'s three
public methods keep their existing signatures, so no consumer code changes.

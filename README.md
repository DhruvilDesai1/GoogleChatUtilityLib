# Google Chat Utility Library

A reusable utility for sending Google Chat notifications from TestNG suites.

[![](https://jitpack.io/v/DhruvilDesai1/GoogleChatUtilityLib.svg)](https://jitpack.io/#DhruvilDesai1/GoogleChatUtilityLib)

> **This library is superseded.** It only supports TestNG. From `v2.0.0` onward this
> project ships `chatnotify`, a single command-line tool covering TestNG, JUnit, pytest,
> Jest, Mocha, Playwright, Cypress, and plain scripts. `v1.1.0` is the final release of
> the Java library — upgrade to it if you are on `v1.0.1` or earlier, because those
> versions can abort your test suite when the webhook is unreachable.

## 1. Installation

### Maven
Add the JitPack repository and the dependency to your `pom.xml`:

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



## 2. Usage

### Extend BaseTest
In your test classes, extend `com.teamninja.utilities.BaseTest`:
```java
import com.teamninja.utilities.BaseTest;
import org.testng.annotations.Test;

public class MyTest extends BaseTest {
    @Test
    public void testSomething() { ... }
}
```

## 3. Configuration
You can configure the library in 3 ways (in order of priority):

### A. Programmatic (Highest Priority)
**Important:** To ensure configuration is loaded *before* the "Suite Started" notification, use a `static` block in your Test class:
```java
import com.teamninja.utilities.GoogleChatConfig;
import com.teamninja.utilities.BaseTest;
import org.testng.annotations.Test;

public class MyTest extends BaseTest {
    static {
        GoogleChatConfig.setProjectName("My Awesome App");
        GoogleChatConfig.setEnvironment("Beta");
        GoogleChatConfig.setWebhookUrl("https://chat.googleapis.com/...");
        GoogleChatConfig.setMessageType("TEXT"); 
    }
    
    @Test
    public void testSomething() { ... }
}
```

### B. System Properties (CI/CD)
```bash
mvn test -DprojectName="My App" -DmessageType="TEXT"
```

### C. Environment Variables / .env (Local/IDE)
Create a `.env` file in your project root:
```properties
PROJECT_NAME=My App
GOOGLE_CHAT_WEBHOOK_URL=https://chat.googleapis.com/...
ENVIRONMENT=Beta
MESSAGE_TYPE=TEXT
```

> **Add `.env` to your `.gitignore` before saving a webhook URL in it.** A Google Chat
> webhook URL is a credential: anyone holding it can post to your space. Committing one
> to a repository leaks it.

## 4. Features
- **Easy Integration**: Send notifications to Google Chat from TestNG suites.
- **Flexible Config**: Works seamlessly in IDEs (via `.env`) and CI/CD (via System Props).
- **Optional Environment**: If you don't specify an environment, it won't show up in the chat card.

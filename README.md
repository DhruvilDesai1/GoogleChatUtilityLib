# Google Chat Utility Library

A reusable utility for sending Google Chat notifications from TestNG suites.

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
    <version>v1.0.1</version>
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

## 4. Features
- **Easy Integration**: Send notifications to Google Chat from TestNG suites.
- **Flexible Config**: Works seamlessly in IDEs (via `.env`) and CI/CD (via System Props).
- **Optional Environment**: If you don't specify an environment, it won't show up in the chat card.

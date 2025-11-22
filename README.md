# Google Chat Notifier Utility

A reusable Java library for sending Google Chat notifications from TestNG test suites. This utility allows you to easily integrate Google Chat alerts into your automation framework, providing real-time updates on test execution start and finish.

## Features

- **Automatic Notifications**: Sends notifications when a test suite starts and finishes.
- **Rich Cards**: Supports Google Chat cards with decorated text and icons.
- **Flexible Configuration**: Configure via code, system properties, or `.env` files.
- **Environment Aware**: Optionally display the environment (e.g., Live, Beta) in notifications.
- **Easy Integration**: Just extend `BaseTest` or add the `SuiteListener`.

## Installation

### Maven

To use this library in your Maven project, install it locally or deploy it to your repository. Then add the dependency:

```xml
<dependency>
    <groupId>com.teamninja.utilities</groupId>
    <artifactId>google-chat-notifier</artifactId>
    <version>1.0.0</version>
</dependency>
```

## Configuration

You can configure the utility using one of the following methods (in order of precedence):

1.  **Programmatic**: Call `GoogleChatConfig` setters before the suite starts.
2.  **System Properties**: Pass `-D` arguments to the JVM.
3.  **Environment Variables**: Use a `.env` file or system environment variables.

### Configuration Keys

| Key | Description | Example |
| :--- | :--- | :--- |
| `googleChatWebhookUrl` / `GOOGLE_CHAT_WEBHOOK_URL` | **Required**. The webhook URL for your Google Chat space. | `https://chat.googleapis.com/...` |
| `projectName` / `PROJECT_NAME` | Name of your project to display in cards. | `My Automation Project` |
| `environment` / `ENVIRONMENT` | (Optional) Environment name. | `Live`, `Beta` |
| `messageType` / `MESSAGE_TYPE` | (Optional) `CARD` (default) or `TEXT`. | `CARD` |

## Usage

### Option 1: Extend BaseTest

The easiest way to use the notifier is to extend the `BaseTest` class in your test classes.

```java
import com.teamninja.utilities.BaseTest;
import org.testng.annotations.Test;

public class MyTest extends BaseTest {
    @Test
    public void testSomething() {
        // Your test code
    }
}
```

### Option 2: Add Listener in testng.xml

If you prefer not to extend a base class, you can add the listener directly to your `testng.xml` file.

```xml
<suite name="My Suite">
    <listeners>
        <listener class-name="com.teamninja.utilities.SuiteListener"/>
    </listeners>
    
    <test name="My Test">
        <classes>
            <class name="com.example.MyTest"/>
        </classes>
    </test>
</suite>
```

## Building from Source

To build the project locally:

```bash
mvn clean install
```



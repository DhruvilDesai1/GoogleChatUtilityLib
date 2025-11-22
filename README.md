# Google Chat Utility Library

A reusable utility for sending Google Chat notifications from TestNG suites.

## 1. How to Build
To rebuild the library, run:
```bash
mvn clean install
```
The JAR will be generated in `target/google-chat-notifier-1.0.0.jar`.

## 2. How to Use in Your Projects

### Step 1: Add Dependency
**Option A: Maven (Recommended)**
First, run `mvn clean install` in this folder.
Then add this to your project's `pom.xml`:
```xml
<dependency>
    <groupId>com.teamninja.utilities</groupId>
    <artifactId>google-chat-notifier</artifactId>
    <version>1.0.0</version>
</dependency>
```

**Option B: Manual JAR (For Private/Local Use)**
If you cannot use the Maven install method, you can manually add the JAR to your project.

1.  **Create a `lib` folder** in your project's root directory (same level as `pom.xml`).
2.  **Copy the JAR**: Copy `target/google-chat-notifier-1.0.0.jar` from this project into your new `lib` folder.
3.  **Commit the JAR**: Ensure your `.gitignore` does NOT exclude the `lib` folder. You **MUST commit this JAR** to your Git repository so that Jenkins/CI can find it.
4.  **Update `pom.xml`**: Add the dependency with `system` scope:

```xml
<dependency>
    <groupId>com.teamninja.utilities</groupId>
    <artifactId>google-chat-notifier</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>${project.basedir}/lib/google-chat-notifier-1.0.0.jar</systemPath>
</dependency>
```

### Step 2: Extend BaseTest
In your test classes, extend `com.teamninja.utilities.BaseTest`:
```java
import com.teamninja.utilities.BaseTest;
import org.testng.annotations.Test;

public class MyTest extends BaseTest {
    @Test
    public void testSomething() { ... }
}
```

### Step 3: Configure
You can configure the library in 3 ways (in order of priority):

#### A. Programmatic (Highest Priority)
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

#### B. System Properties (CI/CD)
```bash
mvn test -DprojectName="My App" -DmessageType="TEXT"
```

#### C. Environment Variables / .env (Local/IDE)
Create a `.env` file in your project root:
```properties
PROJECT_NAME=My App
GOOGLE_CHAT_WEBHOOK_URL=https://chat.googleapis.com/...
ENVIRONMENT=Beta
MESSAGE_TYPE=TEXT
```

## 3. Features
- **Flexible Config**: Works seamlessly in IDEs (via `.env`) and CI/CD (via System Props).
- **Optional Environment**: If you don't specify an environment, it won't show up in the chat card.

## 4. CI/CD Integration (Jenkins/Git)
Since this is a local library, Jenkins needs to build it before running your main tests.

**Recommended Strategy: "Build First"**
Add a stage in your Jenkins pipeline to download and install this library *before* your test stage.

**Example Jenkins Pipeline:**
```groovy
pipeline {
    agent any
    stages {
        stage('Install Utility Lib') {
            steps {
                // 1. Download the library code
                // Replace with your actual repo URL
                git 'https://github.com/DhruvilDesai1/GoogleChatUtilityLib.git'
                
                // 2. Install it to Jenkins local Maven repo
                sh 'mvn clean install' 
            }
        }
        stage('Run Main Tests') {
            steps {
                // 3. Now download your actual project
                git 'https://github.com/your-user/my-test-project.git'
                
                // 4. Run tests (Maven will find the lib installed in step 2)
                sh 'mvn test'
            }
        }
    }
}
```

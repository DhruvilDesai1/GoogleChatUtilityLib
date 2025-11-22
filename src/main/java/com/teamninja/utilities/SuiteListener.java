package com.teamninja.utilities;

import io.github.cdimascio.dotenv.Dotenv;
import org.testng.ISuite;
import org.testng.ISuiteListener;
import java.util.Map;

public class SuiteListener implements ISuiteListener {

    private String getProjectName() {
        // 1. Programmatic
        if (GoogleChatConfig.getProjectName() != null && !GoogleChatConfig.getProjectName().isEmpty()) {
            return GoogleChatConfig.getProjectName();
        }
        // 2. System Property
        String sysProp = System.getProperty("projectName");
        if (sysProp != null && !sysProp.isEmpty()) {
            return sysProp;
        }
        // 3. Environment Variable / .env
        try {
            Dotenv dotenv = Dotenv.configure().ignoreIfMissing().load();
            String envVar = dotenv.get("PROJECT_NAME");
            if (envVar != null && !envVar.isEmpty()) {
                return envVar;
            }
        } catch (Exception e) {
            // Ignore
        }
        // 4. Default
        return "Unknown Project";
    }

    private String getEnvironment() {
        // 1. Programmatic
        if (GoogleChatConfig.getEnvironment() != null && !GoogleChatConfig.getEnvironment().isEmpty()) {
            return GoogleChatConfig.getEnvironment();
        }
        // 2. System Property
        String sysProp = System.getProperty("environment");
        if (sysProp != null && !sysProp.isEmpty()) {
            return sysProp;
        }
        // 3. Environment Variable / .env
        try {
            Dotenv dotenv = Dotenv.configure().ignoreIfMissing().load();
            String envVar = dotenv.get("ENVIRONMENT");
            if (envVar != null && !envVar.isEmpty()) {
                return envVar;
            }
        } catch (Exception e) {
            // Ignore
        }
        // 4. Default (Null to indicate omission)
        return null;
    }

    @Override
    public void onStart(ISuite suite) {
        StringBuilder testFiles = new StringBuilder();

        // Logic to scan for test files
        suite.getXmlSuite().getTests().forEach(test -> {
            test.getXmlClasses().forEach(cls -> {
                testFiles.append("- ").append(cls.getName()).append("\n");
            });
        });

        // If no classes found in XML (e.g. running from IDE context), try to get from
        // methods
        if (testFiles.length() == 0) {
            suite.getAllMethods().stream()
                    .map(m -> m.getTestClass().getName())
                    .distinct()
                    .forEach(name -> testFiles.append("- ").append(name).append("\n"));
        }

        String projectName = getProjectName();
        String environment = getEnvironment();

        GoogleChatNotifier.sendStartNotification(projectName, suite.getName(), testFiles.toString(), environment);
    }

    @Override
    public void onFinish(ISuite suite) {
        Map<String, org.testng.ISuiteResult> results = suite.getResults();
        int passed = 0;
        int failed = 0;
        int skipped = 0;

        for (org.testng.ISuiteResult result : results.values()) {
            org.testng.ITestContext context = result.getTestContext();
            passed += context.getPassedTests().size();
            failed += context.getFailedTests().size();
            skipped += context.getSkippedTests().size();
        }

        String projectName = getProjectName();
        String environment = getEnvironment();

        GoogleChatNotifier.sendFinishNotification(projectName, suite.getName(), passed, failed, skipped, environment);
    }
}

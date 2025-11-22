package com.teamninja.utilities;

import org.testng.annotations.Listeners;

@Listeners(com.teamninja.utilities.SuiteListener.class)
public class BaseTest {
    // Extend this class in your test classes to enable Google Chat notifications
    // when running individual test files.
}

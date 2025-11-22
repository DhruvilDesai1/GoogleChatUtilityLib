package com.teamninja.utilities;

public class GoogleChatConfig {
    private static String projectName;
    private static String environment;
    private static String webhookUrl;

    public static String getProjectName() {
        return projectName;
    }

    public static void setProjectName(String projectName) {
        GoogleChatConfig.projectName = projectName;
    }

    public static String getEnvironment() {
        return environment;
    }

    public static void setEnvironment(String environment) {
        GoogleChatConfig.environment = environment;
    }

    public static String getWebhookUrl() {
        return webhookUrl;
    }

    public static void setWebhookUrl(String webhookUrl) {
        GoogleChatConfig.webhookUrl = webhookUrl;
    }

    private static String messageType;

    public static String getMessageType() {
        return messageType;
    }

    public static void setMessageType(String messageType) {
        GoogleChatConfig.messageType = messageType;
    }
}

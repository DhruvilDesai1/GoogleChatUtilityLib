package com.teamninja.utilities;

import io.github.cdimascio.dotenv.Dotenv;
import io.restassured.RestAssured;
import io.restassured.http.ContentType;
import org.json.JSONArray;
import org.json.JSONObject;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public class GoogleChatNotifier {

        private static String getWebhookUrl() {
                // 1. Programmatic
                if (GoogleChatConfig.getWebhookUrl() != null && !GoogleChatConfig.getWebhookUrl().isEmpty()) {
                        return GoogleChatConfig.getWebhookUrl();
                }
                // 2. System Property
                String sysProp = System.getProperty("googleChatWebhookUrl");
                if (sysProp != null && !sysProp.isEmpty()) {
                        return sysProp;
                }
                // 3. Environment Variable / .env
                try {
                        Dotenv dotenv = Dotenv.configure().ignoreIfMissing().load();
                        return dotenv.get("GOOGLE_CHAT_WEBHOOK_URL");
                } catch (Exception e) {
                        return null;
                }
        }

        private static String getMessageType() {
                // 1. Programmatic
                if (GoogleChatConfig.getMessageType() != null && !GoogleChatConfig.getMessageType().isEmpty()) {
                        return GoogleChatConfig.getMessageType();
                }
                // 2. System Property
                String sysProp = System.getProperty("messageType");
                if (sysProp != null && !sysProp.isEmpty()) {
                        return sysProp;
                }
                // 3. Environment Variable / .env
                try {
                        Dotenv dotenv = Dotenv.configure().ignoreIfMissing().load();
                        String envVar = dotenv.get("MESSAGE_TYPE");
                        if (envVar != null && !envVar.isEmpty()) {
                                return envVar;
                        }
                } catch (Exception e) {
                        // Ignore
                }
                // 4. Default
                return "CARD";
        }

        public static void sendNotification(String jsonPayload) {
                String webhookUrl = getWebhookUrl();
                if (webhookUrl == null || webhookUrl.isEmpty()) {
                        System.out.println("Google Chat Webhook URL not found. Skipping notification.");
                        return;
                }

                try {
                        RestAssured.given()
                                        .contentType(ContentType.JSON)
                                        .body(jsonPayload)
                                        .post(webhookUrl)
                                        .then()
                                        .statusCode(200);

                        System.out.println("Google Chat notification sent successfully.");
                } catch (Throwable t) {
                        System.err.println("Failed to send Google Chat notification: " + t);
                }
        }

        public static void sendStartNotification(String projectName, String suiteName, String testFiles,
                        String environment) {
                String messageType = getMessageType();
                String startTime = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));

                if ("TEXT".equalsIgnoreCase(messageType)) {
                        String text = String.format(
                                        "*%s - %s Started*\nStart Time: %s\nEnvironment: %s\nTest Files:\n%s",
                                        projectName, suiteName, startTime, (environment != null ? environment : "N/A"),
                                        testFiles);
                        JSONObject payload = new JSONObject().put("text", text);
                        sendNotification(payload.toString());
                } else {
                        // Default to CARD
                        JSONObject cardHeader = new JSONObject()
                                        .put("title", projectName)
                                        .put("subtitle", suiteName + " - Started");

                        JSONArray widgets = new JSONArray()
                                        .put(createDecoratedTextWidget("CLOCK", "Start Time", startTime));

                        if (environment != null && !environment.isEmpty()) {
                                widgets.put(createDecoratedTextWidgetWithUrl("Environment", environment,
                                                "https://fonts.gstatic.com/s/e/notoemoji/15.0/1f30d/512.png"));
                        }

                        widgets.put(createParagraphWidget("<b>Test Files:</b><br>" + testFiles.replace("\n", "<br>")));

                        JSONObject section = new JSONObject().put("widgets", widgets);

                        JSONObject card = new JSONObject()
                                        .put("header", cardHeader)
                                        .put("sections", new JSONArray().put(section));

                        JSONObject payload = new JSONObject()
                                        .put("cardsV2", new JSONArray().put(new JSONObject().put("card", card)));

                        sendNotification(payload.toString());
                }
        }

        public static void sendFinishNotification(String projectName, String suiteName, int passed, int failed,
                        int skipped, String environment) {
                String messageType = getMessageType();
                String endTime = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
                int total = passed + failed + skipped;

                if ("TEXT".equalsIgnoreCase(messageType)) {
                        String text = String.format(
                                        "*%s - %s Finished*\nEnd Time: %s\nEnvironment: %s\nTotal: %d | Passed: %d | Failed: %d | Skipped: %d",
                                        projectName, suiteName, endTime, (environment != null ? environment : "N/A"),
                                        total, passed, failed,
                                        skipped);
                        JSONObject payload = new JSONObject().put("text", text);
                        sendNotification(payload.toString());
                } else {
                        // Default to CARD
                        JSONObject cardHeader = new JSONObject()
                                        .put("title", projectName)
                                        .put("subtitle", suiteName + " - Finished");

                        JSONArray summaryWidgets = new JSONArray()
                                        .put(createDecoratedTextWidget("CLOCK", "End Time", endTime));

                        if (environment != null && !environment.isEmpty()) {
                                summaryWidgets.put(createDecoratedTextWidgetWithUrl("Environment", environment,
                                                "https://fonts.gstatic.com/s/e/notoemoji/15.0/1f30d/512.png"));
                        }

                        summaryWidgets.put(createDecoratedTextWidget("STAR", "Total Tests", String.valueOf(total)));

                        JSONObject summarySection = new JSONObject()
                                        .put("header", "Execution Summary")
                                        .put("widgets", summaryWidgets);

                        JSONObject resultsSection = new JSONObject()
                                        .put("header", "Results")
                                        .put("widgets", new JSONArray()
                                                        .put(createDecoratedTextWidgetWithUrl("Passed",
                                                                        String.valueOf(passed),
                                                                        "https://fonts.gstatic.com/s/e/notoemoji/15.0/2705/512.png"))
                                                        .put(createDecoratedTextWidgetWithUrl("Failed",
                                                                        String.valueOf(failed),
                                                                        "https://fonts.gstatic.com/s/e/notoemoji/15.0/274c/512.png"))
                                                        .put(createDecoratedTextWidgetWithUrl("Skipped",
                                                                        String.valueOf(skipped),
                                                                        "https://fonts.gstatic.com/s/e/notoemoji/15.0/26a0/512.png")));

                        JSONObject card = new JSONObject()
                                        .put("header", cardHeader)
                                        .put("sections", new JSONArray().put(summarySection).put(resultsSection));

                        JSONObject payload = new JSONObject()
                                        .put("cardsV2", new JSONArray().put(new JSONObject().put("card", card)));

                        sendNotification(payload.toString());
                }
        }

        private static JSONObject createDecoratedTextWidgetWithUrl(String topLabel, String text, String iconUrl) {
                return new JSONObject().put("decoratedText", new JSONObject()
                                .put("startIcon", new JSONObject().put("iconUrl", iconUrl))
                                .put("topLabel", topLabel)
                                .put("text", text));
        }

        private static JSONObject createDecoratedTextWidget(String knownIcon, String topLabel, String text) {
                return new JSONObject().put("decoratedText", new JSONObject()
                                .put("startIcon", new JSONObject().put("knownIcon", knownIcon))
                                .put("topLabel", topLabel)
                                .put("text", text));
        }

        private static JSONObject createParagraphWidget(String text) {
                return new JSONObject().put("textParagraph", new JSONObject().put("text", text));
        }
}

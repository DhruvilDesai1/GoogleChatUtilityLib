package com.teamninja.utilities;

import com.sun.net.httpserver.HttpServer;
import org.testng.Assert;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.Test;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class GoogleChatNotifierTest {

    @AfterMethod
    public void resetConfig() {
        GoogleChatConfig.setWebhookUrl(null);
        GoogleChatConfig.setMessageType(null);
    }

    @Test
    public void unreachableWebhookDoesNotThrow() {
        GoogleChatConfig.setWebhookUrl("http://127.0.0.1:9/webhook");
        try {
            GoogleChatNotifier.sendNotification("{\"text\":\"hi\"}");
        } catch (Throwable t) {
            Assert.fail("sendNotification must not propagate: " + t);
        }
    }

    @Test
    public void unresolvableHostDoesNotThrow() {
        GoogleChatConfig.setWebhookUrl("https://example.invalid/webhook");
        try {
            GoogleChatNotifier.sendNotification("{\"text\":\"hi\"}");
        } catch (Throwable t) {
            Assert.fail("sendNotification must not propagate: " + t);
        }
    }

    @Test
    public void missingWebhookDoesNotThrow() {
        GoogleChatConfig.setWebhookUrl(null);
        try {
            GoogleChatNotifier.sendNotification("{\"text\":\"hi\"}");
        } catch (Throwable t) {
            Assert.fail("sendNotification must not propagate: " + t);
        }
    }

    @Test
    public void startNotificationSurvivesUnreachableWebhook() {
        GoogleChatConfig.setWebhookUrl("http://127.0.0.1:9/webhook");
        try {
            GoogleChatNotifier.sendStartNotification("Proj", "Suite", "- A\n- B\n", "staging");
        } catch (Throwable t) {
            Assert.fail("sendNotification must not propagate: " + t);
        }
    }

    @Test
    public void finishNotificationSurvivesUnreachableWebhook() {
        GoogleChatConfig.setWebhookUrl("http://127.0.0.1:9/webhook");
        try {
            GoogleChatNotifier.sendFinishNotification("Proj", "Suite", 3, 1, 0, "staging");
        } catch (Throwable t) {
            Assert.fail("sendNotification must not propagate: " + t);
        }
    }

    // The five tests above use connection-refused / DNS-failure targets. Those fail inside
    // RestAssured's .post(), throwing a plain Exception (ConnectException / UnknownHostException)
    // that the pre-fix catch (Exception e) already handles — so they pass even against the
    // unpatched code and never exercise the actual defect. This test spins up a real local HTTP
    // server that returns a non-200 status, which makes RestAssured's .then().statusCode(200)
    // throw java.lang.AssertionError (an Error, not an Exception) — the path the fix targets.
    @Test
    public void non200ResponseDoesNotThrow() throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/webhook", exchange -> {
            byte[] body = "not found".getBytes();
            exchange.sendResponseHeaders(404, body.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(body);
            }
        });
        server.start();
        try {
            GoogleChatConfig.setWebhookUrl("http://127.0.0.1:" + server.getAddress().getPort() + "/webhook");
            try {
                GoogleChatNotifier.sendNotification("{\"text\":\"hi\"}");
            } catch (Throwable t) {
                Assert.fail("sendNotification must not propagate: " + t);
            }
        } finally {
            server.stop(0);
        }
    }

    @Test(timeOut = 30000)
    public void unresponsiveServerFailsWithinSocketTimeout() throws Exception {
        try (ServerSocket server = new ServerSocket(0, 1, InetAddress.getLoopbackAddress())) {
            Thread accepter = new Thread(() -> {
                try {
                    // Accept the connection, then never respond.
                    Socket accepted = server.accept();
                    Thread.sleep(25000);
                    accepted.close();
                } catch (Exception ignored) {
                    // Test finished; the socket was closed underneath us.
                }
            });
            accepter.setDaemon(true);
            accepter.start();

            GoogleChatConfig.setWebhookUrl("http://127.0.0.1:" + server.getLocalPort() + "/webhook");
            long startedAt = System.currentTimeMillis();
            try {
                GoogleChatNotifier.sendNotification("{\"text\":\"hi\"}");
            } catch (Throwable t) {
                Assert.fail("sendNotification must not propagate: " + t);
            }
            long elapsed = System.currentTimeMillis() - startedAt;
            Assert.assertTrue(elapsed < 20000,
                    "expected the socket timeout to bound the call, but it took " + elapsed + "ms");
        }
    }
}

package dev.acp.relay;

import org.junit.jupiter.api.*;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Integration tests for {@link RelayClient}.
 *
 * <p>Tests that require a live relay are guarded with {@code @Tag("integration")} and
 * skip automatically when the relay is not reachable.
 * Unit tests (JSON, request building, error parsing) run in any environment.
 */
class RelayClientTest {

    // ── Helpers ───────────────────────────────────────────────────────────

    static final int ALPHA_PORT = 7951;
    static final int BETA_PORT  = 7952;

    static Process alphaProcess;
    static Process betaProcess;

    static RelayClient alpha;
    static RelayClient beta;

    static boolean relayAvailable = false;

    @BeforeAll
    static void startRelays() throws Exception {
        String relayScript = findRelayScript();
        if (relayScript == null) {
            System.out.println("[SKIP] acp_relay.py not found — integration tests will be skipped");
            return;
        }

        alphaProcess = startRelay(relayScript, ALPHA_PORT, "JavaAlpha");
        betaProcess  = startRelay(relayScript, BETA_PORT,  "JavaBeta");

        // Wait for both to be ready
        boolean alphaReady = waitForPort("localhost", ALPHA_PORT, 10_000);
        boolean betaReady  = waitForPort("localhost", BETA_PORT,  10_000);

        if (!alphaReady || !betaReady) {
            System.out.println("[SKIP] Relays did not start in time — integration tests will be skipped");
            return;
        }

        alpha = RelayClient.of("http://localhost:" + ALPHA_PORT);
        beta  = RelayClient.of("http://localhost:" + BETA_PORT);
        relayAvailable = true;
        System.out.println("[OK] Relays started: alpha=" + ALPHA_PORT + " beta=" + BETA_PORT);
    }

    @AfterAll
    static void stopRelays() {
        if (alphaProcess != null) alphaProcess.destroyForcibly();
        if (betaProcess  != null) betaProcess.destroyForcibly();
    }

    // ── Unit tests (no relay needed) ─────────────────────────────────────

    @Test
    @DisplayName("SendRequest.user() factory sets role=user and text")
    void sendRequestUserFactory() {
        SendRequest req = SendRequest.user("hello");
        assertEquals("user",  req.getRole());
        assertEquals("hello", req.getText());
        assertNull(req.getMessageId());
    }

    @Test
    @DisplayName("SendRequest.agent() factory sets role=agent")
    void sendRequestAgentFactory() {
        SendRequest req = SendRequest.agent("done");
        assertEquals("agent", req.getRole());
        assertEquals("done",  req.getText());
    }

    @Test
    @DisplayName("SendRequest.withMessageId() returns new instance")
    void sendRequestWithMessageId() {
        SendRequest base = SendRequest.user("hi");
        SendRequest req  = base.withMessageId("idem-001");
        assertNull(base.getMessageId());          // original unchanged
        assertEquals("idem-001", req.getMessageId());
    }

    @Test
    @DisplayName("SendRequest.sync() sets sync=true and timeout")
    void sendRequestSync() {
        SendRequest req = SendRequest.user("go").sync(30);
        assertTrue(req.isSync());
        assertEquals(30, req.getTimeout());
    }

    @Test
    @DisplayName("Part.text() factory")
    void partTextFactory() {
        Part p = Part.text("hello");
        assertEquals("text",  p.getType());
        assertEquals("hello", p.getText());
        assertNull(p.getMimeType());
    }

    @Test
    @DisplayName("Part.file() factory")
    void partFileFactory() {
        Part p = Part.file("https://example.com/doc.pdf", "application/pdf");
        assertEquals("file", p.getType());
        assertEquals("https://example.com/doc.pdf", p.getFileUrl());
        assertEquals("application/pdf", p.getMimeType());
    }

    @Test
    @DisplayName("Task.isTerminal() for all states")
    void taskIsTerminal() {
        assertTrue(new Task("t", "completed",   0, 0, null).isTerminal());
        assertTrue(new Task("t", "failed",      0, 0, null).isTerminal());
        assertTrue(new Task("t", "canceled",    0, 0, null).isTerminal());
        assertFalse(new Task("t", "submitted",  0, 0, null).isTerminal());
        assertFalse(new Task("t", "working",    0, 0, null).isTerminal());
        assertFalse(new Task("t", "input_required", 0, 0, null).isTerminal());
    }

    @Test
    @DisplayName("Message.firstText() returns first text part")
    void messageFirstText() {
        List<Part> parts = Arrays.asList(Part.text("hello"), Part.text("world"));
        Message msg = new Message("message", "id1", 0, "from", "user", parts, null, null);
        assertEquals("hello", msg.firstText());
    }

    @Test
    @DisplayName("Message.firstText() returns null when no text parts")
    void messageFirstTextEmpty() {
        Message msg = new Message("message", "id1", 0, "from", "user",
                Collections.emptyList(), null, null);
        assertNull(msg.firstText());
    }

    @Test
    @DisplayName("AcpException carries HTTP status and error code")
    void acpExceptionFields() {
        AcpException e = new AcpException(404, "ERR_NOT_FOUND", "not found");
        assertEquals(404,             e.getHttpStatus());
        assertEquals("ERR_NOT_FOUND", e.getErrorCode());
        assertTrue(e.getMessage().contains("404"));
        assertTrue(e.getMessage().contains("ERR_NOT_FOUND"));
    }

    // ── Integration tests ─────────────────────────────────────────────────

    @Test
    @DisplayName("I1: ping() returns true when relay is running")
    void i1Ping() {
        assumeRelayAvailable();
        assertTrue(alpha.ping(), "alpha relay should be reachable");
        assertTrue(beta.ping(),  "beta relay should be reachable");
    }

    @Test
    @DisplayName("I2: agentCard() returns self with name and link")
    void i2AgentCard() {
        assumeRelayAvailable();
        Map<String, Object> card = alpha.agentCard();
        assertNotNull(card);
        @SuppressWarnings("unchecked")
        Map<String, Object> self = (Map<String, Object>) card.get("self");
        assertNotNull(self, "agentCard should have 'self' key");
        String name = Json.str(self, "name");
        assertNotNull(name, "self.name should not be null");
    }

    @Test
    @DisplayName("I3: link() returns acp:// link")
    void i3Link() {
        assumeRelayAvailable();
        String link = alpha.link();
        assertNotNull(link, "link should not be null");
        assertTrue(link.startsWith("acp://"), "link should start with acp://");
    }

    @Test
    @DisplayName("I4: P2P connect alpha <-> beta")
    void i4Connect() {
        assumeRelayAvailable();
        String betaLink  = beta.link();
        String peerId    = alpha.connectPeer(betaLink);
        assertNotNull(peerId, "peerId should not be null after connect");
    }

    @Test
    @DisplayName("I5: send and recv round-trip")
    void i5SendRecv() throws Exception {
        assumeRelayAvailable();

        // Ensure connected — poll until status shows connected
        String betaLink = beta.link();
        alpha.connectPeer(betaLink);

        long deadline = System.currentTimeMillis() + 5000;
        while (System.currentTimeMillis() < deadline) {
            Map<String, Object> st = alpha.status();
            if (Boolean.TRUE.equals(st.get("connected"))) break;
            Thread.sleep(100);
        }
        Thread.sleep(200);  // extra settle

        // Alpha sends to Beta
        SendResponse resp = alpha.send(SendRequest.user("Java SDK test message"));
        assertTrue(resp.isOk(), "send should succeed");
        assertNotNull(resp.getMessageId());

        // Beta polls for messages
        Thread.sleep(400);
        List<Message> msgs = beta.recv();
        assertTrue(msgs.size() >= 1, "beta should have received at least 1 message");

        // Find our message
        boolean found = msgs.stream()
                .anyMatch(m -> "Java SDK test message".equals(m.firstText()));
        assertTrue(found, "beta should have received the test message");
    }

    @Test
    @DisplayName("I6: idempotency — same message_id sent twice, both return ok")
    void i6Idempotency() throws Exception {
        assumeRelayAvailable();

        String betaLink = beta.link();
        alpha.connectPeer(betaLink);
        Thread.sleep(300);

        SendRequest req = SendRequest.user("idempotent").withMessageId("java-idem-test-001");
        SendResponse r1 = alpha.send(req);
        SendResponse r2 = alpha.send(req);

        assertTrue(r1.isOk(), "first send should succeed");
        assertTrue(r2.isOk(), "second send (idempotent) should succeed");
    }

    @Test
    @DisplayName("I7: send to invalid peer returns AcpException with 4xx")
    void i7InvalidPeer() {
        assumeRelayAvailable();
        AcpException ex = assertThrows(AcpException.class,
                () -> alpha.sendToPeer("peer_nonexistent", SendRequest.user("hi")));
        assertTrue(ex.getHttpStatus() >= 400 && ex.getHttpStatus() < 500,
                "should be a 4xx error, got: " + ex.getHttpStatus());
    }

    @Test
    @DisplayName("I8: getTasks() returns a list (possibly empty)")
    void i8GetTasks() {
        assumeRelayAvailable();
        List<Task> tasks = alpha.getTasks();
        assertNotNull(tasks);
    }

    @Test
    @DisplayName("I9: status() returns agent_name and session_id")
    void i9Status() {
        assumeRelayAvailable();
        Map<String, Object> status = alpha.status();
        assertNotNull(status.get("agent_name"),  "status.agent_name should be present");
        assertNotNull(status.get("session_id"),  "status.session_id should be present");
        assertNotNull(status.get("acp_version"), "status.acp_version should be present");
    }

    @Test
    @DisplayName("I10: concurrent sends — 20 messages in parallel")
    void i10ConcurrentSends() throws Exception {
        assumeRelayAvailable();

        // Re-connect to ensure a fresh, stable WS connection for this test
        String betaLink = beta.link();
        alpha.connectPeer(betaLink);

        // Poll until alpha sees beta as connected
        long deadline = System.currentTimeMillis() + 5000;
        while (System.currentTimeMillis() < deadline) {
            Map<String, Object> status = alpha.status();
            if (Boolean.TRUE.equals(status.get("connected"))) break;
            Thread.sleep(100);
        }
        Thread.sleep(300);  // extra settle time

        int n = 20;
        CountDownLatch latch = new CountDownLatch(n);
        AtomicInteger success = new AtomicInteger(0);
        AtomicInteger failure = new AtomicInteger(0);

        ExecutorService pool = Executors.newFixedThreadPool(5);
        for (int i = 0; i < n; i++) {
            final int idx = i;
            pool.submit(() -> {
                try {
                    SendResponse r = alpha.send(
                            SendRequest.user("concurrent-" + idx)
                                    .withMessageId("java-concurrent-" + idx));
                    if (r.isOk()) success.incrementAndGet();
                    else          failure.incrementAndGet();
                } catch (Exception e) {
                    failure.incrementAndGet();
                } finally {
                    latch.countDown();
                }
            });
        }

        assertTrue(latch.await(15, TimeUnit.SECONDS), "all sends should complete within 15s");
        pool.shutdown();

        // Allow up to 2 failures due to ThreadingHTTPServer connection-limit under burst load
        // (known relay limitation, not an SDK issue — see BUGS.md BUG-012 notes)
        assertTrue(success.get() >= n - 2,
                "at least " + (n - 2) + "/" + n + " concurrent sends should succeed, got: " + success.get());
        assertTrue(failure.get() <= 2,
                "at most 2 failures acceptable under burst, got: " + failure.get());
    }

    // ── Utilities ─────────────────────────────────────────────────────────

    private void assumeRelayAvailable() {
        org.junit.jupiter.api.Assumptions.assumeTrue(relayAvailable,
                "Relay not available — skipping integration test");
    }

    private static String findRelayScript() {
        String[] candidates = {
            "relay/acp_relay.py",
            "../relay/acp_relay.py",
            "../../relay/acp_relay.py",
        };
        File cwd = new File(System.getProperty("user.dir"));
        for (String c : candidates) {
            File f = new File(cwd, c);
            if (f.exists()) return f.getAbsolutePath();
        }
        // Try from repo root
        File repoRoot = cwd;
        for (int i = 0; i < 4; i++) {
            File f = new File(repoRoot, "relay/acp_relay.py");
            if (f.exists()) return f.getAbsolutePath();
            repoRoot = repoRoot.getParentFile();
            if (repoRoot == null) break;
        }
        return null;
    }

    private static Process startRelay(String script, int port, String name) throws Exception {
        ProcessBuilder pb = new ProcessBuilder(
                "python3", script,
                "--name", name,
                "--http-port", String.valueOf(port),
                "--ws-port",   String.valueOf(port - 100)
        );
        pb.redirectErrorStream(true);
        pb.redirectOutput(ProcessBuilder.Redirect.DISCARD);
        return pb.start();
    }

    private static boolean waitForPort(String host, int port, long timeoutMs) {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            try (Socket s = new Socket()) {
                s.connect(new InetSocketAddress(host, port), 200);
                return true;
            } catch (IOException e) {
                try { Thread.sleep(100); } catch (InterruptedException ie) { break; }
            }
        }
        return false;
    }
}

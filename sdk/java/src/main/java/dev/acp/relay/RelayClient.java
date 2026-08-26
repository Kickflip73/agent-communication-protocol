package dev.acp.relay;

import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.function.Consumer;

/**
 * HTTP client for the ACP Relay ({@code acp_relay.py}).
 *
 * <p><b>Quick start:</b>
 * <pre>{@code
 * RelayClient client = RelayClient.of("http://localhost:7901");
 *
 * // Send a message to the connected peer
 * SendResponse resp = client.send(SendRequest.user("Hello from Java!"));
 *
 * // Poll for received messages
 * List<Message> msgs = client.recv();
 * msgs.forEach(m -> System.out.println(m.firstText()));
 * }</pre>
 *
 * <p><b>Zero external dependencies</b> — requires JDK 11+.
 *
 * <p>All methods throw {@link AcpException} (unchecked) on network or relay error.
 */
public final class RelayClient implements Closeable {

    private static final Duration DEFAULT_TIMEOUT = Duration.ofSeconds(30);

    private final String            baseUrl;
    private final HttpClient        http;

    // ── Construction ──────────────────────────────────────────────────────

    private RelayClient(String baseUrl, HttpClient http) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.http    = http;
    }

    /**
     * Create a client with default settings (30 s timeout, no auth).
     *
     * @param baseUrl relay base URL, e.g. {@code "http://localhost:7901"}
     */
    public static RelayClient of(String baseUrl) {
        HttpClient hc = HttpClient.newBuilder()
                .connectTimeout(DEFAULT_TIMEOUT)
                .build();
        return new RelayClient(baseUrl, hc);
    }

    /**
     * Create a client with a custom {@link HttpClient} (for testing, custom TLS, etc.).
     */
    public static RelayClient of(String baseUrl, HttpClient httpClient) {
        return new RelayClient(baseUrl, httpClient);
    }

    // ── Core messaging ────────────────────────────────────────────────────

    /**
     * Send a message to the connected peer via {@code POST /message:send}.
     *
     * <pre>{@code
     * SendResponse r = client.send(SendRequest.user("hello"));
     * System.out.println(r.getMessageId());
     * }</pre>
     */
    public SendResponse send(SendRequest req) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("role", req.getRole());
        if (req.getText() != null) {
            body.put("text", req.getText());
        }
        if (req.getParts() != null && !req.getParts().isEmpty()) {
            List<Map<String, Object>> parts = new ArrayList<>();
            for (Part p : req.getParts()) {
                Map<String, Object> pm = new LinkedHashMap<>();
                pm.put("type", p.getType());
                if (p.getText()     != null) pm.put("text",     p.getText());
                if (p.getMimeType() != null) pm.put("mime_type", p.getMimeType());
                if (p.getFileUrl()  != null) pm.put("file_url", p.getFileUrl());
                if (p.getData()     != null) pm.put("data",     p.getData());
                parts.add(pm);
            }
            body.put("parts", parts);
        }
        if (req.getMessageId() != null) body.put("message_id", req.getMessageId());
        if (req.getTaskId()    != null) body.put("task_id",    req.getTaskId());
        if (req.getContextId() != null) body.put("context_id", req.getContextId());
        if (req.isSync()) {
            body.put("sync", true);
            if (req.getTimeout() > 0) body.put("timeout", req.getTimeout());
        }

        Map<String, Object> r = postJson("/message:send", body);
        return new SendResponse(
                Json.bool(r, "ok"),
                Json.str(r,  "message_id"),
                Json.str(r,  "error"),
                parseTask(Json.obj(r, "task"))
        );
    }

    /**
     * Poll for received messages via {@code GET /recv}.
     *
     * @return unmodifiable list of messages (may be empty)
     */
    public List<Message> recv() {
        return recv(0, 0L);
    }

    /**
     * Poll for received messages with optional limit and since-cursor.
     *
     * @param limit maximum number of messages (0 = server default)
     * @param since return only messages with {@code ts > since} (Unix millis; 0 = all)
     */
    public List<Message> recv(int limit, long since) {
        StringBuilder url = new StringBuilder(baseUrl).append("/recv?");
        if (limit > 0) url.append("limit=").append(limit).append("&");
        if (since > 0) url.append("since=").append(since).append("&");

        Map<String, Object> r = getJson(url.toString());
        List<Object> raw = Json.list(r, "messages");
        List<Message> out = new ArrayList<>(raw.size());
        for (Object item : raw) {
            if (item instanceof Map) out.add(parseMessage((Map<?, ?>) item));
        }
        return Collections.unmodifiableList(out);
    }

    // ── Status & discovery ────────────────────────────────────────────────

    /**
     * Fetch relay runtime status via {@code GET /status}.
     *
     * @return map with keys {@code state}, {@code session_id}, {@code link}, {@code agent_name}, etc.
     */
    public Map<String, Object> status() {
        return getJson(baseUrl + "/status");
    }

    /**
     * Reachability ping: fetch {@code /.well-known/acp.json} and return {@code true} on success.
     */
    public boolean ping() {
        try {
            getJson(baseUrl + "/.well-known/acp.json");
            return true;
        } catch (AcpException e) {
            return false;
        }
    }

    /**
     * Fetch the relay's AgentCard via {@code GET /.well-known/acp.json}.
     *
     * @return raw map (keys: {@code self}, {@code peer}, …)
     */
    public Map<String, Object> agentCard() {
        return getJson(baseUrl + "/.well-known/acp.json");
    }

    /**
     * Get the session link ({@code acp://…}) for sharing with another agent.
     *
     * @return link string, or {@code null} if not yet established
     */
    public String link() {
        Map<String, Object> r = getJson(baseUrl + "/link");
        return Json.str(r, "link");
    }

    // ── Task management ───────────────────────────────────────────────────

    /**
     * List all tasks via {@code GET /tasks}.
     */
    public List<Task> getTasks() {
        Map<String, Object> r = getJson(baseUrl + "/tasks");
        List<Object> raw = Json.list(r, "tasks");
        List<Task> out = new ArrayList<>(raw.size());
        for (Object item : raw) {
            if (item instanceof Map) out.add(parseTask((Map<?, ?>) item));
        }
        return Collections.unmodifiableList(out);
    }

    /**
     * Cancel a task via {@code POST /tasks/{id}:cancel}.
     *
     * @throws AcpException if the relay returns an error
     */
    public void cancelTask(String taskId) {
        Map<String, Object> r = postJson("/tasks/" + taskId + ":cancel", Collections.emptyMap());
        if (!Json.bool(r, "ok")) {
            throw new AcpException(-1, Json.str(r, "code"), Json.str(r, "message"));
        }
    }

    /**
     * List connected peers via {@code GET /peers}.
     *
     * @return list of raw peer maps
     */
    public List<Map<String, Object>> peers() {
        Map<String, Object> r = getJson(baseUrl + "/peers");
        List<Object> raw = Json.list(r, "peers");
        List<Map<String, Object>> out = new ArrayList<>(raw.size());
        for (Object item : raw) {
            if (item instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> peer = (Map<String, Object>) item;
                out.add(peer);
            }
        }
        return Collections.unmodifiableList(out);
    }

    /**
     * Connect to a peer using an {@code acp://} link via {@code POST /peers/connect}.
     *
     * @param acpLink  the {@code acp://…} link from the other relay
     * @return peer_id assigned by this relay
     */
    public String connectPeer(String acpLink) {
        Map<String, Object> body = Collections.singletonMap("link", acpLink);
        Map<String, Object> r    = postJson("/peers/connect", body);
        if (!Json.bool(r, "ok")) {
            throw new AcpException(-1, Json.str(r, "code"), Json.str(r, "message"));
        }
        return Json.str(r, "peer_id");
    }

    /**
     * Send a message to a specific peer via {@code POST /peer/{peerId}/send}.
     * Use this when multiple peers are connected (avoids {@code ERR_AMBIGUOUS_PEER}).
     */
    public SendResponse sendToPeer(String peerId, SendRequest req) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("role", req.getRole());
        if (req.getText() != null) body.put("text", req.getText());
        if (req.getMessageId() != null) body.put("message_id", req.getMessageId());

        Map<String, Object> r = postJson("/peer/" + peerId + "/send", body);
        return new SendResponse(
                Json.bool(r, "ok"),
                Json.str(r,  "message_id"),
                Json.str(r,  "error"),
                parseTask(Json.obj(r, "task"))
        );
    }

    // ── Skills ────────────────────────────────────────────────────────────

    /**
     * Query peer capabilities via {@code POST /skills/query}.
     *
     * @param filter optional filter map (pass empty map or null for all skills)
     * @return list of raw skill maps (keys: {@code id}, {@code name}, {@code description}, …)
     */
    public List<Map<String, Object>> querySkills(Map<String, Object> filter) {
        Map<String, Object> body = filter != null ? filter : Collections.emptyMap();
        Map<String, Object> r    = postJson("/skills/query", body);
        List<Object> raw = Json.list(r, "skills");
        List<Map<String, Object>> out = new ArrayList<>(raw.size());
        for (Object item : raw) {
            if (item instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> skill = (Map<String, Object>) item;
                out.add(skill);
            }
        }
        return Collections.unmodifiableList(out);
    }

    // ── SSE streaming ─────────────────────────────────────────────────────

    /**
     * Subscribe to the SSE event stream ({@code GET /stream}) and deliver events to a callback.
     *
     * <p>This method <em>blocks</em> until the stream is closed or an error occurs.
     * Run it on a dedicated thread or virtual thread (JDK 21+) for non-blocking use.
     *
     * <pre>{@code
     * new Thread(() -> client.stream(ev -> {
     *     System.out.println(ev.getType() + ": " + ev.getData());
     * })).start();
     * }</pre>
     *
     * @param handler  called for every SSE event received
     * @throws AcpException on connection failure
     */
    public void stream(Consumer<SseEvent> handler) {
        HttpRequest request;
        try {
            request = HttpRequest.newBuilder()
                    .uri(new URI(baseUrl + "/stream"))
                    .header("Accept", "text/event-stream")
                    .GET()
                    .build();
        } catch (URISyntaxException e) {
            throw new AcpException("Invalid URL: " + baseUrl + "/stream", e);
        }

        HttpResponse<InputStream> response;
        try {
            response = http.send(request, HttpResponse.BodyHandlers.ofInputStream());
        } catch (IOException | InterruptedException e) {
            throw new AcpException("SSE connection failed: " + e.getMessage(), e);
        }

        if (response.statusCode() >= 400) {
            throw new AcpException(response.statusCode(), null, "SSE stream returned error");
        }

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
            String eventType = null;
            StringBuilder dataBuffer = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.startsWith("event:")) {
                    eventType = line.substring(6).trim();
                } else if (line.startsWith("data:")) {
                    dataBuffer.append(line.substring(5).trim());
                } else if (line.isEmpty()) {
                    // end of event block
                    if (dataBuffer.length() > 0) {
                        handler.accept(new SseEvent(
                                eventType != null ? eventType : "message",
                                dataBuffer.toString()));
                    }
                    eventType = null;
                    dataBuffer.setLength(0);
                }
            }
        } catch (IOException e) {
            throw new AcpException("SSE stream read error: " + e.getMessage(), e);
        }
    }

    // ── Availability (v1.2) ───────────────────────────────────────────────

    /**
     * Update this relay's availability metadata via {@code PATCH /.well-known/acp.json}.
     * Useful for heartbeat/cron agents to advertise their schedule.
     *
     * @param availability map of availability fields (e.g. {@code mode}, {@code next_active_at})
     */
    public void patchAvailability(Map<String, Object> availability) {
        Map<String, Object> body = Collections.singletonMap("availability", availability);
        patchJson("/.well-known/acp.json", body);
    }

    // ── Closeable ─────────────────────────────────────────────────────────

    @Override
    public void close() {
        // HttpClient in JDK 11 does not implement Closeable; resources are released by GC.
        // This method exists so RelayClient can be used in try-with-resources.
    }

    // ── HTTP internals ────────────────────────────────────────────────────

    private Map<String, Object> getJson(String url) {
        HttpRequest request;
        try {
            request = HttpRequest.newBuilder()
                    .uri(new URI(url))
                    .header("Accept", "application/json")
                    .GET()
                    .timeout(DEFAULT_TIMEOUT)
                    .build();
        } catch (URISyntaxException e) {
            throw new AcpException("Invalid URL: " + url, e);
        }
        return executeAndParse(request);
    }

    private Map<String, Object> postJson(String path, Map<String, Object> body) {
        String jsonBody = Json.toJson(body);
        HttpRequest request;
        try {
            request = HttpRequest.newBuilder()
                    .uri(new URI(baseUrl + path))
                    .header("Content-Type", "application/json")
                    .header("Accept", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8))
                    .timeout(DEFAULT_TIMEOUT)
                    .build();
        } catch (URISyntaxException e) {
            throw new AcpException("Invalid URL: " + baseUrl + path, e);
        }
        return executeAndParse(request);
    }

    private void patchJson(String path, Map<String, Object> body) {
        String jsonBody = Json.toJson(body);
        HttpRequest request;
        try {
            request = HttpRequest.newBuilder()
                    .uri(new URI(baseUrl + path))
                    .header("Content-Type", "application/json")
                    .method("PATCH", HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8))
                    .timeout(DEFAULT_TIMEOUT)
                    .build();
        } catch (URISyntaxException e) {
            throw new AcpException("Invalid URL: " + baseUrl + path, e);
        }
        executeAndParse(request);
    }

    private Map<String, Object> executeAndParse(HttpRequest request) {
        HttpResponse<String> response;
        try {
            response = http.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (IOException | InterruptedException e) {
            throw new AcpException("HTTP request failed: " + e.getMessage(), e);
        }

        String responseBody = response.body();
        if (response.statusCode() >= 400) {
            // Try to extract ACP error code from JSON body
            try {
                Map<String, Object> err = Json.parseObject(responseBody);
                String code    = Json.str(err, "code");
                String message = Json.str(err, "message");
                if (code == null) code = Json.str(err, "error");
                if (message == null) message = responseBody;
                throw new AcpException(response.statusCode(), code, message);
            } catch (AcpException ex) {
                throw ex;
            } catch (Exception ex) {
                throw new AcpException(response.statusCode(), null, responseBody);
            }
        }

        if (responseBody == null || responseBody.isBlank()) {
            return Collections.emptyMap();
        }
        return Json.parseObject(responseBody);
    }

    // ── Object builders ───────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private Message parseMessage(Map<?, ?> raw) {
        Map<String, Object> m = (Map<String, Object>) raw;
        List<Part> parts = new ArrayList<>();
        for (Object po : Json.list(m, "parts")) {
            if (po instanceof Map) {
                Map<String, Object> pm = (Map<String, Object>) po;
                // Relay returns parts with "content" key (not "text") for text parts
                String text = Json.str(pm, "text");
                if (text == null) text = Json.str(pm, "content");
                parts.add(new Part.Builder(Json.str(pm, "type") != null ? Json.str(pm, "type") : "text")
                        .text(text)
                        .mimeType(Json.str(pm, "mime_type"))
                        .fileUrl(Json.str(pm, "file_url"))
                        .data(pm.get("data"))
                        .build());
            }
        }
        // ts may be in "received_at" (float epoch) or "ts" (millis) depending on relay version
        long ts = Json.lng(m, "ts");
        if (ts == 0) {
            Object ra = m.get("received_at");
            if (ra instanceof Number) ts = (long) (((Number) ra).doubleValue() * 1000);
        }
        return new Message(
                Json.str(m, "type"),
                Json.str(m, "message_id") != null ? Json.str(m, "message_id") : Json.str(m, "id"),
                ts,
                Json.str(m, "from"),
                Json.str(m, "role"),
                parts,
                Json.str(m, "task_id"),
                Json.str(m, "context_id")
        );
    }

    @SuppressWarnings("unchecked")
    private Task parseTask(Map<?, ?> raw) {
        if (raw == null || raw.isEmpty()) return null;
        Map<String, Object> m = (Map<String, Object>) raw;
        return new Task(
                Json.str(m, "id"),
                Json.str(m, "status"),
                Json.lng(m, "created_at"),
                Json.lng(m, "updated_at"),
                Json.str(m, "message_id")
        );
    }
}

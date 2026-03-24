package dev.acp.relay;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * Request payload for {@code POST /message:send}.
 *
 * <p>Use the builder for full control, or the convenience factories:
 * <pre>{@code
 * SendRequest.user("Hello!")
 * SendRequest.agent("Task complete.").withMessageId("idempotent-id-001")
 * }</pre>
 */
public final class SendRequest {

    private final String      role;
    private final List<Part>  parts;
    private final String      text;
    private final String      messageId;
    private final String      taskId;
    private final String      contextId;
    private final boolean     sync;
    private final int         timeout;

    private SendRequest(Builder b) {
        this.role      = Objects.requireNonNull(b.role, "role is required");
        this.parts     = b.parts != null ? Collections.unmodifiableList(b.parts) : null;
        this.text      = b.text;
        this.messageId = b.messageId;
        this.taskId    = b.taskId;
        this.contextId = b.contextId;
        this.sync      = b.sync;
        this.timeout   = b.timeout;
    }

    // ── Factories ────────────────────────────────────────────────────────

    /** Convenience: {@code role="user"} text message. */
    public static SendRequest user(String text) {
        return new Builder("user").text(text).build();
    }

    /** Convenience: {@code role="agent"} text message. */
    public static SendRequest agent(String text) {
        return new Builder("agent").text(text).build();
    }

    // ── Fluent mutators (return new instances) ───────────────────────────

    /** Return a copy of this request with the given client-side idempotency key. */
    public SendRequest withMessageId(String id) {
        return toBuilder().messageId(id).build();
    }

    /** Return a copy of this request linked to a task. */
    public SendRequest withTaskId(String id) {
        return toBuilder().taskId(id).build();
    }

    /** Return a copy of this request with a context group ID. */
    public SendRequest withContextId(String id) {
        return toBuilder().contextId(id).build();
    }

    /** Return a copy of this request requesting synchronous execution. */
    public SendRequest sync(int timeoutSeconds) {
        return toBuilder().sync(true).timeout(timeoutSeconds).build();
    }

    // ── Accessors ────────────────────────────────────────────────────────

    public String     getRole()      { return role; }
    public List<Part> getParts()     { return parts; }
    public String     getText()      { return text; }
    public String     getMessageId() { return messageId; }
    public String     getTaskId()    { return taskId; }
    public String     getContextId() { return contextId; }
    public boolean    isSync()       { return sync; }
    public int        getTimeout()   { return timeout; }

    private Builder toBuilder() {
        return new Builder(role)
                .parts(parts != null ? parts : null)
                .text(text)
                .messageId(messageId)
                .taskId(taskId)
                .contextId(contextId)
                .sync(sync)
                .timeout(timeout);
    }

    // ── Builder ──────────────────────────────────────────────────────────

    public static final class Builder {
        private final String role;
        private List<Part> parts;
        private String text;
        private String messageId;
        private String taskId;
        private String contextId;
        private boolean sync;
        private int timeout;

        public Builder(String role) { this.role = role; }

        public Builder parts(List<Part> v)  { this.parts = v;     return this; }
        public Builder parts(Part... v)     { this.parts = Arrays.asList(v); return this; }
        public Builder text(String v)       { this.text = v;       return this; }
        public Builder messageId(String v)  { this.messageId = v;  return this; }
        public Builder taskId(String v)     { this.taskId = v;     return this; }
        public Builder contextId(String v)  { this.contextId = v;  return this; }
        public Builder sync(boolean v)      { this.sync = v;       return this; }
        public Builder timeout(int v)       { this.timeout = v;    return this; }

        public SendRequest build() { return new SendRequest(this); }
    }
}

package dev.acp.relay;

/**
 * A single Server-Sent Event received from {@code GET /stream}.
 *
 * <p>ACP event types: {@code "acp.message"}, {@code "acp.artifact"}, {@code "acp.status"}.
 */
public final class SseEvent {

    private final String type;
    private final String data;

    SseEvent(String type, String data) {
        this.type = type;
        this.data = data;
    }

    /** SSE event type (the value after {@code event:} in the stream). */
    public String getType() { return type; }

    /** Raw JSON data payload (the value after {@code data:} in the stream). */
    public String getData() { return data; }

    @Override public String toString() {
        return "SseEvent{type=" + type + ", data=" + data + "}";
    }
}

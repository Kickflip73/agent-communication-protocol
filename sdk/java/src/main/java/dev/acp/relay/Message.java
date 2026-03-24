package dev.acp.relay;

import java.util.Collections;
import java.util.List;

/**
 * An ACP message envelope, as returned by {@code GET /recv}.
 */
public final class Message {

    private final String type;
    private final String messageId;
    private final long   ts;
    private final String from;
    private final String role;
    private final List<Part> parts;
    private final String taskId;
    private final String contextId;

    public Message(String type, String messageId, long ts, String from,
                   String role, List<Part> parts, String taskId, String contextId) {
        this.type      = type;
        this.messageId = messageId;
        this.ts        = ts;
        this.from      = from;
        this.role      = role;
        this.parts     = parts != null ? Collections.unmodifiableList(parts) : Collections.emptyList();
        this.taskId    = taskId;
        this.contextId = contextId;
    }

    public String      getType()      { return type; }
    public String      getMessageId() { return messageId; }
    public long        getTs()        { return ts; }
    public String      getFrom()      { return from; }
    public String      getRole()      { return role; }
    public List<Part>  getParts()     { return parts; }
    public String      getTaskId()    { return taskId; }
    public String      getContextId() { return contextId; }

    /** Convenience: return the text of the first text-type Part, or {@code null} if none. */
    public String firstText() {
        return parts.stream()
                .filter(p -> "text".equals(p.getType()) && p.getText() != null)
                .map(Part::getText)
                .findFirst()
                .orElse(null);
    }

    @Override public String toString() {
        return "Message{id=" + messageId + ", role=" + role + ", text=" + firstText() + "}";
    }
}

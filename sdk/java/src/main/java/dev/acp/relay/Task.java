package dev.acp.relay;

/**
 * An ACP Task object (spec §5).
 *
 * <p>Valid status values: {@code submitted}, {@code working},
 * {@code completed}, {@code failed}, {@code input_required}.
 */
public final class Task {

    private final String id;
    private final String status;
    private final long   createdAt;
    private final long   updatedAt;
    private final String messageId;

    public Task(String id, String status, long createdAt, long updatedAt, String messageId) {
        this.id        = id;
        this.status    = status;
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
        this.messageId = messageId;
    }

    public String getId()        { return id; }
    public String getStatus()    { return status; }
    public long   getCreatedAt() { return createdAt; }
    public long   getUpdatedAt() { return updatedAt; }
    public String getMessageId() { return messageId; }

    /** {@code true} when the task has reached a terminal state. */
    public boolean isTerminal() {
        return "completed".equals(status) || "failed".equals(status) || "canceled".equals(status);
    }

    @Override public String toString() {
        return "Task{id=" + id + ", status=" + status + "}";
    }
}

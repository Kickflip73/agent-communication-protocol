package dev.acp.relay;

/**
 * Response from {@code POST /message:send} or {@code POST /peer/{id}/send}.
 */
public final class SendResponse {

    private final boolean ok;
    private final String  messageId;
    private final String  error;
    private final Task    task;

    SendResponse(boolean ok, String messageId, String error, Task task) {
        this.ok        = ok;
        this.messageId = messageId;
        this.error     = error;
        this.task      = task;
    }

    /** {@code true} if the relay accepted the message. */
    public boolean isOk()          { return ok; }

    /** Server-assigned message ID (for idempotency tracking). */
    public String  getMessageId()  { return messageId; }

    /** ACP error description if {@code ok == false}. */
    public String  getError()      { return error; }

    /**
     * Task linked to this message, or {@code null} if no task was created.
     * Only present when {@code task_id} was specified in the request or when
     * {@code sync=true} was set.
     */
    public Task    getTask()       { return task; }

    @Override public String toString() {
        return "SendResponse{ok=" + ok + ", messageId=" + messageId
                + (task != null ? ", task=" + task : "") + "}";
    }
}

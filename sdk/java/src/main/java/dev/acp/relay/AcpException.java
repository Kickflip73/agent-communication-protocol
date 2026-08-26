package dev.acp.relay;

/**
 * Thrown when the ACP Relay returns an error response or a network failure occurs.
 */
public final class AcpException extends RuntimeException {

    /** HTTP status code, or -1 if not applicable (e.g. I/O error). */
    private final int httpStatus;

    /** ACP error code string (e.g. {@code "ERR_NOT_FOUND"}), or {@code null}. */
    private final String errorCode;

    public AcpException(String message) {
        super(message);
        this.httpStatus = -1;
        this.errorCode  = null;
    }

    public AcpException(String message, Throwable cause) {
        super(message, cause);
        this.httpStatus = -1;
        this.errorCode  = null;
    }

    public AcpException(int httpStatus, String errorCode, String message) {
        super(String.format("HTTP %d [%s]: %s", httpStatus, errorCode, message));
        this.httpStatus = httpStatus;
        this.errorCode  = errorCode;
    }

    /** HTTP status code returned by the relay, or {@code -1} for non-HTTP errors. */
    public int getHttpStatus() { return httpStatus; }

    /** ACP error code (e.g. {@code "ERR_NOT_FOUND"}), or {@code null}. */
    public String getErrorCode() { return errorCode; }
}

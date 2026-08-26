package dev.acp.relay;

import java.util.Objects;

/**
 * A single content unit in an ACP message.
 *
 * <p>ACP supports three part types:
 * <ul>
 *   <li>{@code "text"} – plain or markdown text (most common)</li>
 *   <li>{@code "file"} – a URL or base64-encoded payload</li>
 *   <li>{@code "data"} – arbitrary JSON-serialisable object</li>
 * </ul>
 *
 * <p>Convenience factories: {@link #text(String)}, {@link #file(String, String)}.
 */
public final class Part {

    private final String type;
    private final String text;
    private final String mimeType;
    private final String fileUrl;
    private final Object data;

    private Part(Builder b) {
        this.type     = Objects.requireNonNull(b.type, "type");
        this.text     = b.text;
        this.mimeType = b.mimeType;
        this.fileUrl  = b.fileUrl;
        this.data     = b.data;
    }

    // ── Factories ────────────────────────────────────────────────────────

    /** Create a plain-text part. */
    public static Part text(String text) {
        return new Builder("text").text(text).build();
    }

    /** Create a file part with an optional MIME type. Pass {@code null} for mimeType if unknown. */
    public static Part file(String fileUrl, String mimeType) {
        return new Builder("file").fileUrl(fileUrl).mimeType(mimeType).build();
    }

    /** Create a data part wrapping an arbitrary object (will be JSON-serialised). */
    public static Part data(Object data) {
        return new Builder("data").data(data).build();
    }

    // ── Accessors ────────────────────────────────────────────────────────

    public String getType()     { return type; }
    public String getText()     { return text; }
    public String getMimeType() { return mimeType; }
    public String getFileUrl()  { return fileUrl; }
    public Object getData()     { return data; }

    @Override public String toString() {
        return "Part{type=" + type + ", text=" + text + "}";
    }

    // ── Builder ──────────────────────────────────────────────────────────

    public static final class Builder {
        private final String type;
        private String text;
        private String mimeType;
        private String fileUrl;
        private Object data;

        public Builder(String type) { this.type = type; }

        public Builder text(String v)     { this.text = v;     return this; }
        public Builder mimeType(String v) { this.mimeType = v; return this; }
        public Builder fileUrl(String v)  { this.fileUrl = v;  return this; }
        public Builder data(Object v)     { this.data = v;     return this; }

        public Part build() { return new Part(this); }
    }
}

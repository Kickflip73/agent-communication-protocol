package dev.acp.relay;

import java.util.*;

/**
 * Minimal zero-dependency JSON serialiser/parser used internally by the SDK.
 *
 * <p>This is intentionally small: it only handles the subset of JSON needed by
 * the ACP relay API (objects, arrays, strings, numbers, booleans, null).
 * It is <em>not</em> a general-purpose JSON library.
 *
 * <p>Internal use only — not part of the public API.
 */
final class Json {

    private Json() {}

    // ── Serialisation ─────────────────────────────────────────────────────

    static String toJson(Object value) {
        if (value == null)                  return "null";
        if (value instanceof Boolean)       return value.toString();
        if (value instanceof Number)        return value.toString();
        if (value instanceof String)        return quoteString((String) value);
        if (value instanceof Map<?,?>)      return mapToJson((Map<?,?>) value);
        if (value instanceof List<?>)       return listToJson((List<?>) value);
        if (value instanceof Object[])      return listToJson(Arrays.asList((Object[]) value));
        // Fallback: treat as string
        return quoteString(value.toString());
    }

    private static String quoteString(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"':  sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\b': sb.append("\\b");  break;
                case '\f': sb.append("\\f");  break;
                case '\n': sb.append("\\n");  break;
                case '\r': sb.append("\\r");  break;
                case '\t': sb.append("\\t");  break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else          sb.append(c);
            }
        }
        sb.append('"');
        return sb.toString();
    }

    private static String mapToJson(Map<?,?> map) {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<?,?> e : map.entrySet()) {
            if (e.getValue() == null) continue;   // skip null values (omitempty)
            if (!first) sb.append(',');
            sb.append(quoteString(e.getKey().toString()));
            sb.append(':');
            sb.append(toJson(e.getValue()));
            first = false;
        }
        sb.append('}');
        return sb.toString();
    }

    private static String listToJson(List<?> list) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < list.size(); i++) {
            if (i > 0) sb.append(',');
            sb.append(toJson(list.get(i)));
        }
        sb.append(']');
        return sb.toString();
    }

    // ── Deserialisation ───────────────────────────────────────────────────

    /** Parse a JSON string into a nested structure of Map/List/String/Number/Boolean/null. */
    @SuppressWarnings("unchecked")
    static Map<String, Object> parseObject(String json) {
        Object parsed = new Parser(json).parseValue();
        if (!(parsed instanceof Map)) {
            throw new AcpException("Expected JSON object, got: " + json);
        }
        return (Map<String, Object>) parsed;
    }

    @SuppressWarnings("unchecked")
    static List<Object> parseArray(String json) {
        Object parsed = new Parser(json).parseValue();
        if (!(parsed instanceof List)) {
            throw new AcpException("Expected JSON array, got: " + json);
        }
        return (List<Object>) parsed;
    }

    // ── Type helpers ──────────────────────────────────────────────────────

    static String str(Map<String, Object> m, String key) {
        Object v = m.get(key);
        return v == null ? null : v.toString();
    }

    static long lng(Map<String, Object> m, String key) {
        Object v = m.get(key);
        if (v == null) return 0L;
        if (v instanceof Number) return ((Number) v).longValue();
        try { return Long.parseLong(v.toString()); } catch (NumberFormatException e) { return 0L; }
    }

    static int integer(Map<String, Object> m, String key) {
        Object v = m.get(key);
        if (v == null) return 0;
        if (v instanceof Number) return ((Number) v).intValue();
        try { return Integer.parseInt(v.toString()); } catch (NumberFormatException e) { return 0; }
    }

    static boolean bool(Map<String, Object> m, String key) {
        Object v = m.get(key);
        if (v == null) return false;
        if (v instanceof Boolean) return (Boolean) v;
        return "true".equalsIgnoreCase(v.toString());
    }

    @SuppressWarnings("unchecked")
    static List<Object> list(Map<String, Object> m, String key) {
        Object v = m.get(key);
        if (v instanceof List) return (List<Object>) v;
        return Collections.emptyList();
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> obj(Map<String, Object> m, String key) {
        Object v = m.get(key);
        if (v instanceof Map) return (Map<String, Object>) v;
        return Collections.emptyMap();
    }

    // ── Recursive descent parser ──────────────────────────────────────────

    private static final class Parser {
        private final String src;
        private int pos;

        Parser(String src) {
            this.src = src.trim();
            this.pos = 0;
        }

        Object parseValue() {
            skipWs();
            if (pos >= src.length()) throw new AcpException("Unexpected end of JSON");
            char c = src.charAt(pos);
            if (c == '{')         return parseObject();
            if (c == '[')         return parseArray();
            if (c == '"')         return parseString();
            if (c == 't')         return parseLiteral("true",  Boolean.TRUE);
            if (c == 'f')         return parseLiteral("false", Boolean.FALSE);
            if (c == 'n')         return parseLiteral("null",  null);
            if (c == '-' || Character.isDigit(c)) return parseNumber();
            throw new AcpException("Unexpected char '" + c + "' at pos " + pos);
        }

        private Map<String, Object> parseObject() {
            expect('{');
            Map<String, Object> map = new LinkedHashMap<>();
            skipWs();
            if (peek() == '}') { pos++; return map; }
            while (true) {
                skipWs();
                String key = parseString();
                skipWs();
                expect(':');
                skipWs();
                Object val = parseValue();
                map.put(key, val);
                skipWs();
                char next = peek();
                if (next == '}') { pos++; break; }
                if (next == ',') { pos++; continue; }
                throw new AcpException("Expected ',' or '}' at pos " + pos);
            }
            return map;
        }

        private List<Object> parseArray() {
            expect('[');
            List<Object> list = new ArrayList<>();
            skipWs();
            if (peek() == ']') { pos++; return list; }
            while (true) {
                skipWs();
                list.add(parseValue());
                skipWs();
                char next = peek();
                if (next == ']') { pos++; break; }
                if (next == ',') { pos++; continue; }
                throw new AcpException("Expected ',' or ']' at pos " + pos);
            }
            return list;
        }

        private String parseString() {
            expect('"');
            StringBuilder sb = new StringBuilder();
            while (pos < src.length()) {
                char c = src.charAt(pos++);
                if (c == '"') return sb.toString();
                if (c == '\\') {
                    char esc = src.charAt(pos++);
                    switch (esc) {
                        case '"':  sb.append('"');  break;
                        case '\\': sb.append('\\'); break;
                        case '/':  sb.append('/');  break;
                        case 'b':  sb.append('\b'); break;
                        case 'f':  sb.append('\f'); break;
                        case 'n':  sb.append('\n'); break;
                        case 'r':  sb.append('\r'); break;
                        case 't':  sb.append('\t'); break;
                        case 'u':
                            String hex = src.substring(pos, pos + 4); pos += 4;
                            sb.append((char) Integer.parseInt(hex, 16));
                            break;
                        default: sb.append(esc);
                    }
                } else {
                    sb.append(c);
                }
            }
            throw new AcpException("Unterminated string");
        }

        private Number parseNumber() {
            int start = pos;
            if (peek() == '-') pos++;
            while (pos < src.length() && (Character.isDigit(src.charAt(pos)) || src.charAt(pos) == '.'
                    || src.charAt(pos) == 'e' || src.charAt(pos) == 'E'
                    || src.charAt(pos) == '+' || src.charAt(pos) == '-')) {
                pos++;
            }
            String num = src.substring(start, pos);
            if (num.contains(".") || num.contains("e") || num.contains("E")) {
                return Double.parseDouble(num);
            }
            // Use long to avoid int overflow on large timestamps
            return Long.parseLong(num);
        }

        private Object parseLiteral(String literal, Object value) {
            if (src.startsWith(literal, pos)) {
                pos += literal.length();
                return value;
            }
            throw new AcpException("Expected '" + literal + "' at pos " + pos);
        }

        private void skipWs() {
            while (pos < src.length() && Character.isWhitespace(src.charAt(pos))) pos++;
        }

        private char peek() {
            return pos < src.length() ? src.charAt(pos) : 0;
        }

        private void expect(char c) {
            if (pos >= src.length() || src.charAt(pos) != c) {
                throw new AcpException("Expected '" + c + "' at pos " + pos
                        + ", got '" + (pos < src.length() ? src.charAt(pos) : "EOF") + "'");
            }
            pos++;
        }
    }
}

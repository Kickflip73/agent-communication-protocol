package dev.acp.relay;

import org.junit.jupiter.api.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Unit tests for the internal JSON serialiser/parser.
 * These run without any relay instance.
 */
class JsonTest {

    // ── Serialisation ────────────────────────────────────────────────────

    @Test void serializeString() {
        assertEquals("\"hello\"", Json.toJson("hello"));
    }

    @Test void serializeStringEscapes() {
        assertEquals("\"a\\\"b\\nc\"", Json.toJson("a\"b\nc"));
    }

    @Test void serializeNumber() {
        assertEquals("42",   Json.toJson(42));
        assertEquals("3.14", Json.toJson(3.14));
    }

    @Test void serializeBoolean() {
        assertEquals("true",  Json.toJson(true));
        assertEquals("false", Json.toJson(false));
    }

    @Test void serializeNull() {
        assertEquals("null", Json.toJson(null));
    }

    @Test void serializeEmptyMap() {
        assertEquals("{}", Json.toJson(new LinkedHashMap<>()));
    }

    @Test void serializeMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("role", "user");
        m.put("text", "hi");
        assertEquals("{\"role\":\"user\",\"text\":\"hi\"}", Json.toJson(m));
    }

    @Test void serializeMapSkipsNullValues() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("a", "yes");
        m.put("b", null);  // should be omitted
        assertEquals("{\"a\":\"yes\"}", Json.toJson(m));
    }

    @Test void serializeList() {
        List<Object> l = Arrays.asList("x", 1, true);
        assertEquals("[\"x\",1,true]", Json.toJson(l));
    }

    // ── Parsing ──────────────────────────────────────────────────────────

    @Test void parseSimpleObject() {
        Map<String, Object> m = Json.parseObject("{\"ok\":true,\"message_id\":\"msg_001\"}");
        assertEquals(Boolean.TRUE, m.get("ok"));
        assertEquals("msg_001", m.get("message_id"));
    }

    @Test void parseNestedObject() {
        String json = "{\"task\":{\"id\":\"t1\",\"status\":\"completed\"}}";
        Map<String, Object> m = Json.parseObject(json);
        @SuppressWarnings("unchecked")
        Map<String, Object> task = (Map<String, Object>) m.get("task");
        assertNotNull(task);
        assertEquals("t1",        task.get("id"));
        assertEquals("completed", task.get("status"));
    }

    @Test void parseArray() {
        List<Object> l = Json.parseArray("[\"a\",\"b\",\"c\"]");
        assertEquals(3, l.size());
        assertEquals("a", l.get(0));
        assertEquals("c", l.get(2));
    }

    @Test void parseObjectInArray() {
        String json = "[{\"type\":\"text\",\"text\":\"hello\"}]";
        List<Object> l = Json.parseArray(json);
        assertEquals(1, l.size());
        @SuppressWarnings("unchecked")
        Map<String, Object> part = (Map<String, Object>) l.get(0);
        assertEquals("text",  part.get("type"));
        assertEquals("hello", part.get("text"));
    }

    @Test void parseLongTimestamp() {
        Map<String, Object> m = Json.parseObject("{\"ts\":1711267200000}");
        assertEquals(1711267200000L, Json.lng(m, "ts"));
    }

    @Test void parseStringEscapes() {
        Map<String, Object> m = Json.parseObject("{\"s\":\"a\\\"b\\nc\"}");
        assertEquals("a\"b\nc", m.get("s"));
    }

    @Test void parseNullValue() {
        Map<String, Object> m = Json.parseObject("{\"task\":null}");
        assertNull(m.get("task"));
    }

    @Test void parseEmptyObject() {
        Map<String, Object> m = Json.parseObject("{}");
        assertTrue(m.isEmpty());
    }

    @Test void helperStr() {
        Map<String, Object> m = Map.of("k", "v");
        assertEquals("v", Json.str(m, "k"));
        assertNull(Json.str(m, "missing"));
    }

    @Test void helperBool() {
        Map<String, Object> m = Map.of("a", true, "b", false);
        assertTrue(Json.bool(m, "a"));
        assertFalse(Json.bool(m, "b"));
        assertFalse(Json.bool(m, "missing"));
    }

    @Test void helperLng() {
        Map<String, Object> m = Map.of("n", 12345L);
        assertEquals(12345L, Json.lng(m, "n"));
        assertEquals(0L,     Json.lng(m, "missing"));
    }

    // ── Round-trip ────────────────────────────────────────────────────────

    @Test void roundTripSendRequestBody() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("role", "user");
        body.put("text", "Hello, world!");
        body.put("message_id", "idem-001");

        String json = Json.toJson(body);
        Map<String, Object> parsed = Json.parseObject(json);

        assertEquals("user",         parsed.get("role"));
        assertEquals("Hello, world!", parsed.get("text"));
        assertEquals("idem-001",     parsed.get("message_id"));
    }
}

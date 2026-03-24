package dev.acp.relay;
import java.util.*;

/**
 * Standalone smoke test for ACP Java SDK (no JUnit, no relay needed).
 * Exercises: Json, Part, Message, Task, SendRequest, AcpException
 */
public class AcpJavaSmokeTest {
    static int pass = 0, fail = 0;

    static void check(String name, boolean cond) {
        if (cond) { System.out.println("  ✅ " + name); pass++; }
        else       { System.out.println("  ❌ FAIL: " + name); fail++; }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("=== ACP Java SDK Smoke Tests ===\n");

        // ── Json ──────────────────────────────────────────────────────────
        System.out.println("[Json]");
        check("toJson string",    "\"hello\"".equals(Json.toJson("hello")));
        check("toJson number",    "42".equals(Json.toJson(42)));
        check("toJson bool",      "true".equals(Json.toJson(true)));
        check("toJson null",      "null".equals(Json.toJson(null)));
        check("toJson list",      "[\"a\",\"b\"]".equals(Json.toJson(Arrays.asList("a","b"))));
        Map<String,Object> m = new LinkedHashMap<>();
        m.put("k","v"); m.put("n",1);
        check("toJson map",       "{\"k\":\"v\",\"n\":1}".equals(Json.toJson(m)));
        check("toJson escape",    "\"a\\\"b\\nc\"".equals(Json.toJson("a\"b\nc")));

        // parse
        Map<String,Object> parsed = Json.parseObject("{\"role\":\"user\",\"x\":42}");
        check("parseObject str",  "user".equals(Json.str(parsed,"role")));
        check("parseObject num",  42L == Json.lng(parsed,"x"));
        List<Object> arr = Json.parseArray("[1,2,3]");
        check("parseArray len",   arr.size() == 3);
        check("parseArray val",   1L == ((Number)arr.get(0)).longValue());

        // ── Part ──────────────────────────────────────────────────────────
        System.out.println("\n[Part]");
        Part tp = Part.text("hello");
        check("text type",        "text".equals(tp.getType()));
        check("text getText",     "hello".equals(tp.getText()));
        Part dp = Part.data(Collections.singletonMap("k","v"));
        check("data type",        "data".equals(dp.getType()));
        check("data getData",     dp.getData() != null);
        Part bp = new Part.Builder("file").fileUrl("s3://bucket/f").build();
        check("builder fileUrl",  "s3://bucket/f".equals(bp.getFileUrl()));

        // ── Message ───────────────────────────────────────────────────────
        System.out.println("\n[Message]");
        List<Part> parts = Collections.singletonList(Part.text("hi"));
        Message msg = new Message("acp.message","msg-1",1234567890L,"peerA","user",parts,null,null);
        check("msg id",           "msg-1".equals(msg.getMessageId()));
        check("msg role",         "user".equals(msg.getRole()));
        check("msg firstText",    "hi".equals(msg.firstText()));
        check("msg from",         "peerA".equals(msg.getFrom()));

        // ── Task ──────────────────────────────────────────────────────────
        System.out.println("\n[Task]");
        Task done = new Task("t1","completed",100L,200L,"msg-1");
        check("task id",          "t1".equals(done.getId()));
        check("task isTerminal",  done.isTerminal());
        Task running = new Task("t2","working",100L,200L,"msg-2");
        check("task not terminal",!running.isTerminal());
        Task failed = new Task("t3","failed",100L,200L,"msg-3");
        check("failed isTerminal",failed.isTerminal());

        // ── SendRequest ───────────────────────────────────────────────────
        System.out.println("\n[SendRequest]");
        SendRequest u = SendRequest.user("hello user");
        check("user role",        "user".equals(u.getRole()));
        check("user text",        "hello user".equals(u.getText()));
        SendRequest a = SendRequest.agent("agent reply");
        check("agent role",       "agent".equals(a.getRole()));
        SendRequest withId = u.withMessageId("mid-99");
        check("withMessageId",    "mid-99".equals(withId.getMessageId()));
        SendRequest withCtx = u.withContextId("ctx-1");
        check("withContextId",    "ctx-1".equals(withCtx.getContextId()));

        // ── AcpException ──────────────────────────────────────────────────
        System.out.println("\n[AcpException]");
        AcpException ex1 = new AcpException("something failed");
        check("ex1 msg",          "something failed".equals(ex1.getMessage()));
        AcpException ex2 = new AcpException(503, "SERVICE_UNAVAILABLE", "upstream error");
        check("ex2 status",       503 == ex2.getHttpStatus());
        check("ex2 code",         "SERVICE_UNAVAILABLE".equals(ex2.getErrorCode()));
        check("ex2 msg",          ex2.getMessage().contains("upstream error"));
        check("ex2 instanceof",   ex2 instanceof RuntimeException);

        // ── Summary ───────────────────────────────────────────────────────
        int total = pass + fail;
        System.out.println("\n" + "=".repeat(45));
        System.out.printf("Java SDK smoke: %d/%d PASS%n", pass, total);
        if (fail > 0) { System.out.println("FAILURES: " + fail); System.exit(1); }
    }
}

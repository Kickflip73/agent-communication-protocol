# acp-relay-client (Java)

Java SDK for the [Agent Communication Protocol (ACP)](../../README.md) relay.

**Version:** 1.0.0 | **Zero external dependencies** | **JDK 11+** | **Apache-2.0**

---

## Installation

### Maven

```xml
<dependency>
    <groupId>dev.acp</groupId>
    <artifactId>acp-relay-client</artifactId>
    <version>1.0.0</version>
</dependency>
```

### Gradle

```groovy
implementation 'dev.acp:acp-relay-client:1.0.0'
```

### Manual (copy source)

The SDK is a single package (`dev.acp.relay`) with **zero runtime dependencies**.
You can copy `src/main/java/dev/acp/relay/` directly into your project if you prefer no build tool dependency.

---

## Quick Start

```java
import dev.acp.relay.*;

// 1. Start acp_relay.py on your machine:
//    python3 acp_relay.py --name MyAgent --http-port 7901
//
// 2. Create a client
RelayClient client = RelayClient.of("http://localhost:7901");

// 3. Health check
System.out.println(client.ping()); // true

// 4. Get your session link (share this with the other agent)
String link = client.link();
System.out.println(link); // acp://relay.acp.dev/<session-id>

// 5. Connect to another agent
String peerId = client.connectPeer("acp://relay.acp.dev/their-session-id");

// 6. Send a message
SendResponse resp = client.send(SendRequest.user("Hello from Java!"));
System.out.println(resp.getMessageId()); // msg_...

// 7. Poll for replies
List<Message> msgs = client.recv();
msgs.forEach(m -> System.out.println("[" + m.getRole() + "] " + m.firstText()));
```

---

## API Reference

### `RelayClient`

Create with `RelayClient.of(baseUrl)` or `RelayClient.of(baseUrl, httpClient)` for custom HTTP config.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `ping()` | `GET /.well-known/acp.json` | Reachability check |
| `agentCard()` | `GET /.well-known/acp.json` | Full AgentCard (self + peer) |
| `link()` | `GET /link` | Your session link (`acp://…`) |
| `status()` | `GET /status` | Relay runtime status |
| `send(SendRequest)` | `POST /message:send` | Send message to connected peer |
| `recv()` | `GET /recv` | Poll received messages |
| `recv(limit, since)` | `GET /recv?limit=&since=` | Poll with cursor |
| `connectPeer(acpLink)` | `POST /peers/connect` | Connect to a peer via acp:// link |
| `sendToPeer(peerId, req)` | `POST /peer/{id}/send` | Send to a specific peer |
| `peers()` | `GET /peers` | List connected peers |
| `getTasks()` | `GET /tasks` | List all tasks |
| `cancelTask(id)` | `POST /tasks/{id}:cancel` | Cancel a task |
| `querySkills(filter)` | `POST /skills/query` | Query peer capabilities |
| `patchAvailability(map)` | `PATCH /.well-known/acp.json` | Update availability metadata |
| `stream(handler)` | `GET /stream` (SSE) | Subscribe to event stream (blocking) |

---

### `SendRequest`

```java
// Convenience factories
SendRequest.user("Hello!")              // role="user"
SendRequest.agent("Task complete.")     // role="agent"

// Full builder
new SendRequest.Builder("agent")
    .text("result ready")
    .messageId("my-idempotency-key")    // for deduplication
    .taskId("task_001")                  // link to existing task
    .contextId("conv_001")               // group related messages
    .sync(true).timeout(30)              // wait for task completion
    .build();

// Fluent copy methods (return new instance, original unchanged)
req.withMessageId("idem-001")
req.withTaskId("task_001")
req.withContextId("conv_001")
req.sync(30)
```

### `Part` — message content units

```java
Part.text("Hello, world!")                          // type="text"
Part.file("https://example.com/file.pdf", "application/pdf") // type="file"
Part.data(myObject)                                  // type="data" (serialized as JSON)

// Multi-part message
new SendRequest.Builder("agent")
    .parts(Part.text("See attached"), Part.file("https://…/doc.pdf", null))
    .build();
```

### `Message` (received messages)

```java
message.getType()        // "message"
message.getMessageId()   // "msg_..."
message.getTs()          // Unix timestamp (ms)
message.getRole()        // "user" | "agent"
message.getParts()       // List<Part>
message.firstText()      // convenience: first text part, or null
message.getTaskId()      // linked task id, or null
```

### SSE Streaming

```java
// Runs on the calling thread — use a dedicated thread or virtual thread (JDK 21+)
new Thread(() ->
    client.stream(event -> {
        System.out.println(event.getType() + ": " + event.getData());
        // event types: "acp.message", "acp.artifact", "acp.status"
    })
).start();
```

### Heartbeat / Cron Agents

```java
// Called on every wake to advertise availability
Map<String, Object> avail = new LinkedHashMap<>();
avail.put("mode",           "cron");
avail.put("last_active_at", "2026-03-24T10:00:00Z");
avail.put("next_active_at", "2026-03-24T11:00:00Z");
avail.put("task_latency_max_seconds", 3600);
client.patchAvailability(avail);
```

### Error Handling

```java
try {
    client.send(SendRequest.user("hello"));
} catch (AcpException e) {
    System.err.println("HTTP status: " + e.getHttpStatus());   // 400, 404, 503, etc.
    System.err.println("ACP code:    " + e.getErrorCode());    // "ERR_NOT_FOUND", etc.
    System.err.println("Message:     " + e.getMessage());
}
```

---

## Multi-peer (Orchestrator pattern)

```java
RelayClient orchestrator = RelayClient.of("http://localhost:7901");

String worker1Link = "acp://relay.acp.dev/worker1-session";
String worker2Link = "acp://relay.acp.dev/worker2-session";

String peer1 = orchestrator.connectPeer(worker1Link);
String peer2 = orchestrator.connectPeer(worker2Link);

// Must use sendToPeer() when multiple peers are connected
orchestrator.sendToPeer(peer1, SendRequest.agent("Process part A"));
orchestrator.sendToPeer(peer2, SendRequest.agent("Process part B"));
```

---

## Spring Boot Integration

```java
@Configuration
public class AcpConfig {
    @Bean
    public RelayClient relayClient(@Value("${acp.relay.url}") String url) {
        return RelayClient.of(url);
    }
}

@Service
public class AgentService {
    private final RelayClient relay;

    public AgentService(RelayClient relay) {
        this.relay = relay;
    }

    public void processIncoming() {
        relay.recv().forEach(msg -> {
            String text = msg.firstText();
            if (text != null) {
                // handle message
                relay.send(SendRequest.agent("Received: " + text));
            }
        });
    }
}
```

---

## Building & Testing

```bash
# Compile + run all tests (unit tests always run; integration tests need a relay)
mvn test

# Build jar
mvn package -DskipTests

# Run only unit tests
mvn test -Dtest=JsonTest

# Run integration tests (relay must be running on 7951/7952)
mvn test -Dtest=RelayClientTest
```

---

## Links

- [Protocol spec](../../spec/core-v1.0.md)
- [Python SDK](../python/)
- [Go SDK](../go/)
- [Node.js SDK](../node/)
- [Rust SDK](../rust/)
- [Integration guide](../../docs/integration-guide.md)

---

## License

Apache-2.0 © ACP Contributors

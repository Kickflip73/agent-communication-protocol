# acp-relay-client (Go)

Go SDK stub for the [ACP Relay](https://github.com/Kickflip73/agent-communication-protocol) HTTP API.

> **Status:** Stub / Preview — API surface is stable; production hardening in progress.

## Install

```bash
go get github.com/Kickflip73/agent-communication-protocol/sdk/go@latest
```

> Requires Go 1.21+. No external dependencies — stdlib only.

## Quick Start

```go
package main

import (
    "context"
    "fmt"
    "log"

    "github.com/Kickflip73/agent-communication-protocol/sdk/go/acprelay"
)

func main() {
    client := acprelay.New("http://localhost:7901")
    ctx := context.Background()

    // Send a message
    resp, err := client.Send(ctx, acprelay.SendRequest{
        Role: "user",
        Text: "Hello from Go!",
    })
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println("sent:", resp.MessageID)

    // Poll for replies
    msgs, err := client.Recv(ctx, acprelay.RecvOptions{Limit: 10})
    if err != nil {
        log.Fatal(err)
    }
    for _, m := range msgs.Messages {
        fmt.Printf("[%s] %s\n", m.Role, m.Parts[0].Text)
    }
}
```

## API Reference

| Method | Endpoint | Stability |
|--------|----------|-----------|
| `Send(ctx, SendRequest)` | `POST /message:send` | stable |
| `Recv(ctx, RecvOptions)` | `GET /recv` | stable |
| `GetStatus(ctx)` | `GET /status` | stable |
| `GetTasks(ctx)` | `GET /tasks` | stable |
| `CancelTask(ctx, id)` | `POST /tasks/{id}:cancel` | stable |
| `QuerySkills(ctx, opts)` | `POST /skills/query` | stable |

## Running Tests

```bash
cd sdk/go
go test ./acprelay/... -v
```

## See Also

- [Python SDK](../python/)
- [Node.js SDK](../node/)
- [ACP Core Spec v1.0](../../spec/core-v1.0.md)
- [Security Model](../../docs/security.md)

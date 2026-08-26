package acprelay

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// SSEEvent is a single Server-Sent Event received from GET /stream. [stable]
//
// ACP emits three event types (spec §8.3):
//   - "status"   — task state transition  (data: {"type":"acp.task.status", ...})
//   - "artifact" — streamed output chunk  (data: {"type":"acp.task.artifact", ...})
//   - "message"  — inbound message        (data: {"type":"acp.message", ...})
type SSEEvent struct {
	// ID is the optional SSE event id field (may be empty).
	ID string
	// Type is the SSE event type field (e.g. "status", "artifact", "message").
	// Defaults to "message" if absent per SSE spec.
	Type string
	// Data is the raw JSON payload of the event.
	Data string
	// Parsed is the decoded JSON payload. Nil if Data is empty or not valid JSON.
	Parsed map[string]any
}

// StreamOptions controls the GET /stream request.
type StreamOptions struct {
	// Timeout is the maximum duration to keep the stream open.
	// Zero means no timeout (stream until context is cancelled).
	Timeout time.Duration
}

// Stream subscribes to the SSE event stream at GET /stream. [stable]
//
// It returns a channel that emits *SSEEvent values. The channel is closed
// when the stream ends (server EOF, timeout, or context cancellation).
// Any transport error is sent as an SSEEvent with Type="error" and Data=err.Error().
//
// Usage:
//
//	events, err := client.Stream(ctx, acprelay.StreamOptions{Timeout: 30 * time.Second})
//	if err != nil { ... }
//	for ev := range events {
//	    if ev.Type == "error" { break }
//	    fmt.Println(ev.Type, ev.Data)
//	}
func (c *Client) Stream(ctx context.Context, opts StreamOptions) (<-chan *SSEEvent, error) {
	streamURL := c.baseURL + "/stream"

	reqCtx := ctx
	if opts.Timeout > 0 {
		var cancel context.CancelFunc
		reqCtx, cancel = context.WithTimeout(ctx, opts.Timeout)
		// cancel is called inside the goroutine when the loop exits
		_ = cancel
		reqCtx, cancel = context.WithTimeout(ctx, opts.Timeout)
		ch := make(chan *SSEEvent, 32)
		go func() {
			defer cancel()
			defer close(ch)
			streamLoop(reqCtx, c.httpClient, streamURL, ch)
		}()
		return ch, nil
	}

	ch := make(chan *SSEEvent, 32)
	go func() {
		defer close(ch)
		streamLoop(reqCtx, c.httpClient, streamURL, ch)
	}()
	return ch, nil
}

// streamLoop runs the SSE read loop and sends events to ch.
func streamLoop(ctx context.Context, hc *http.Client, url string, ch chan<- *SSEEvent) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		sendErr(ch, fmt.Errorf("acprelay/stream: build request: %w", err))
		return
	}
	req.Header.Set("Accept", "text/event-stream")
	req.Header.Set("Cache-Control", "no-cache")

	resp, err := hc.Do(req)
	if err != nil {
		sendErr(ch, fmt.Errorf("acprelay/stream: connect: %w", err))
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		sendErr(ch, fmt.Errorf("acprelay/stream: server returned %d", resp.StatusCode))
		return
	}

	// SSE parser — accumulates lines per event block
	scanner := bufio.NewScanner(resp.Body)
	var (
		evID   string
		evType string
		evData strings.Builder
	)

	flush := func() {
		data := strings.TrimSuffix(evData.String(), "\n")
		if data == "" && evType == "" && evID == "" {
			return
		}
		ev := &SSEEvent{
			ID:   evID,
			Type: evType,
			Data: data,
		}
		if ev.Type == "" {
			ev.Type = "message" // SSE default
		}
		if data != "" {
			var parsed map[string]any
			if json.Unmarshal([]byte(data), &parsed) == nil {
				ev.Parsed = parsed
			}
		}
		select {
		case ch <- ev:
		case <-ctx.Done():
			return
		}
		// reset
		evID = ""
		evType = ""
		evData.Reset()
	}

	for scanner.Scan() {
		select {
		case <-ctx.Done():
			return
		default:
		}

		line := scanner.Text()

		switch {
		case line == "":
			// blank line = dispatch event
			flush()
		case strings.HasPrefix(line, "id:"):
			evID = strings.TrimSpace(strings.TrimPrefix(line, "id:"))
		case strings.HasPrefix(line, "event:"):
			evType = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
		case strings.HasPrefix(line, "data:"):
			evData.WriteString(strings.TrimSpace(strings.TrimPrefix(line, "data:")))
			evData.WriteString("\n")
		case strings.HasPrefix(line, ":"):
			// SSE comment — ignore
		}
	}

	if err := scanner.Err(); err != nil && ctx.Err() == nil {
		sendErr(ch, fmt.Errorf("acprelay/stream: read: %w", err))
	}
}

func sendErr(ch chan<- *SSEEvent, err error) {
	select {
	case ch <- &SSEEvent{Type: "error", Data: err.Error()}:
	default:
	}
}

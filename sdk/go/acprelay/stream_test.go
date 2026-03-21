package acprelay_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Kickflip73/agent-communication-protocol/sdk/go/acprelay"
)

// sseServer returns a test server that streams the given SSE payload then closes.
func sseServer(t *testing.T, payload string) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, payload)
		if f, ok := w.(http.Flusher); ok {
			f.Flush()
		}
	}))
}

// ── Stream basic ──────────────────────────────────────────────────────────

func TestStream_SingleEvent(t *testing.T) {
	srv := sseServer(t, "event: status\ndata: {\"type\":\"acp.task.status\",\"status\":\"completed\"}\n\n")
	defer srv.Close()

	c := acprelay.New(srv.URL)
	ch, err := c.Stream(context.Background(), acprelay.StreamOptions{Timeout: 2 * time.Second})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var events []*acprelay.SSEEvent
	for ev := range ch {
		events = append(events, ev)
	}

	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	if events[0].Type != "status" {
		t.Errorf("Type = %q, want %q", events[0].Type, "status")
	}
	if events[0].Parsed == nil {
		t.Error("Parsed should not be nil for valid JSON data")
	}
	if events[0].Parsed["status"] != "completed" {
		t.Errorf("Parsed[status] = %v", events[0].Parsed["status"])
	}
}

func TestStream_MultipleEvents(t *testing.T) {
	payload := "" +
		"event: message\ndata: {\"type\":\"acp.message\",\"role\":\"agent\"}\n\n" +
		"event: artifact\ndata: {\"type\":\"acp.task.artifact\",\"chunk\":\"hello\"}\n\n" +
		"event: status\ndata: {\"type\":\"acp.task.status\",\"status\":\"completed\"}\n\n"

	srv := sseServer(t, payload)
	defer srv.Close()

	c := acprelay.New(srv.URL)
	ch, err := c.Stream(context.Background(), acprelay.StreamOptions{Timeout: 2 * time.Second})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var events []*acprelay.SSEEvent
	for ev := range ch {
		if ev.Type == "error" {
			t.Fatalf("unexpected error event: %s", ev.Data)
		}
		events = append(events, ev)
	}

	if len(events) != 3 {
		t.Fatalf("expected 3 events, got %d", len(events))
	}
	types := []string{events[0].Type, events[1].Type, events[2].Type}
	want := []string{"message", "artifact", "status"}
	for i := range want {
		if types[i] != want[i] {
			t.Errorf("events[%d].Type = %q, want %q", i, types[i], want[i])
		}
	}
}

func TestStream_DefaultEventType(t *testing.T) {
	// No "event:" field → type should default to "message"
	srv := sseServer(t, "data: {\"hello\":\"world\"}\n\n")
	defer srv.Close()

	c := acprelay.New(srv.URL)
	ch, err := c.Stream(context.Background(), acprelay.StreamOptions{Timeout: 2 * time.Second})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	events := collect(ch)
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	if events[0].Type != "message" {
		t.Errorf("Type = %q, want %q (SSE default)", events[0].Type, "message")
	}
}

func TestStream_EventWithID(t *testing.T) {
	srv := sseServer(t, "id: evt_001\nevent: status\ndata: {}\n\n")
	defer srv.Close()

	c := acprelay.New(srv.URL)
	ch, _ := c.Stream(context.Background(), acprelay.StreamOptions{Timeout: 2 * time.Second})
	events := collect(ch)

	if len(events) < 1 {
		t.Fatal("expected at least 1 event")
	}
	if events[0].ID != "evt_001" {
		t.Errorf("ID = %q, want %q", events[0].ID, "evt_001")
	}
}

func TestStream_SSEComment_Ignored(t *testing.T) {
	// Comment lines (: ...) must be ignored; only real event dispatched
	payload := ": this is a comment\nevent: status\ndata: {\"ok\":true}\n\n"
	srv := sseServer(t, payload)
	defer srv.Close()

	c := acprelay.New(srv.URL)
	ch, _ := c.Stream(context.Background(), acprelay.StreamOptions{Timeout: 2 * time.Second})
	events := collect(ch)

	if len(events) != 1 {
		t.Fatalf("expected 1 event (comment ignored), got %d", len(events))
	}
	if events[0].Type != "status" {
		t.Errorf("Type = %q, want status", events[0].Type)
	}
}

func TestStream_NonJSONData(t *testing.T) {
	// Non-JSON data: Parsed should be nil, Data should contain raw string
	srv := sseServer(t, "event: ping\ndata: keep-alive\n\n")
	defer srv.Close()

	c := acprelay.New(srv.URL)
	ch, _ := c.Stream(context.Background(), acprelay.StreamOptions{Timeout: 2 * time.Second})
	events := collect(ch)

	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	if events[0].Parsed != nil {
		t.Error("Parsed should be nil for non-JSON data")
	}
	if events[0].Data != "keep-alive" {
		t.Errorf("Data = %q", events[0].Data)
	}
}

func TestStream_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "relay not connected", 503)
	}))
	defer srv.Close()

	c := acprelay.New(srv.URL)
	ch, err := c.Stream(context.Background(), acprelay.StreamOptions{Timeout: 2 * time.Second})
	if err != nil {
		t.Fatalf("Stream() itself should not error; error propagated via channel")
	}

	var gotError bool
	for ev := range ch {
		if ev.Type == "error" {
			gotError = true
		}
	}
	if !gotError {
		t.Error("expected error event for 503 response")
	}
}

func TestStream_ContextCancel(t *testing.T) {
	// Server streams forever; context cancel should terminate the channel
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(200)
		flusher := w.(http.Flusher)
		for {
			select {
			case <-r.Context().Done():
				return
			default:
				fmt.Fprint(w, ": heartbeat\n\n")
				flusher.Flush()
				time.Sleep(10 * time.Millisecond)
			}
		}
	}))
	defer srv.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	c := acprelay.New(srv.URL)
	ch, err := c.Stream(ctx, acprelay.StreamOptions{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Drain until closed
	for range ch {
	}
	// If we get here within the test timeout, context cancel works
}

// ── helper ────────────────────────────────────────────────────────────────

func collect(ch <-chan *acprelay.SSEEvent) []*acprelay.SSEEvent {
	var out []*acprelay.SSEEvent
	for ev := range ch {
		out = append(out, ev)
	}
	return out
}

package acprelay_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Kickflip73/agent-communication-protocol/sdk/go/acprelay"
)

// ── helpers ────────────────────────────────────────────────────────────────

func jsonServer(t *testing.T, handler func(w http.ResponseWriter, r *http.Request)) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(handler))
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// ── New / construction ─────────────────────────────────────────────────────

func TestNew(t *testing.T) {
	c := acprelay.New("http://localhost:7901")
	if c == nil {
		t.Fatal("New returned nil")
	}
}

func TestNewWithHTTPClient(t *testing.T) {
	c := acprelay.NewWithHTTPClient("http://localhost:7901", &http.Client{})
	if c == nil {
		t.Fatal("NewWithHTTPClient returned nil")
	}
}

// ── GetStatus ──────────────────────────────────────────────────────────────

func TestGetStatus_OK(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/status" || r.Method != http.MethodGet {
			http.Error(w, "wrong path/method", 400)
			return
		}
		writeJSON(w, map[string]any{
			"state":      "connected",
			"session_id": "sess_abc123",
			"link":       "acp://relay.test/sess_abc123",
			"agent_name": "TestAgent",
		})
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	st, err := c.GetStatus(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if st.State != "connected" {
		t.Errorf("State = %q, want %q", st.State, "connected")
	}
	if st.SessionID != "sess_abc123" {
		t.Errorf("SessionID = %q", st.SessionID)
	}
}

func TestGetStatus_ServerError(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal error", 500)
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	_, err := c.GetStatus(context.Background())
	if err == nil {
		t.Fatal("expected error, got nil")
	}
}

// ── Send ──────────────────────────────────────────────────────────────────

func TestSend_TextShorthand(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/message:send" || r.Method != http.MethodPost {
			http.Error(w, "wrong path/method", 400)
			return
		}
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["role"] != "user" {
			http.Error(w, "role missing", 400)
			return
		}
		writeJSON(w, map[string]any{
			"ok":         true,
			"message_id": "msg_test001",
		})
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	resp, err := c.Send(context.Background(), acprelay.SendRequest{
		Role: "user",
		Text: "Hello from Go!",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !resp.OK {
		t.Errorf("expected ok=true")
	}
	if resp.MessageID != "msg_test001" {
		t.Errorf("MessageID = %q", resp.MessageID)
	}
}

func TestSend_WithParts(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		parts, ok := body["parts"].([]any)
		if !ok || len(parts) == 0 {
			http.Error(w, "parts missing", 400)
			return
		}
		writeJSON(w, map[string]any{"ok": true, "message_id": "msg_parts01"})
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	resp, err := c.Send(context.Background(), acprelay.SendRequest{
		Role: "agent",
		Parts: []acprelay.Part{
			{Type: "text", Text: "part one"},
			{Type: "text", Text: "part two"},
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.MessageID != "msg_parts01" {
		t.Errorf("MessageID = %q", resp.MessageID)
	}
}

func TestSend_ServerReturnsError(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(400)
		writeJSON(w, map[string]any{"ok": false, "error": "role is required"})
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	_, err := c.Send(context.Background(), acprelay.SendRequest{})
	if err == nil {
		t.Fatal("expected error, got nil")
	}
}

// ── Recv ──────────────────────────────────────────────────────────────────

func TestRecv_Empty(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/recv" {
			http.Error(w, "wrong path", 400)
			return
		}
		writeJSON(w, map[string]any{"messages": []any{}, "count": 0})
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	resp, err := c.Recv(context.Background(), acprelay.RecvOptions{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Count != 0 || len(resp.Messages) != 0 {
		t.Errorf("expected empty, got count=%d", resp.Count)
	}
}

func TestRecv_WithMessages(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{
			"messages": []map[string]any{
				{
					"type":       "acp.message",
					"message_id": "msg_recv01",
					"ts":         1742558400000,
					"from":       "RemoteAgent",
					"role":       "agent",
					"parts":      []map[string]any{{"type": "text", "text": "Hi!"}},
				},
			},
			"count": 1,
		})
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	resp, err := c.Recv(context.Background(), acprelay.RecvOptions{Limit: 10})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Count != 1 || len(resp.Messages) != 1 {
		t.Fatalf("expected 1 message, got %d", resp.Count)
	}
	if resp.Messages[0].MessageID != "msg_recv01" {
		t.Errorf("MessageID = %q", resp.Messages[0].MessageID)
	}
}

// ── GetTasks ──────────────────────────────────────────────────────────────

func TestGetTasks_OK(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{
			"tasks": []map[string]any{
				{"id": "task_001", "status": "completed", "created_at": 1000, "updated_at": 2000},
			},
		})
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	tasks, err := c.GetTasks(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(tasks) != 1 || tasks[0].ID != "task_001" {
		t.Errorf("unexpected tasks: %+v", tasks)
	}
}

// ── CancelTask ────────────────────────────────────────────────────────────

func TestCancelTask_OK(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "wrong method", 405)
			return
		}
		writeJSON(w, map[string]any{"ok": true})
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	if err := c.CancelTask(context.Background(), "task_001"); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCancelTask_NotFound(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(404)
		writeJSON(w, map[string]any{"ok": false, "error": "task not found"})
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	err := c.CancelTask(context.Background(), "bad_id")
	if err == nil {
		t.Fatal("expected error, got nil")
	}
}

// ── QuerySkills ───────────────────────────────────────────────────────────

func TestQuerySkills_OK(t *testing.T) {
	srv := jsonServer(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/skills/query" || r.Method != http.MethodPost {
			http.Error(w, "wrong path/method", 400)
			return
		}
		writeJSON(w, map[string]any{
			"skills": []map[string]any{
				{"id": "skill_summarize", "name": "Summarize", "description": "Summarizes text"},
			},
			"count": 1,
		})
	})
	defer srv.Close()

	c := acprelay.New(srv.URL)
	resp, err := c.QuerySkills(context.Background(), nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Count != 1 || resp.Skills[0].ID != "skill_summarize" {
		t.Errorf("unexpected skills: %+v", resp.Skills)
	}
}

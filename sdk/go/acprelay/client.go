// Package acprelay provides a Go client for the ACP Relay HTTP API (v1.0).
//
// ACP (Agent Communication Protocol) enables peer-to-peer communication between
// AI agents via a lightweight relay. This package wraps the HTTP endpoints
// exposed by acp_relay.py.
//
// # Quick Start
//
//	client := acprelay.New("http://localhost:7901")
//
//	// Send a message
//	resp, err := client.Send(context.Background(), acprelay.SendRequest{
//	    Role: "user",
//	    Text: "Hello from Go!",
//	})
//
//	// Poll for received messages
//	msgs, err := client.Recv(context.Background(), acprelay.RecvOptions{})
//
// # Spec
//
// https://github.com/Kickflip73/agent-communication-protocol/blob/main/spec/core-v1.0.md
package acprelay

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

const defaultTimeout = 30 * time.Second

// Client is an ACP Relay HTTP client. Create one with [New].
type Client struct {
	baseURL    string
	httpClient *http.Client
}

// New creates a new Client pointing at baseURL (e.g. "http://localhost:7901").
func New(baseURL string) *Client {
	return &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: defaultTimeout,
		},
	}
}

// NewWithHTTPClient creates a Client using a custom *http.Client.
func NewWithHTTPClient(baseURL string, hc *http.Client) *Client {
	return &Client{baseURL: baseURL, httpClient: hc}
}

// ── Types ──────────────────────────────────────────────────────────────────

// Part represents a single content unit in a message (text, file, or data).
// Mirrors the ACP Part model defined in spec §3.2.
type Part struct {
	// Type is one of "text", "file", or "data". Required.
	Type string `json:"type"`

	// Text is the content for type="text".
	Text string `json:"text,omitempty"`

	// MimeType optionally qualifies the content type (e.g. "text/markdown").
	MimeType string `json:"mime_type,omitempty"`

	// Data holds arbitrary JSON for type="data".
	Data any `json:"data,omitempty"`

	// FileURL holds a URL or base64-encoded payload for type="file".
	FileURL string `json:"file_url,omitempty"`
}

// Message represents a message envelope returned by the relay (e.g. from /recv).
type Message struct {
	Type      string `json:"type"`
	MessageID string `json:"message_id"`
	Ts        int64  `json:"ts"`
	From      string `json:"from"`
	Role      string `json:"role"`
	Parts     []Part `json:"parts"`
	TaskID    string `json:"task_id,omitempty"`
	ContextID string `json:"context_id,omitempty"`
}

// Task represents an ACP task object (spec §5).
type Task struct {
	ID        string `json:"id"`
	Status    string `json:"status"` // submitted | working | completed | failed | input_required
	CreatedAt int64  `json:"created_at"`
	UpdatedAt int64  `json:"updated_at"`
	MessageID string `json:"message_id,omitempty"`
}

// Status is the response from GET /status.
type Status struct {
	State     string `json:"state"`
	SessionID string `json:"session_id,omitempty"`
	Link      string `json:"link,omitempty"`
	AgentName string `json:"agent_name,omitempty"`
}

// SendRequest is the payload for POST /message:send.
type SendRequest struct {
	// Role is required. Must be "user" or "agent" (validated server-side, v0.9+).
	Role string `json:"role"`

	// Parts is a list of content parts. Mutually exclusive with Text.
	Parts []Part `json:"parts,omitempty"`

	// Text is a convenience shorthand for a single text part. Mutually exclusive with Parts.
	Text string `json:"text,omitempty"`

	// MessageID is an optional client-generated idempotency key.
	MessageID string `json:"message_id,omitempty"`

	// TaskID links this message to an existing task.
	TaskID string `json:"task_id,omitempty"`

	// ContextID groups related messages into a logical conversation.
	ContextID string `json:"context_id,omitempty"`

	// Sync requests synchronous task completion (blocks until terminal state).
	Sync bool `json:"sync,omitempty"`

	// Timeout is the sync wait limit in seconds (default: relay-configured).
	Timeout int `json:"timeout,omitempty"`
}

// SendResponse is the response from POST /message:send.
type SendResponse struct {
	OK        bool    `json:"ok"`
	MessageID string  `json:"message_id,omitempty"`
	Task      *Task   `json:"task,omitempty"`
	Error     string  `json:"error,omitempty"`
}

// RecvOptions controls the GET /recv request.
type RecvOptions struct {
	// Limit is the maximum number of messages to return (default: server default).
	Limit int
	// Since returns only messages with ts > Since (Unix millis).
	Since int64
}

// RecvResponse is the response from GET /recv.
type RecvResponse struct {
	Messages []Message `json:"messages"`
	Count    int       `json:"count"`
}

// SkillInfo represents a single skill returned by /skills/query.
type SkillInfo struct {
	ID          string   `json:"id"`
	Name        string   `json:"name"`
	Description string   `json:"description,omitempty"`
	InputModes  []string `json:"inputModes,omitempty"`
	OutputModes []string `json:"outputModes,omitempty"`
}

// SkillsQueryResponse is the response from POST /skills/query.
type SkillsQueryResponse struct {
	Skills []SkillInfo `json:"skills"`
	Count  int         `json:"count"`
}

// ── Core methods ──────────────────────────────────────────────────────────

// Send posts a message to the peer via POST /message:send. [stable]
func (c *Client) Send(ctx context.Context, req SendRequest) (*SendResponse, error) {
	var resp SendResponse
	if err := c.postJSON(ctx, "/message:send", req, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// Recv polls for received messages via GET /recv. [stable]
func (c *Client) Recv(ctx context.Context, opts RecvOptions) (*RecvResponse, error) {
	u, _ := url.Parse(c.baseURL + "/recv")
	q := u.Query()
	if opts.Limit > 0 {
		q.Set("limit", fmt.Sprintf("%d", opts.Limit))
	}
	if opts.Since > 0 {
		q.Set("since", fmt.Sprintf("%d", opts.Since))
	}
	u.RawQuery = q.Encode()

	var resp RecvResponse
	if err := c.getJSON(ctx, u.String(), &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// GetStatus fetches relay status via GET /status. [stable]
func (c *Client) GetStatus(ctx context.Context) (*Status, error) {
	var resp Status
	if err := c.getJSON(ctx, c.baseURL+"/status", &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// GetTasks fetches all tasks via GET /tasks. [stable]
func (c *Client) GetTasks(ctx context.Context) ([]Task, error) {
	var resp struct {
		Tasks []Task `json:"tasks"`
	}
	if err := c.getJSON(ctx, c.baseURL+"/tasks", &resp); err != nil {
		return nil, err
	}
	return resp.Tasks, nil
}

// CancelTask cancels a task via POST /tasks/{id}:cancel. [stable]
func (c *Client) CancelTask(ctx context.Context, taskID string) error {
	var resp struct {
		OK    bool   `json:"ok"`
		Error string `json:"error,omitempty"`
	}
	path := fmt.Sprintf("/tasks/%s:cancel", taskID)
	if err := c.postJSON(ctx, path, nil, &resp); err != nil {
		return err
	}
	if !resp.OK {
		return fmt.Errorf("cancel task %s: %s", taskID, resp.Error)
	}
	return nil
}

// QuerySkills lists available skills via POST /skills/query. [stable]
// Pass nil for opts to return all skills.
func (c *Client) QuerySkills(ctx context.Context, opts map[string]any) (*SkillsQueryResponse, error) {
	if opts == nil {
		opts = map[string]any{}
	}
	var resp SkillsQueryResponse
	if err := c.postJSON(ctx, "/skills/query", opts, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// ── Internal helpers ──────────────────────────────────────────────────────

func (c *Client) postJSON(ctx context.Context, path string, body any, out any) error {
	var buf io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("acprelay: marshal: %w", err)
		}
		buf = bytes.NewReader(b)
	} else {
		buf = bytes.NewReader([]byte("{}"))
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, buf)
	if err != nil {
		return fmt.Errorf("acprelay: new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	return c.do(req, out)
}

func (c *Client) getJSON(ctx context.Context, rawURL string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return fmt.Errorf("acprelay: new request: %w", err)
	}
	return c.do(req, out)
}

func (c *Client) do(req *http.Request, out any) error {
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("acprelay: http: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("acprelay: server returned %d: %s", resp.StatusCode, string(body))
	}

	if out != nil {
		if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
			return fmt.Errorf("acprelay: decode response: %w", err)
		}
	}
	return nil
}

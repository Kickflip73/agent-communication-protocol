//! # ACP Relay SDK for Rust
//!
//! Thin HTTP client for [`acp_relay.py`](https://github.com/Kickflip73/agent-communication-protocol).
//!
//! ## Quick start
//!
//! ```rust,no_run
//! use acp_relay_sdk::{RelayClient, MessageRequest};
//!
//! fn main() -> Result<(), acp_relay_sdk::AcpError> {
//!     let client = RelayClient::new("http://localhost:8100")?;
//!
//!     // Send a message
//!     let resp = client.send_message(MessageRequest::user("Hello, Agent!"))?;
//!     println!("task_id: {}", resp.task_id.unwrap_or_default());
//!
//!     // Read AgentCard
//!     let card = client.agent_card()?;
//!     println!("peer: {:?}", card.self_card.name);
//!
//!     Ok(())
//! }
//! ```
//!
//! ## Live availability update (v1.2)
//!
//! ```rust,no_run
//! use acp_relay_sdk::{RelayClient, AvailabilityPatch};
//!
//! fn main() -> Result<(), acp_relay_sdk::AcpError> {
//!     let client = RelayClient::new("http://localhost:8100")?;
//!     client.patch_availability(AvailabilityPatch {
//!         last_active_at:  Some("2026-03-22T13:00:00Z".into()),
//!         next_active_at:  Some("2026-03-22T14:00:00Z".into()),
//!         ..Default::default()
//!     })?;
//!     Ok(())
//! }
//! ```

use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Duration;

// ── Error type ────────────────────────────────────────────────────────────────

/// All errors returned by the ACP SDK.
#[derive(Debug, thiserror::Error)]
pub enum AcpError {
    #[error("HTTP request failed: {0}")]
    Http(#[from] reqwest::Error),

    #[error("ACP relay returned error (code {code}): {message}")]
    Relay { code: String, message: String },

    #[error("Invalid base URL: {0}")]
    InvalidUrl(String),

    #[error("JSON serialisation error: {0}")]
    Json(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, AcpError>;

// ── Request / response types ──────────────────────────────────────────────────

/// A single content part (text, file, or structured data).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum Part {
    Text { text: String },
    File { uri: String, mime_type: Option<String> },
    Data { data: serde_json::Value },
}

/// Request body for `POST /message:send`.
#[derive(Debug, Clone, Serialize, Default)]
pub struct MessageRequest {
    pub role: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parts: Option<Vec<Part>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub task_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub context_id: Option<String>,
    /// If true, block until task completes or times out.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sync: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeout: Option<u32>,
}

impl MessageRequest {
    /// Convenience: build a `role="user"` text message.
    pub fn user(text: impl Into<String>) -> Self {
        Self { role: "user".into(), text: Some(text.into()), ..Default::default() }
    }

    /// Convenience: build a `role="agent"` text message.
    pub fn agent(text: impl Into<String>) -> Self {
        Self { role: "agent".into(), text: Some(text.into()), ..Default::default() }
    }

    /// Attach a client-generated message ID (for idempotency).
    pub fn with_message_id(mut self, id: impl Into<String>) -> Self {
        self.message_id = Some(id.into());
        self
    }

    /// Request synchronous execution.
    pub fn sync_timeout(mut self, timeout_secs: u32) -> Self {
        self.sync    = Some(true);
        self.timeout = Some(timeout_secs);
        self
    }
}

/// Response from `POST /message:send`.
#[derive(Debug, Clone, Deserialize)]
pub struct MessageResponse {
    pub task_id:    Option<String>,
    pub message_id: Option<String>,
    pub status:     Option<String>,
    pub error:      Option<RelayError>,
    #[serde(flatten)]
    pub extra: HashMap<String, serde_json::Value>,
}

/// Relay-level error envelope.
#[derive(Debug, Clone, Deserialize)]
pub struct RelayError {
    pub code:    String,
    pub message: String,
    pub failed_message_id: Option<String>,
}

/// The `availability` block in an AgentCard (v1.2).
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Availability {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mode: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub interval_seconds: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_active_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_active_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub task_latency_max_seconds: Option<u64>,
}

/// AgentCard returned by `GET /.well-known/acp.json`.
#[derive(Debug, Clone, Deserialize)]
pub struct AgentCard {
    pub id:           Option<String>,
    pub name:         Option<String>,
    pub version:      Option<String>,
    pub capabilities: Option<serde_json::Value>,
    pub availability: Option<Availability>,
    pub skills:       Option<Vec<serde_json::Value>>,
    #[serde(flatten)]
    pub extra: HashMap<String, serde_json::Value>,
}

/// Response from `GET /.well-known/acp.json`.
#[derive(Debug, Clone, Deserialize)]
pub struct AgentCardResponse {
    #[serde(rename = "self")]
    pub self_card: AgentCard,
    pub peer:      Option<AgentCard>,
}

/// Patch payload for `PATCH /.well-known/acp.json` (v1.2).
#[derive(Debug, Clone, Serialize, Default)]
pub struct AvailabilityPatch {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mode: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub interval_seconds: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_active_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_active_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub task_latency_max_seconds: Option<u64>,
}

/// Response from `PATCH /.well-known/acp.json`.
#[derive(Debug, Clone, Deserialize)]
pub struct PatchAvailabilityResponse {
    pub ok:           Option<bool>,
    pub availability: Option<Availability>,
    pub error:        Option<String>,
}

/// Relay status from `GET /status`.
#[derive(Debug, Clone, Deserialize)]
pub struct RelayStatus {
    pub session_id:   Option<String>,
    pub agent_name:   Option<String>,
    pub connected:    Option<bool>,
    pub link:         Option<String>,
    pub started_at:   Option<f64>,
    pub uptime_secs:  Option<f64>,
    pub version:      Option<String>,
    #[serde(flatten)]
    pub extra: HashMap<String, serde_json::Value>,
}

// ── RelayClient ───────────────────────────────────────────────────────────────

/// Blocking HTTP client for a running `acp_relay.py` instance.
///
/// Default base URL: `http://localhost:8100`
pub struct RelayClient {
    base: String,
    http: Client,
}

impl RelayClient {
    /// Create a new client.
    ///
    /// `base_url` should be the HTTP port of the relay (default port = WS port + 100).
    /// Example: `"http://localhost:8100"`.
    pub fn new(base_url: impl Into<String>) -> Result<Self> {
        let base = base_url.into().trim_end_matches('/').to_owned();
        if !base.starts_with("http://") && !base.starts_with("https://") {
            return Err(AcpError::InvalidUrl(base));
        }
        let http = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()?;
        Ok(Self { base, http })
    }

    fn url(&self, path: &str) -> String {
        format!("{}{}", self.base, path)
    }

    // ── Core message API ────────────────────────────────────────────────────

    /// Send a message to the connected peer.
    ///
    /// Maps to `POST /message:send`.
    pub fn send_message(&self, req: MessageRequest) -> Result<MessageResponse> {
        let resp = self.http
            .post(self.url("/message:send"))
            .json(&req)
            .send()?
            .json::<MessageResponse>()?;

        if let Some(err) = &resp.error {
            return Err(AcpError::Relay {
                code:    err.code.clone(),
                message: err.message.clone(),
            });
        }
        Ok(resp)
    }

    // ── AgentCard API ────────────────────────────────────────────────────────

    /// Fetch the local AgentCard (and peer card if connected).
    ///
    /// Maps to `GET /.well-known/acp.json`.
    pub fn agent_card(&self) -> Result<AgentCardResponse> {
        Ok(self.http
            .get(self.url("/.well-known/acp.json"))
            .send()?
            .json::<AgentCardResponse>()?)
    }

    /// Live-update the AgentCard availability block without restarting the relay.
    ///
    /// Maps to `PATCH /.well-known/acp.json` (v1.2).
    pub fn patch_availability(&self, patch: AvailabilityPatch) -> Result<PatchAvailabilityResponse> {
        let body = serde_json::json!({ "availability": patch });
        let resp = self.http
            .patch(self.url("/.well-known/acp.json"))
            .json(&body)
            .send()?
            .json::<PatchAvailabilityResponse>()?;

        if let Some(err) = &resp.error {
            return Err(AcpError::Relay {
                code:    "ERR_PATCH".into(),
                message: err.clone(),
            });
        }
        Ok(resp)
    }

    // ── Status & utility ────────────────────────────────────────────────────

    /// Fetch relay status.
    ///
    /// Maps to `GET /status`.
    pub fn status(&self) -> Result<RelayStatus> {
        Ok(self.http
            .get(self.url("/status"))
            .send()?
            .json::<RelayStatus>()?)
    }

    /// Fetch the session link (share this with another agent to connect).
    ///
    /// Maps to `GET /link`.
    pub fn link(&self) -> Result<Option<String>> {
        let resp = self.http
            .get(self.url("/link"))
            .send()?
            .json::<serde_json::Value>()?;
        Ok(resp["link"].as_str().map(str::to_owned))
    }

    /// Check if the relay is reachable (health-check).
    pub fn ping(&self) -> Result<bool> {
        Ok(self.http
            .get(self.url("/.well-known/acp.json"))
            .timeout(Duration::from_secs(5))
            .send()
            .map(|r| r.status().is_success())
            .unwrap_or(false))
    }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn message_request_user_helper() {
        let req = MessageRequest::user("hello");
        assert_eq!(req.role, "user");
        assert_eq!(req.text.as_deref(), Some("hello"));
        assert!(req.parts.is_none());
    }

    #[test]
    fn message_request_agent_helper() {
        let req = MessageRequest::agent("pong");
        assert_eq!(req.role, "agent");
        assert_eq!(req.text.as_deref(), Some("pong"));
    }

    #[test]
    fn message_request_with_message_id() {
        let req = MessageRequest::user("test").with_message_id("uuid-123");
        assert_eq!(req.message_id.as_deref(), Some("uuid-123"));
    }

    #[test]
    fn message_request_sync_timeout() {
        let req = MessageRequest::user("test").sync_timeout(30);
        assert_eq!(req.sync, Some(true));
        assert_eq!(req.timeout, Some(30));
    }

    #[test]
    fn invalid_base_url_returns_error() {
        let err = RelayClient::new("ftp://localhost:8100").unwrap_err();
        assert!(matches!(err, AcpError::InvalidUrl(_)));
    }

    #[test]
    fn valid_base_url_accepted() {
        assert!(RelayClient::new("http://localhost:8100").is_ok());
        assert!(RelayClient::new("https://my-relay.example.com").is_ok());
    }

    #[test]
    fn base_url_trailing_slash_stripped() {
        let client = RelayClient::new("http://localhost:8100/").unwrap();
        assert_eq!(client.url("/status"), "http://localhost:8100/status");
    }

    #[test]
    fn availability_patch_serialises_correctly() {
        let patch = AvailabilityPatch {
            next_active_at: Some("2026-03-22T14:00:00Z".into()),
            last_active_at: Some("2026-03-22T13:00:00Z".into()),
            ..Default::default()
        };
        let body = serde_json::json!({ "availability": patch });
        let s = serde_json::to_string(&body).unwrap();
        assert!(s.contains("next_active_at"));
        assert!(s.contains("last_active_at"));
        // mode should be omitted (None → skip_serializing_if)
        assert!(!s.contains("\"mode\""));
    }
}

"""
acp_client.models — Data models for the ACP relay API.

All models are plain dataclasses with no external dependencies.
They can be serialised to/from the dicts returned by RelayClient methods.

Example:
    from acp_client.models import AgentCard, Message, Task, TaskStatus

    card = AgentCard.from_dict(client.card())
    print(card.name, card.version)

    for msg in client.recv():
        m = Message.from_dict(msg)
        print(m.role, m.text)
"""
from __future__ import annotations

import uuid
import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    """ACP task lifecycle states (v0.5 → v2.6)."""

    SUBMITTED      = "submitted"
    WORKING        = "working"
    COMPLETED      = "completed"
    FAILED         = "failed"
    INPUT_REQUIRED = "input_required"
    CANCELED       = "canceled"
    CANCELLING     = "cancelling"   # v2.6 two-phase cancel

    @classmethod
    def terminal_states(cls) -> frozenset["TaskStatus"]:
        """Return the set of states from which a task cannot proceed."""
        return frozenset({cls.COMPLETED, cls.FAILED, cls.CANCELED})

    def is_terminal(self) -> bool:
        return self in self.terminal_states()


class PartType(str, Enum):
    """ACP structured-message part types."""
    TEXT = "text"
    FILE = "file"
    DATA = "data"


# ─────────────────────────────────────────────────────────────
# Part — structured message payload
# ─────────────────────────────────────────────────────────────

@dataclass
class Part:
    """
    A single part in a structured ACP message (v0.5+).

    Attributes:
        type:      "text" | "file" | "data"
        text:      Content for type=text.
        mime_type: MIME type for type=file.
        data:      Arbitrary dict for type=data.
        name:      Optional filename for type=file.
        url:       Optional URL for type=file.
    """

    type: str
    text: Optional[str] = None
    mime_type: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    name: Optional[str] = None
    url: Optional[str] = None

    @classmethod
    def text_part(cls, content: str) -> "Part":
        return cls(type=PartType.TEXT, text=content)

    @classmethod
    def data_part(cls, payload: dict) -> "Part":
        return cls(type=PartType.DATA, data=payload)

    @classmethod
    def file_part(cls, name: str, mime_type: str, url: str = None) -> "Part":
        return cls(type=PartType.FILE, name=name, mime_type=mime_type, url=url)

    def to_dict(self) -> dict:
        d: dict = {"type": self.type}
        if self.text is not None:
            d["text"] = self.text
        if self.mime_type is not None:
            d["mime_type"] = self.mime_type
        if self.data is not None:
            d["data"] = self.data
        if self.name is not None:
            d["name"] = self.name
        if self.url is not None:
            d["url"] = self.url
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Part":
        return cls(
            type=d.get("type", "text"),
            text=d.get("text"),
            mime_type=d.get("mime_type"),
            data=d.get("data"),
            name=d.get("name"),
            url=d.get("url"),
        )


# ─────────────────────────────────────────────────────────────
# Message
# ─────────────────────────────────────────────────────────────

@dataclass
class Message:
    """
    An ACP relay message (v0.6+).

    Attributes:
        message_id:   Server-assigned idempotency key.
        role:         "user" | "assistant" | "agent"
        text:         Plain-text shorthand (if parts is empty).
        parts:        Structured Part list.
        from_peer:    Sender peer_id or name.
        task_id:      Associated task id (optional).
        context_id:   Multi-turn context group id (v0.7).
        server_seq:   Server-assigned sequence number.
        ts:           ISO-8601 timestamp.
    """

    message_id: str = field(default_factory=lambda: "msg_" + uuid.uuid4().hex[:16])
    role: str = "user"
    text: Optional[str] = None
    parts: List[Part] = field(default_factory=list)
    from_peer: Optional[str] = None
    task_id: Optional[str] = None
    context_id: Optional[str] = None
    server_seq: Optional[int] = None
    ts: Optional[str] = None

    def get_text(self) -> str:
        """Return the combined text content of all text parts (or the `text` field)."""
        if self.text:
            return self.text
        return "\n".join(
            p.text for p in self.parts if p.type == PartType.TEXT and p.text
        )

    def to_dict(self) -> dict:
        d: dict = {"role": self.role, "message_id": self.message_id}
        if self.text is not None:
            d["text"] = self.text
        if self.parts:
            d["parts"] = [p.to_dict() for p in self.parts]
        if self.from_peer:
            d["from"] = self.from_peer
        if self.task_id:
            d["task_id"] = self.task_id
        if self.context_id:
            d["context_id"] = self.context_id
        if self.server_seq is not None:
            d["server_seq"] = self.server_seq
        if self.ts:
            d["ts"] = self.ts
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        parts = [Part.from_dict(p) for p in d.get("parts", [])]
        return cls(
            message_id=d.get("message_id", ""),
            role=d.get("role", "user"),
            text=d.get("text"),
            parts=parts,
            from_peer=d.get("from") or d.get("from_peer"),
            task_id=d.get("task_id"),
            context_id=d.get("context_id"),
            server_seq=d.get("server_seq"),
            ts=d.get("ts"),
        )


# ─────────────────────────────────────────────────────────────
# Task
# ─────────────────────────────────────────────────────────────

@dataclass
class Task:
    """
    An ACP task (v0.5+).

    Attributes:
        task_id:    Server-assigned task identifier.
        status:     Current TaskStatus.
        description: Human-readable task description.
        input:      Task input payload dict.
        output:     Task output payload dict (set on completion).
        peer_id:    Associated peer agent id.
        created_at: ISO-8601 creation timestamp.
        updated_at: ISO-8601 last-update timestamp.
        error:      Error dict (if status=failed).
        metadata:   Arbitrary extra fields from the server.
    """

    task_id: str = field(default_factory=lambda: "task_" + uuid.uuid4().hex[:12])
    status: TaskStatus = TaskStatus.SUBMITTED
    description: Optional[str] = None
    input: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    peer_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        """Return True if the task is in a terminal state."""
        return self.status.is_terminal() if isinstance(self.status, TaskStatus) else \
               self.status in {"completed", "failed", "canceled"}

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "description": self.description,
            "input": self.input,
            "output": self.output,
            "peer_id": self.peer_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            **self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        status_raw = d.get("status") or d.get("state", "submitted")
        try:
            status = TaskStatus(status_raw)
        except ValueError:
            status = TaskStatus.SUBMITTED

        known_keys = {
            "task_id", "id", "status", "state", "description",
            "input", "output", "peer_id", "created_at", "updated_at", "error",
        }
        metadata = {k: v for k, v in d.items() if k not in known_keys}

        return cls(
            task_id=d.get("task_id") or d.get("id", ""),
            status=status,
            description=d.get("description"),
            input=d.get("input", {}),
            output=d.get("output", {}),
            peer_id=d.get("peer_id"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            error=d.get("error"),
            metadata=metadata,
        )


# ─────────────────────────────────────────────────────────────
# Extension — AgentCard extension descriptor (v2.8)
# ─────────────────────────────────────────────────────────────

@dataclass
class Extension:
    """
    ACP AgentCard extension descriptor (v2.8).

    Each extension is identified by a unique URI and carries optional metadata.
    Clients that do not recognise an extension MUST ignore it (non-required)
    or MAY refuse the connection (required=True).

    URI naming convention:
      - Built-in:  ``acp:ext:<name>-v<version>``  (e.g. ``acp:ext:hmac-v1``)
      - External:  full HTTPS URL                  (e.g. ``https://corp.example.com/ext/billing``)

    Well-known built-in URIs
    ~~~~~~~~~~~~~~~~~~~~~~~~
    ``acp:ext:hmac-v1``
        HMAC-SHA256 message signing.  Activated by ``--secret``.
    ``acp:ext:mdns-v1``
        mDNS LAN peer discovery.  Activated by ``--advertise-mdns``.
    ``acp:ext:h2c-v1``
        HTTP/2 cleartext transport.  Activated by ``--http2``.

    Attributes:
        uri:      Unique extension identifier URI (required).
        required: If True, clients that don't support this extension SHOULD
                  abort the connection.  Default: False.
        params:   Arbitrary key-value parameters for the extension.
    """

    uri: str
    required: bool = False
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict = {"uri": self.uri, "required": self.required}
        if self.params:
            d["params"] = dict(self.params)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Extension":
        if not isinstance(d, dict):
            raise ValueError(f"Extension.from_dict expects a dict, got {type(d).__name__}")
        uri = d.get("uri")
        if not uri:
            raise ValueError("Extension dict missing required 'uri' field")
        return cls(
            uri=uri,
            required=bool(d.get("required", False)),
            params=dict(d.get("params", {})),
        )

    def __repr__(self) -> str:
        req_flag = " required" if self.required else ""
        return f"<Extension uri={self.uri!r}{req_flag}>"


# ─────────────────────────────────────────────────────────────
# AgentCard
# ─────────────────────────────────────────────────────────────

@dataclass
class AgentCard:
    """
    ACP AgentCard (/.well-known/acp.json) — capability declaration (v0.4+).

    Attributes:
        name:              Human-readable agent name.
        version:           Agent version string.
        description:       Short description.
        acp_version:       ACP protocol version implemented.
        capabilities:      Capability flags dict.
        skills:            List of skill descriptor dicts.
        supported_interfaces: Interface groups supported (v2.5+).
        transport_modes:   Routing topology modes (v2.4+): "p2p" | "relay".
        availability:      Scheduling availability descriptor (v2.1+).
        limitations:       List of limitation strings (v2.7+).
        extensions:        List of Extension objects (v2.8+). URI-identified extension
                           declarations.  Built-in extensions (hmac, mdns, h2c) are
                           auto-registered; additional ones added via --extensions CLI flag.
                           Clients that don't recognise an extension MUST ignore it unless
                           required=True.
        identity:          DID identity block (v1.3+).
        metadata:          Arbitrary extra top-level fields.
    """

    name: str = "unnamed-agent"
    version: str = "0.0.0"
    description: str = ""
    acp_version: str = "0.4"
    capabilities: Dict[str, Any] = field(default_factory=dict)
    skills: List[Dict[str, Any]] = field(default_factory=list)
    supported_interfaces: List[str] = field(default_factory=list)
    transport_modes: List[str] = field(default_factory=lambda: ["p2p", "relay"])
    availability: Dict[str, Any] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)
    extensions: List[Extension] = field(default_factory=list)
    identity: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Convenience accessors

    def supports(self, capability: str) -> bool:
        """Return True if the named capability is declared and truthy."""
        return bool(self.capabilities.get(capability, False))

    def has_interface(self, interface: str) -> bool:
        """Return True if the agent declares the given interface group."""
        return interface in self.supported_interfaces

    def has_limitation(self, limitation: str) -> bool:
        """Return True if the agent declares the given limitation."""
        return limitation in self.limitations

    def can_use_p2p(self) -> bool:
        """Return True if P2P routing mode is supported."""
        return "p2p" in self.transport_modes

    def can_use_relay(self) -> bool:
        """Return True if relay routing mode is supported."""
        return "relay" in self.transport_modes

    def has_extension(self, uri: str) -> bool:
        """Return True if the agent declares the given extension URI (v2.8+)."""
        return any(e.uri == uri for e in self.extensions)

    def get_extension(self, uri: str) -> Optional["Extension"]:
        """Return the Extension object for the given URI, or None (v2.8+)."""
        for e in self.extensions:
            if e.uri == uri:
                return e
        return None

    def required_extensions(self) -> List["Extension"]:
        """Return all extensions where required=True (v2.8+)."""
        return [e for e in self.extensions if e.required]

    def to_dict(self) -> dict:
        d: dict = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "acp_version": self.acp_version,
            "capabilities": self.capabilities,
            # v2.8: always emit extensions (empty list when none)
            "extensions": [e.to_dict() for e in self.extensions],
        }
        if self.skills:
            d["skills"] = self.skills
        if self.supported_interfaces:
            d["supported_interfaces"] = self.supported_interfaces
        if self.transport_modes != ["p2p", "relay"]:
            d["transport_modes"] = self.transport_modes
        if self.availability:
            d["availability"] = self.availability
        if self.limitations:
            d["limitations"] = self.limitations
        if self.identity:
            d["identity"] = self.identity
        d.update(self.metadata)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AgentCard":
        known_keys = {
            "name", "version", "description", "acp_version",
            "capabilities", "skills", "supported_interfaces",
            "transport_modes", "availability", "limitations",
            "extensions", "identity", "self",
        }
        # Some relays nest the card under "self"
        if "self" in d and isinstance(d["self"], dict):
            inner = d["self"]
            d = {**inner, **{k: v for k, v in d.items() if k != "self"}}

        metadata = {k: v for k, v in d.items() if k not in known_keys}

        # v2.8: parse extensions list; tolerate missing field (backward compat)
        raw_extensions = d.get("extensions", [])
        extensions: List[Extension] = []
        if isinstance(raw_extensions, list):
            for item in raw_extensions:
                if isinstance(item, dict):
                    try:
                        extensions.append(Extension.from_dict(item))
                    except (ValueError, KeyError):
                        pass  # skip malformed entries; forward-compat

        return cls(
            name=d.get("name", "unnamed-agent"),
            version=d.get("version", "0.0.0"),
            description=d.get("description", ""),
            acp_version=d.get("acp_version", "0.4"),
            capabilities=d.get("capabilities", {}),
            skills=d.get("skills", []),
            supported_interfaces=d.get("supported_interfaces", []),
            transport_modes=d.get("transport_modes", ["p2p", "relay"]),
            availability=d.get("availability", {}),
            limitations=d.get("limitations", []),
            extensions=extensions,
            identity=d.get("identity", {}),
            metadata=metadata,
        )

    def __repr__(self) -> str:
        return (
            f"<AgentCard name={self.name!r} version={self.version!r} "
            f"acp={self.acp_version!r}>"
        )

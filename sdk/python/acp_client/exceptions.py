"""
acp_client.exceptions — ACP error hierarchy.

All exceptions raised by RelayClient and AsyncRelayClient are subclasses of
ACPError, allowing callers to catch the whole family with a single clause:

    try:
        client.send("hello")
    except ACPError as e:
        print(e.code, e.message)
"""
from __future__ import annotations


class ACPError(Exception):
    """Base exception for all ACP client errors."""

    def __init__(self, message: str = "", code: str = "ERR_ACP", *, response: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.response = response or {}

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


class ConnectionError(ACPError):
    """Raised when the client cannot reach the relay."""

    def __init__(self, message: str = "Cannot connect to relay", *, url: str = ""):
        super().__init__(message, code="ERR_CONNECTION")
        self.url = url


class PeerNotFoundError(ACPError):
    """Raised when the target peer_id does not exist."""

    def __init__(self, peer_id: str = ""):
        super().__init__(
            f"Peer {peer_id!r} not found",
            code="ERR_PEER_NOT_FOUND",
        )
        self.peer_id = peer_id


class TaskNotFoundError(ACPError):
    """Raised when the target task_id does not exist."""

    def __init__(self, task_id: str = ""):
        super().__init__(
            f"Task {task_id!r} not found",
            code="ERR_TASK_NOT_FOUND",
        )
        self.task_id = task_id


class TaskNotCancelableError(ACPError):
    """Raised when trying to cancel a task that is already in a terminal state."""

    def __init__(self, task_id: str = ""):
        super().__init__(
            f"Task {task_id!r} is in a terminal state and cannot be canceled",
            code="ERR_TASK_NOT_CANCELABLE",
        )
        self.task_id = task_id


class SendError(ACPError):
    """Raised when the relay rejects a send request."""

    def __init__(self, message: str = "Send failed", *, response: dict = None):
        super().__init__(message, code="ERR_SEND", response=response)


class TimeoutError(ACPError):  # noqa: A001 — intentional shadow of builtins.TimeoutError
    """Raised when a blocking operation exceeds its timeout."""

    def __init__(self, operation: str = "operation", timeout: float = 0.0):
        super().__init__(
            f"{operation} timed out after {timeout:.1f}s",
            code="ERR_TIMEOUT",
        )
        self.operation = operation
        self.timeout = timeout


class AuthError(ACPError):
    """Raised on 401 / 403 responses from the relay."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code="ERR_AUTH")


def _raise_from_response(resp: dict, peer_id: str = "", task_id: str = "") -> None:
    """
    Inspect a relay response dict and raise the appropriate ACPError subclass
    if the response indicates an error.  No-op if the response looks successful.
    """
    if resp.get("ok") is True:
        return
    code = resp.get("error_code") or resp.get("error", "")
    msg = resp.get("message") or str(resp)

    mapping = {
        "ERR_PEER_NOT_FOUND": lambda: PeerNotFoundError(peer_id),
        "ERR_TASK_NOT_FOUND": lambda: TaskNotFoundError(task_id),
        "ERR_TASK_NOT_CANCELABLE": lambda: TaskNotCancelableError(task_id),
        "ERR_AUTH": lambda: AuthError(msg),
    }
    factory = mapping.get(code)
    if factory:
        raise factory()
    # Generic fallback
    if code or not resp.get("ok", True):
        raise ACPError(msg, code=code or "ERR_ACP", response=resp)

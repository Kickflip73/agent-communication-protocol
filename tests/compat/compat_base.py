"""
ACP Compatibility Test Suite — base framework
Zero external dependencies (stdlib only).
"""
import json
import urllib.request
import urllib.error
import time
import sys

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "
SKIP = "⏭ "


class Compat:
    """Base class for ACP compatibility test suites."""

    def __init__(self, base_url: str, agent_card: dict, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.agent_card = agent_card
        self.verbose = verbose
        self.results: list[dict] = []

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def get(self, path: str, timeout: float = 5.0) -> tuple[int, dict]:
        url = self.base_url + path
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read())
            except Exception:
                body = {}
            return e.code, body
        except Exception as e:
            return 0, {"_error": str(e)}

    def post(self, path: str, body: dict, timeout: float = 5.0) -> tuple[int, dict]:
        url = self.base_url + path
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                body_resp = json.loads(e.read())
            except Exception:
                body_resp = {}
            return e.code, body_resp
        except Exception as e:
            return 0, {"_error": str(e)}

    # ── Assertion helpers ─────────────────────────────────────────────────────

    def check(self, name: str, condition: bool, level: str = "MUST",
              detail: str = "") -> bool:
        status = PASS if condition else (FAIL if level == "MUST" else WARN)
        self.results.append({
            "name": name,
            "pass": condition,
            "level": level,
            "status": status,
            "detail": detail,
        })
        if self.verbose:
            print(f"  {status} [{level}] {name}" + (f" — {detail}" if detail else ""))
        return condition

    def skip(self, name: str, reason: str = "") -> None:
        self.results.append({
            "name": name,
            "pass": None,
            "level": "MAY",
            "status": SKIP,
            "detail": reason,
        })
        if self.verbose:
            print(f"  {SKIP} [MAY ] {name}" + (f" — {reason}" if reason else ""))

    def has_capability(self, cap: str) -> bool:
        caps = self.agent_card.get("capabilities", {})
        return bool(caps.get(cap))

    # ── Summary ───────────────────────────────────────────────────────────────

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r["pass"] is True)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r["pass"] is False and r["level"] == "MUST")

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r["pass"] is False and r["level"] != "MUST")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r["pass"] is None)

    @property
    def total_required(self) -> int:
        return sum(1 for r in self.results if r["level"] == "MUST")

    def run(self) -> None:
        raise NotImplementedError

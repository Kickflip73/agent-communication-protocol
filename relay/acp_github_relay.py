#!/usr/bin/env python3
"""
ACP GitHub Issues Relay — v0.1
================================
Uses a GitHub Issue as a shared mailbox for two agents.
Both agents poll the same issue's comments.

Transport-agnostic: the session layer (acp_relay.py) doesn't
know if it's talking over WebSocket direct or GitHub relay.

Architecture:
  Agent A  --[POST comment]--> GitHub Issue <--[GET comments]-- Agent B
  Agent B  --[POST comment]--> GitHub Issue <--[GET comments]-- Agent A

Session handshake:
  1. Initiator creates an Issue → gets relay link: acp+gh://REPO/ISSUE_NUM/TOKEN
  2. Joiner fetches the issue URL, starts polling comments
  3. Both sides write their AgentCard as the first comment
  4. Poll interval: 3s (configurable via --poll-interval)
"""

import argparse
import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error
import uuid
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
class ThreadingHTTPServer(ThreadingMixIn, HTTPServer): daemon_threads = True
from urllib.parse import urlparse, parse_qs

VERSION = "0.1"
POLL_INTERVAL = 3  # seconds between polls
MAX_COMMENT_BYTES = 60000  # GitHub comment limit ~65536

# ── Global state ──────────────────────────────────────────────────────────────
_session = {
    "issue_num":     None,
    "repo":          None,
    "token":         None,
    "agent_name":    None,
    "skills":        [],
    "connected":     False,
    "peer_card":     None,
    "last_seen_id":  0,      # highest comment ID we've already processed
    "http_port":     7901,
    "role":          None,   # "initiator" | "joiner"
}
_recv_queue = deque(maxlen=500)
_sent_ids   = set()   # our own comment IDs (skip when polling)

GH_BASE = "https://api.github.com"

def _gh(method, path, body=None, token=None):
    tok = token or _session["token"]
    url = f"{GH_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"token {tok}",
        "User-Agent": f"acp-gh-relay/{VERSION}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github.v3+json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            if r.status == 204:
                return {}
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = e.read()[:200]
        raise RuntimeError(f"GitHub API {method} {path} -> HTTP {e.code}: {err}")

def _make_agent_card():
    return {
        "type":        "acp.agent_card",
        "name":        _session["agent_name"],
        "acp_version": "0.6-dev",
        "skills":      [{"id": s, "name": s} for s in _session["skills"]],
        "relay":       "github_issues",
    }

def _post_message(parts, msg_id=None, task_id=None):
    """Post a message as a GitHub comment."""
    mid = msg_id or f"msg_{uuid.uuid4().hex[:12]}"
    payload = {
        "type":       "acp.message",
        "message_id": mid,
        "from":       _session["agent_name"],
        "ts":         time.time(),
        "parts":      parts,
    }
    if task_id:
        payload["task_id"] = task_id

    repo  = _session["repo"]
    issue = _session["issue_num"]
    comment = _gh("POST", f"/repos/{repo}/issues/{issue}/comments",
                  {"body": json.dumps(payload)})
    _sent_ids.add(comment["id"])
    return mid, comment["id"]

def _poll_loop():
    """Background thread: poll GitHub comments, put new ones in recv queue."""
    repo  = _session["repo"]
    issue = _session["issue_num"]
    my_name = _session["agent_name"]

    while True:
        try:
            comments = _gh("GET", f"/repos/{repo}/issues/{issue}/comments?per_page=50&sort=created&direction=asc")
            for c in comments:
                cid = c["id"]
                if cid in _sent_ids:
                    continue
                if cid <= _session["last_seen_id"]:
                    continue

                _session["last_seen_id"] = cid

                try:
                    body = json.loads(c["body"])
                except Exception:
                    continue

                # Handle AgentCard handshake
                if body.get("type") == "acp.agent_card":
                    if body.get("name") != my_name:
                        _session["peer_card"] = body
                        _session["connected"] = True
                        print(f"\n[ACP-GH] Peer connected: {body['name']}")
                    continue

                # Regular message
                if body.get("from") != my_name:
                    _recv_queue.append(body)

        except Exception as e:
            print(f"[ACP-GH] Poll error: {e}")

        time.sleep(POLL_INTERVAL)


# ── HTTP interface (same API surface as acp_relay.py) ─────────────────────────

class RelayHTTP(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        p = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)

        if p in ("/status", "/.well-known/acp.json"):
            self._json({
                "acp_version": "0.6-dev",
                "transport":   "github_issues",
                "connected":   _session["connected"],
                "agent_name":  _session["agent_name"],
                "peer_card":   _session["peer_card"],
                "relay_url":   f"https://github.com/{_session['repo']}/issues/{_session['issue_num']}",
                "link":        f"acp+gh://{_session['repo']}/{_session['issue_num']}",
            })
        elif p == "/link":
            self._json({
                "link":    f"acp+gh://{_session['repo']}/{_session['issue_num']}",
                "issue":   f"https://github.com/{_session['repo']}/issues/{_session['issue_num']}",
                "note":    "Share this link with the other agent. They need a GitHub token with repo scope.",
            })
        elif p == "/recv":
            limit = int(qs.get("limit", ["50"])[0])
            msgs  = [_recv_queue.popleft() for _ in range(min(limit, len(_recv_queue)))]
            self._json({"messages": msgs, "count": len(msgs), "remaining": len(_recv_queue)})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path

        if p == "/message:send":
            try:
                body  = self._body()
                parts = body.get("parts") or [{"type": "text", "content": str(body.get("content",""))}]
                mid, cid = _post_message(parts, msg_id=body.get("message_id"), task_id=body.get("task_id"))
                self._json({"ok": True, "message_id": mid, "comment_id": cid})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        else:
            self._json({"error": "not found"}, 404)


def main():
    global _session

    parser = argparse.ArgumentParser(description=f"ACP GitHub Issues Relay v{VERSION}")
    parser.add_argument("--name",   default="ACP-Agent", help="Agent name")
    parser.add_argument("--skills", default="",          help="Comma-separated skill ids")
    parser.add_argument("--token",  default=os.environ.get("GITHUB_TOKEN",""), help="GitHub token (repo scope)")
    parser.add_argument("--repo",   default="Kickflip73/agent-communication-protocol")
    parser.add_argument("--join",   default=None, help="acp+gh://REPO/ISSUE_NUM to join")
    parser.add_argument("--port",   type=int, default=7902, help="HTTP port")
    parser.add_argument("--poll-interval", type=int, default=3)
    args = parser.parse_args()

    if not args.token:
        print("ERROR: --token or GITHUB_TOKEN env var required")
        sys.exit(1)

    global POLL_INTERVAL
    POLL_INTERVAL = args.poll_interval

    _session["agent_name"] = args.name
    _session["skills"]     = [s.strip() for s in args.skills.split(",") if s.strip()]
    _session["token"]      = args.token
    _session["repo"]       = args.repo
    _session["http_port"]  = args.port

    if args.join:
        # Joiner: parse acp+gh://REPO/ISSUE_NUM
        joined = args.join.replace("acp+gh://", "")
        parts_url = joined.split("/")
        _session["repo"]      = "/".join(parts_url[:2])
        _session["issue_num"] = int(parts_url[2])
        _session["role"]      = "joiner"
        print(f"[ACP-GH] Joining relay mailbox: {args.join}")
    else:
        # Initiator: create a new Issue
        issue = _gh("POST", f"/repos/{args.repo}/issues", {
            "title": f"[ACP Relay] Session {uuid.uuid4().hex[:8]}",
            "body":  json.dumps({"type": "acp.relay_session", "created_by": args.name,
                                 "ts": time.time()}),
            "labels": [],
        }, token=args.token)
        _session["issue_num"] = issue["number"]
        _session["role"]      = "initiator"
        link = f"acp+gh://{args.repo}/{issue['number']}"
        print(f"\n[ACP-GH] Relay mailbox created: #{issue['number']}")
        print(f"[ACP-GH] Share this link with the other agent:")
        print(f"         {link}")
        print(f"         {issue['html_url']}\n")

    # Post our AgentCard as first comment
    repo  = _session["repo"]
    issue = _session["issue_num"]
    card_comment = _gh("POST", f"/repos/{repo}/issues/{issue}/comments",
                       {"body": json.dumps(_make_agent_card())}, token=args.token)
    _sent_ids.add(card_comment["id"])
    print(f"[ACP-GH] AgentCard posted. Polling for peer...")

    # Start poll thread
    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()

    # Start HTTP server
    server = ThreadingHTTPServer(("127.0.0.1", args.port), RelayHTTP)
    print(f"[ACP-GH] HTTP interface: http://127.0.0.1:{args.port}")
    print(f"[ACP-GH] Same API as acp_relay.py: /message:send  /recv  /status  /link")
    server.serve_forever()


if __name__ == "__main__":
    main()

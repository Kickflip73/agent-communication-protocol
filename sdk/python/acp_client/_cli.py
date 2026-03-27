"""
acp-client CLI — simple command-line interface for the ACP relay.

Commands:
  acp-client status   [--url URL]               Show relay status
  acp-client card     [--url URL]               Show AgentCard
  acp-client link     [--url URL]               Print this node's acp:// link
  acp-client peers    [--url URL]               List connected peers
  acp-client send     TEXT [--url URL] [--peer PEER_ID]  Send a message
  acp-client recv     [--url URL] [--limit N]   Poll received messages
  acp-client tasks    [--url URL] [--status S]  List tasks
  acp-client stream   [--url URL] [--timeout N] Subscribe to SSE stream

Examples:
  acp-client status
  acp-client send "Hello world"
  acp-client send "Hi" --peer sess_abc123
  acp-client recv --limit 10
  acp-client stream --timeout 60
  acp-client tasks --status working
"""
from __future__ import annotations

import argparse
import json
import sys


DEFAULT_URL = "http://localhost:7901"


def _client(url: str):
    from acp_client import RelayClient
    return RelayClient(url)


def cmd_status(args):
    c = _client(args.url)
    print(json.dumps(c.status(), indent=2))


def cmd_card(args):
    c = _client(args.url)
    print(json.dumps(c.card_raw(), indent=2))


def cmd_link(args):
    c = _client(args.url)
    print(c.link())


def cmd_peers(args):
    c = _client(args.url)
    peers = c.peers()
    if not peers:
        print("(no peers connected)")
        return
    for p in peers:
        print(f"  {p.get('peer_id', '?')}  {p.get('name', 'unnamed')}")


def cmd_send(args):
    c = _client(args.url)
    if args.peer:
        resp = c.send_to_peer(args.peer, args.text)
    else:
        resp = c.send(args.text)
    print(json.dumps(resp, indent=2))


def cmd_recv(args):
    c = _client(args.url)
    msgs = c.recv(limit=args.limit)
    if not msgs:
        print("(no messages)")
        return
    for m in msgs:
        role = m.get("role", "?")
        text = m.get("text") or "(structured)"
        mid = m.get("message_id", "")
        print(f"[{role}] {mid}: {text}")


def cmd_tasks(args):
    c = _client(args.url)
    tasks = c.tasks(status=args.status)
    if not tasks:
        print("(no tasks)")
        return
    for t in tasks:
        tid = t.get("task_id") or t.get("id", "?")
        st = t.get("status") or t.get("state", "?")
        desc = t.get("description", "")
        print(f"  {tid}  [{st}]  {desc}")


def cmd_stream(args):
    c = _client(args.url)
    print(f"Subscribing to SSE stream at {args.url}/stream (timeout={args.timeout}s)…")
    for event in c.stream(timeout=args.timeout):
        print(json.dumps(event))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="acp-client",
        description="ACP Relay CLI — interact with a running acp_relay.py",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Relay URL (default: {DEFAULT_URL})")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status",  help="Show relay status")
    sub.add_parser("card",    help="Show AgentCard")
    sub.add_parser("link",    help="Print acp:// link")
    sub.add_parser("peers",   help="List connected peers")

    p_send = sub.add_parser("send", help="Send a message")
    p_send.add_argument("text",   help="Message text")
    p_send.add_argument("--peer", default=None, help="Target peer_id (multi-session)")

    p_recv = sub.add_parser("recv", help="Poll received messages")
    p_recv.add_argument("--limit", type=int, default=20, help="Max messages")

    p_tasks = sub.add_parser("tasks", help="List tasks")
    p_tasks.add_argument("--status", default=None, help="Filter by state")

    p_stream = sub.add_parser("stream", help="Subscribe to SSE event stream")
    p_stream.add_argument("--timeout", type=float, default=60.0, help="Seconds to listen")

    args = parser.parse_args(argv)

    dispatch = {
        "status": cmd_status,
        "card":   cmd_card,
        "link":   cmd_link,
        "peers":  cmd_peers,
        "send":   cmd_send,
        "recv":   cmd_recv,
        "tasks":  cmd_tasks,
        "stream": cmd_stream,
    }
    try:
        dispatch[args.command](args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

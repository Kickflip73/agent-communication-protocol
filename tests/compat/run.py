#!/usr/bin/env python3
"""
ACP Compatibility Test Suite — main runner
Usage:
  python3 tests/compat/run.py [--url URL] [--secret SECRET] [--json] [-v]

Examples:
  python3 tests/compat/run.py
  python3 tests/compat/run.py --url http://remote-agent:7801
  python3 tests/compat/run.py --url http://localhost:7801 --secret my_hmac_secret -v
  python3 tests/compat/run.py --json > results.json
"""
import sys
import os
import json
import argparse
import urllib.request

# Allow importing sibling modules when run from repo root
sys.path.insert(0, os.path.dirname(__file__))

from compat_base import Compat, PASS, FAIL, WARN, SKIP
from test_agentcard import AgentCardSuite
from test_message_send import MessageSendSuite
from test_tasks import TasksSuite
from test_error_codes import ErrorCodesSuite
from test_peers import PeersSuite
from test_query_skills import QuerySkillsSuite
from test_hmac import HMACSigningSuite


VERSION = "0.1.0"
BAR = "━" * 55


def fetch_agent_card(base_url: str) -> dict:
    try:
        with urllib.request.urlopen(f"{base_url}/.well-known/acp.json", timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def run_suite(suite: Compat, verbose: bool) -> tuple[int, int, int, int]:
    suite.verbose = verbose
    suite.run()
    return suite.passed, suite.failed, suite.warned, suite.skipped


def fmt_suite_line(name: str, p: int, f: int, w: int, s: int, total_req: int) -> str:
    if f > 0:
        icon = FAIL
        detail = f"{p}/{total_req} PASS, {f} FAIL"
    elif w > 0:
        icon = WARN
        detail = f"{p}/{total_req} PASS, {w} WARN"
    else:
        detail = f"{p}/{total_req} PASS"
        if s > 0:
            detail += f", {s} SKIP"
        icon = SKIP if total_req == 0 else PASS
    return f"{icon} {name:<25} {detail}"


def main():
    parser = argparse.ArgumentParser(description=f"ACP Compatibility Suite v{VERSION}")
    parser.add_argument("--url", default="http://localhost:7801",
                        help="Base URL of the ACP agent to test (default: http://localhost:7801)")
    parser.add_argument("--secret", default=None,
                        help="HMAC secret (for testing hmac_signing capability)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON results")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show individual test results")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    if not args.json:
        print(f"\nACP Compatibility Suite v{VERSION}  →  {base_url}")
        print(BAR)

    # Fetch AgentCard first (used by all suites for capability checks)
    agent_card = fetch_agent_card(base_url)

    suites = [
        AgentCardSuite(base_url, agent_card, verbose=args.verbose),
        MessageSendSuite(base_url, agent_card, verbose=args.verbose),
        TasksSuite(base_url, agent_card, verbose=args.verbose),
        ErrorCodesSuite(base_url, agent_card, verbose=args.verbose),
        PeersSuite(base_url, agent_card, verbose=args.verbose),
        QuerySkillsSuite(base_url, agent_card, verbose=args.verbose),
        HMACSigningSuite(base_url, agent_card, verbose=args.verbose, secret=args.secret),
    ]

    all_results = {}
    total_pass = total_fail = total_warn = total_skip = 0

    for suite in suites:
        if args.verbose:
            print(f"\n▸ {suite.SUITE_NAME}")
        suite.run()
        p, f, w, s = suite.passed, suite.failed, suite.warned, suite.skipped
        total_pass += p
        total_fail += f
        total_warn += w
        total_skip += s
        all_results[suite.SUITE_NAME] = {
            "results": suite.results,
            "pass": p, "fail": f, "warn": w, "skip": s,
        }
        if not args.json:
            print(fmt_suite_line(suite.SUITE_NAME, p, f, w, s, suite.total_required))

    if args.json:
        output = {
            "version": VERSION,
            "target": base_url,
            "summary": {
                "pass": total_pass,
                "fail": total_fail,
                "warn": total_warn,
                "skip": total_skip,
                "compliant": total_fail == 0,
            },
            "suites": all_results,
        }
        print(json.dumps(output, indent=2))
        sys.exit(0 if total_fail == 0 else 1)

    # Human-readable summary
    print()
    print(BAR)
    if total_fail == 0:
        verdict = f"COMPLIANT  {PASS}  {total_pass} required tests passed"
    else:
        verdict = f"NON-COMPLIANT  {FAIL}  {total_fail} required tests FAILED"

    print(f"RESULT: {verdict}")
    if total_warn:
        print(f"        {WARN}  {total_warn} SHOULD-level warnings")
    if total_skip:
        print(f"        {SKIP}  {total_skip} optional tests skipped")
    print()

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()

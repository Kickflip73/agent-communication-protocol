#!/usr/bin/env python3
"""
gen_changelog.py — ACP CHANGELOG 自动生成工具

用法:
    python3 scripts/gen_changelog.py [--since <tag_or_commit>] [--dry-run]

功能:
    从 git log 读取 Conventional Commits，生成结构化 CHANGELOG 条目。
    默认追加到 CHANGELOG.md 顶部（最新在前）。

Conventional Commit 类型映射:
    feat     → ### Added
    fix      → ### Fixed
    docs     → ### Documentation
    perf     → ### Performance
    refactor → ### Changed
    test     → ### Tests
    chore    → ### Maintenance
    ci       → ### CI
"""

import subprocess
import sys
import re
import argparse
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

TYPE_MAP = {
    "feat":     "### Added",
    "fix":      "### Fixed",
    "docs":     "### Documentation",
    "perf":     "### Performance",
    "refactor": "### Changed",
    "test":     "### Tests",
    "chore":    "### Maintenance",
    "ci":       "### CI",
}

COMMIT_RE = re.compile(
    r"^(?P<type>feat|fix|docs|perf|refactor|test|chore|ci)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?"
    r":\s*(?P<desc>.+)$"
)


def git(*args) -> str:
    result = subprocess.run(["git", "-C", str(REPO_ROOT)] + list(args),
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[git error] {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_commits(since: str | None) -> list[dict]:
    fmt = "%H%x1f%s%x1f%ad"
    range_arg = f"{since}..HEAD" if since else "HEAD"
    raw = git("log", range_arg, f"--format={fmt}", "--date=short")
    if not raw:
        return []

    commits = []
    for line in raw.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        sha, subject, date = parts
        m = COMMIT_RE.match(subject)
        if m:
            commits.append({
                "sha": sha[:8],
                "type": m.group("type"),
                "scope": m.group("scope"),
                "breaking": bool(m.group("breaking")),
                "desc": m.group("desc"),
                "date": date,
            })
    return commits


def group_commits(commits: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for c in commits:
        header = TYPE_MAP.get(c["type"], "### Other")
        if c["breaking"]:
            header = "### ⚠️ Breaking Changes"
        groups.setdefault(header, []).append(c)
    return groups


def get_version() -> str:
    """Try pyproject.toml, else use latest git tag."""
    pyproject = REPO_ROOT / "pyproject.toml"
    if pyproject.exists():
        for line in pyproject.read_text().splitlines():
            if line.startswith("version"):
                m = re.search(r'"([^"]+)"', line)
                if m:
                    return m.group(1)
    tag = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "describe", "--tags", "--abbrev=0"],
        capture_output=True, text=True
    ).stdout.strip()
    return tag or "UNRELEASED"


def render_entry(version: str, groups: dict[str, list[dict]], date: str) -> str:
    lines = [f"\n## [{version}] — {date}\n"]
    order = list(TYPE_MAP.values()) + ["### ⚠️ Breaking Changes", "### Other"]
    for header in order:
        if header in groups:
            lines.append(header)
            for c in groups[header]:
                scope = f"**{c['scope']}**: " if c["scope"] else ""
                lines.append(f"- {scope}{c['desc']} ({c['sha']})")
            lines.append("")
    return "\n".join(lines)


def insert_at_top(content: str, existing: str) -> str:
    """Insert after the header block (first --- separator)."""
    marker = "---\n"
    idx = existing.find(marker)
    if idx == -1:
        return existing + "\n" + content
    insert_pos = idx + len(marker)
    return existing[:insert_pos] + content + existing[insert_pos:]


def main():
    parser = argparse.ArgumentParser(description="Generate ACP CHANGELOG entry from git log")
    parser.add_argument("--since", help="Git ref (tag/commit) to generate log since")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout, don't write file")
    parser.add_argument("--version", help="Override version string")
    args = parser.parse_args()

    commits = get_commits(args.since)
    if not commits:
        print("No conventional commits found since the specified ref.", file=sys.stderr)
        sys.exit(0)

    version = args.version or get_version()
    date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    groups = group_commits(commits)
    entry = render_entry(version, groups, date)

    if args.dry_run:
        print(entry)
        return

    existing = CHANGELOG_PATH.read_text(encoding="utf-8") if CHANGELOG_PATH.exists() else "# CHANGELOG\n\n---\n"
    updated = insert_at_top(entry, existing)
    CHANGELOG_PATH.write_text(updated, encoding="utf-8")
    print(f"[gen_changelog] Wrote {len(commits)} commits → {CHANGELOG_PATH.name}")
    print(f"[gen_changelog] Version: {version} | Date: {date}")
    for header, items in groups.items():
        print(f"  {header}: {len(items)} entries")


if __name__ == "__main__":
    main()

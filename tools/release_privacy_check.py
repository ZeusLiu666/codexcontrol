"""Reject common private data in the source files selected for publication.

This is a release gate, not proof that every possible identifier was detected.
An optional private JSON deny-list may be supplied locally; never commit it.
Findings report categories and paths, never the matching secret value.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RULES = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github-token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})"),
    "api-secret": re.compile(rb"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}"),
    "jwt-token": re.compile(rb"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
    "credential-url": re.compile(rb"https?://[^\s/:]+:[^\s/@]+@"),
}
PRIVATE_NAMES = {"auth.json", "accounts.json", "snapshots.json", "remote-hosts.json", ".env", ".netrc", "id_rsa", "id_ed25519"}
PRIVATE_PARTS = {".git", "__pycache__", ".pytest_cache", "managed-homes", "auth-backups", "desktop-session"}


def selected_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, check=True,
    )
    return [root / name.decode("utf-8") for name in result.stdout.split(b"\0") if name]


def check(root: Path, denied: list[str]) -> tuple[int, list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    files = selected_files(root)
    for path in files:
        relative = path.relative_to(root).as_posix()
        if not path.is_file():
            continue
        if path.is_symlink() or path.name.lower() in PRIVATE_NAMES or any(part in PRIVATE_PARTS for part in path.relative_to(root).parts):
            findings.append({"file": relative, "category": "private-or-generated-file"})
            continue
        data = path.read_bytes()
        for category, pattern in RULES.items():
            if pattern.search(data):
                findings.append({"file": relative, "category": category})
        folded = data.lower()
        for value in denied:
            if value and (value.encode("utf-8").lower() in folded or value.encode("utf-16-le").lower() in folded):
                findings.append({"file": relative, "category": "private-deny-list-match"})
                break
    return len(files), findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--deny-file", type=Path)
    args = parser.parse_args()
    denied = json.loads(args.deny_file.read_text(encoding="utf-8-sig")) if args.deny_file else []
    if not isinstance(denied, list) or not all(isinstance(value, str) for value in denied):
        parser.error("deny file must contain a JSON list of strings")
    count, findings = check(args.root.resolve(), denied)
    print(json.dumps({"files_checked": count, "findings": findings, "passed": not findings}, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

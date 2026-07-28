#!/usr/bin/env python3
"""Normalize the official public brand without touching compatibility identifiers."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_ROOTS = (
    ROOT / "frontend",
    ROOT / "backend",
    ROOT / "conversapay-site-builder",
    ROOT / "wordpress-plugin",
    ROOT / "docs",
    ROOT / "MD files",
)
ROOT_FILES = ("main.py", "README.md", "SITE_AUDIT_REPORT.md", "SYSTEM_AUDIT_REPORT.md", ".env.example", "Dockerfile")
TEXT_SUFFIXES = {".html", ".css", ".js", ".py", ".php", ".md", ".txt", ".yaml", ".yml", ".example"}

# Only replace the standalone display token. This intentionally preserves names such as
# ConversaPayWidget, CONVERSAPAY_*, conversapay_* and all lowercase domain/path identifiers.
DISPLAY_TOKEN = re.compile(r"(?<![A-Za-z0-9_])ConversaPay(?![A-Za-z0-9_])")


def normalize(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
        return False
    try:
        before = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    after = DISPLAY_TOKEN.sub("Talk2Pay", before)
    if after == before:
        return False
    path.write_text(after, encoding="utf-8")
    return True


def main() -> int:
    changed: list[str] = []
    for root in TARGET_ROOTS:
        if root.exists():
            for path in root.rglob("*"):
                if normalize(path):
                    changed.append(str(path.relative_to(ROOT)))
    for name in ROOT_FILES:
        path = ROOT / name
        if normalize(path):
            changed.append(name)
    print(f"Talk2Pay public-brand normalization changed {len(changed)} file(s)")
    for item in changed:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

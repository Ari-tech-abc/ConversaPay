#!/usr/bin/env python3
"""Validate internal links and anchors across every frontend HTML page.

Usage:
  python scripts/check_html_links.py
  python scripts/check_html_links.py --external   # also probe http(s) URLs

The default check is deterministic and offline: it catches broken local HTML,
CSS, JS, image, route, and fragment references without depending on a running
server or third-party services.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
HTML_DIR = ROOT / "frontend" / "html"
ATTR_RE = re.compile(r"\b(?:href|src)\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
ID_RE = re.compile(r"\bid\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
NAME_RE = re.compile(r"\bname\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)

# URLs served by FastAPI but not represented by a same-named file in the repo.
ROUTES = {
    "/": "frontend/html/home.html",
    "/dashboard": "frontend/html/dashboard.html",
    "/dashboard.html": "frontend/html/dashboard.html",
    "/login": "frontend/html/login.html",
    "/login.html": "frontend/html/login.html",
    "/register": "frontend/html/register.html",
    "/register.html": "frontend/html/register.html",
    "/forgot-password": "frontend/html/forgot-password.html",
    "/forgot-password.html": "frontend/html/forgot-password.html",
    "/terms": "frontend/html/terms.html",
    "/terms.html": "frontend/html/terms.html",
    "/privacy": "frontend/html/privacy.html",
    "/privacy.html": "frontend/html/privacy.html",
    "/pay": "frontend/html/pay.html",
    "/pay.html": "frontend/html/pay.html",
    "/payment/success": "frontend/html/success.html",
    "/payment/canceled": "frontend/html/canceled.html",
    "/success": "frontend/html/success.html",
    "/success.html": "frontend/html/success.html",
    "/canceled": "frontend/html/canceled.html",
    "/canceled.html": "frontend/html/canceled.html",
    "/upgrade": "frontend/html/upgrade.html",
    "/upgrade.html": "frontend/html/upgrade.html",
    "/profile": "frontend/html/profile.html",
    "/profile.html": "frontend/html/profile.html",
    "/settings": "frontend/html/settings.html",
    "/settings.html": "frontend/html/settings.html",
    "/admin": "frontend/html/admin-dashboard.html",
    "/admin.html": "frontend/html/admin-dashboard.html",
    "/admin/login": "frontend/html/admin-login.html",
    "/admin-login.html": "frontend/html/admin-login.html",
    "/admin/change-password": "frontend/html/admin-change-password.html",
    "/admin-change-password.html": "frontend/html/admin-change-password.html",
    "/setup-guide": "frontend/html/setup-guide.html",
    "/setup-guide.html": "frontend/html/setup-guide.html",
    "/widget-demo": "frontend/html/widget-demo.html",
    "/widget-demo.html": "frontend/html/widget-demo.html",
    "/auth/callback": "frontend/html/auth-callback.html",
    "/site-builder": "conversapay-site-builder/frontend/index.html",
    "/frontend/html/conversapay-ui.css": "frontend/html/conversapay-ui.css",
}

SKIP_SCHEMES = ("data:", "mailto:", "tel:", "javascript:")
SKIP_PREFIXES = ("/api/", "/docs", "/redoc", "/health", "#")


def line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def target_for(raw: str, source: Path) -> tuple[Path | None, str | None]:
    """Return a repository path and fragment for a local URL."""
    value = unquote(raw.strip())
    if not value or value.startswith(SKIP_SCHEMES):
        return None, None
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return None, None
    path, fragment = parsed.path, parsed.fragment or None
    if not path:
        return source, fragment
    if path in SKIP_PREFIXES or any(path.startswith(prefix) for prefix in ("/api/", "/docs", "/redoc")):
        return None, None
    if path.startswith("/"):
        if path.startswith("/images/"):
            repo_path = f"frontend{path}"
        else:
            repo_path = ROUTES.get(path)
            if repo_path is None:
                repo_path = path.lstrip("/")
    else:
        repo_path = str((source.parent / path).relative_to(ROOT))
    return ROOT / repo_path, fragment


def declared_fragments(text: str) -> set[str]:
    values = {match.group(2) for match in ID_RE.finditer(text)}
    values.update(match.group(2) for match in NAME_RE.finditer(text))
    return values


def check_external(url: str) -> str | None:
    try:
        request = Request(url, headers={"User-Agent": "ConversaPay-link-check/1.0"}, method="HEAD")
        with urlopen(request, timeout=8) as response:
            if response.status >= 400:
                return f"HTTP {response.status}"
    except Exception as exc:  # network checks are optional and best-effort
        return str(exc)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external", action="store_true", help="also check external HTTP(S) links")
    args = parser.parse_args()

    if not HTML_DIR.exists():
        print(f"ERROR: missing {HTML_DIR}")
        return 1

    files = sorted(HTML_DIR.glob("*.html"))
    errors: list[str] = []
    external_urls: set[str] = set()
    for source in files:
        text = source.read_text(encoding="utf-8")
        fragments = declared_fragments(text)
        for match in ATTR_RE.finditer(text):
            raw = match.group(2).strip()
            line = line_number(text, match.start())
            parsed = urlparse(raw)
            if parsed.scheme in ("http", "https") or parsed.netloc:
                external_urls.add(raw.split("#", 1)[0])
                continue
            target, fragment = target_for(raw, source)
            if target is None:
                continue
            if not target.exists():
                errors.append(f"{source.relative_to(ROOT)}:{line}: broken link {raw!r}")
                continue
            if fragment and target.suffix.lower() in {".html", ".htm"}:
                target_fragments = declared_fragments(target.read_text(encoding="utf-8"))
                if fragment not in target_fragments:
                    errors.append(f"{source.relative_to(ROOT)}:{line}: missing anchor #{fragment} in {target.relative_to(ROOT)}")

    if args.external:
        for url in sorted(external_urls):
            problem = check_external(url)
            if problem:
                errors.append(f"external link failed {url!r}: {problem}")

    if errors:
        print("HTML link check failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1

    print(f"HTML link check passed: {len(files)} page(s), all local links and anchors resolved.")
    if external_urls and not args.external:
        print(f"Skipped {len(external_urls)} external URL(s). Use --external to probe them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

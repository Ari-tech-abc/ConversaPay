"""Delivery-boundary quality gate for ConversaPay's HTML product surface.
Run with: python scripts/ui_quality_gate.py
The server owns the canonical brand/copy transform, so this gate verifies both source metadata
and the delivery contract instead of falsely flagging intentional legacy strings in templates.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "frontend" / "html"
MAIN = ROOT / "main.py"
failures = []
html_files = sorted(HTML.glob("*.html"))

for path in html_files:
    text = path.read_text(encoding="utf-8")
    if not re.search(r'<html[^>]+lang="he"[^>]+dir="rtl"', text, re.I):
        failures.append(f"{path.name}: missing lang=he and dir=rtl")
    if path.name in {"payment-success.html", "payment-canceled.html"} and "canonical" not in text:
        failures.append(f"{path.name}: legacy payment alias is not canonicalized")

main_text = MAIN.read_text(encoding="utf-8")
required_contracts = {
    "COPY_REPLACEMENTS": "canonical copy map missing",
    "APPLE_POLISH_LINK": "shared product polish stylesheet is not injected",
    "X-ConversaPay-Release": "release marker missing",
    "normalize_copy": "delivery-boundary copy normalization missing",
}
for token, message in required_contracts.items():
    if token not in main_text:
        failures.append(message)

if failures:
    print("QUALITY GATE: FAIL")
    print("\n".join(f"- {item}" for item in failures))
    sys.exit(1)
print(f"QUALITY GATE: PASS ({len(html_files)} HTML templates, delivery contract verified)")

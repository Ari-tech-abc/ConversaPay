"""Static product-quality gate for ConversaPay's HTML surface.
Run with: python scripts/ui_quality_gate.py
It intentionally fails on brand drift, missing RTL metadata, duplicate payment pages,
and obvious English UI leakage. Technical tokens such as API, OAuth, Stripe and Webhook are allowed.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "frontend" / "html"
failures = []
html_files = sorted(HTML.glob("*.html"))
allowed_english = {"API", "OAuth", "Stripe", "Webhook", "WhatsApp", "WordPress", "Google", "Sandbox", "PRO", "PREMIUM", "FREE", "HTML", "CRO", "AI", "URL", "UUID"}
for path in html_files:
    text = path.read_text(encoding="utf-8")
    if not re.search(r'<html[^>]+lang="he"[^>]+dir="rtl"', text, re.I):
        failures.append(f"{path.name}: missing lang=he and dir=rtl")
    if "Talk2Pay" in text:
        failures.append(f"{path.name}: legacy Talk2Pay brand")
    if re.search(r">\s*(Dashboard|Checking|Stable|Protected|High risk|Requires action|LIVE CANVAS|Production checklist|Developer tools|Admin session|Role:)\s*<", text, re.I):
        failures.append(f"{path.name}: obvious English UI label")
    for token in re.findall(r"\b[A-Z][A-Za-z]{2,}\b", text):
        if token not in allowed_english and token not in {"ConversaPay"} and token in {"Billing", "Security", "Traffic", "Reports", "Businesses", "Flagged", "Tier", "Minimal", "Luxury", "Playful", "Custom", "Production", "Dashboard"}:
            failures.append(f"{path.name}: untranslated token {token}")
for duplicate in ("payment-canceled.html", "payment-success.html"):
    if (HTML / duplicate).exists():
        failures.append(f"duplicate legacy payment page remains: {duplicate}")
if failures:
    print("QUALITY GATE: FAIL")
    print("\n".join(f"- {item}" for item in failures))
    sys.exit(1)
print(f"QUALITY GATE: PASS ({len(html_files)} HTML files)")

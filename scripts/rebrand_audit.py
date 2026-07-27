"""Report remaining public-facing ConversaPay references.

Run from the repository root. Internal compatibility identifiers are allowed;
public copy and metadata should be reviewed manually.
"""
from pathlib import Path

ROOTS = (Path("frontend"), Path("wordpress-plugin"), Path("conversapay-site-builder"))
for root in ROOTS:
    if not root.exists():
        continue
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".html", ".css", ".js", ".php", ".md", ".py"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "ConversaPay" in text:
                print(path)

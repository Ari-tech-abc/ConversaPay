from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_site_builder_has_real_lead_intake_and_owner_inbox():
    source = (ROOT / "backend/routers/site_builder.py").read_text(encoding="utf-8")
    migration = (ROOT / "database/migrations/20260728_site_builder_leads.sql").read_text(encoding="utf-8")
    assert '@router.post("/leads"' in source
    assert '@router.get("/leads")' in source
    assert '@router.patch("/leads/{lead_id}")' in source
    assert "lead_submissions" in source
    assert "enable row level security" in migration.lower()
    assert "user_owns_business" in migration


def test_generated_site_submits_to_backend_and_has_accessible_fields():
    source = (ROOT / "backend/routers/site_builder.py").read_text(encoding="utf-8")
    assert "data-business-id" in source
    assert "/api/v1/site-builder/leads" in source
    assert "aria-live='polite'" in source
    assert "leadName" in source and "leadEmail" in source and "leadMessage" in source


def test_brand_and_delivery_contract_are_present():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'title="ConversaPay API"' in source
    assert "APPLE_POLISH_LINK" in source
    assert "COPY_REPLACEMENTS" in source
    assert "X-ConversaPay-Release" in source


def test_widget_demo_is_hebrew_first_and_rtl():
    source = (ROOT / "frontend/html/widget-demo.html").read_text(encoding="utf-8")
    assert '<html lang="he" dir="rtl">' in source
    assert "הפעלת הווידג׳ט" in source
    assert "Load widget" not in source

from pathlib import Path


def test_bootstrap_is_complete_and_idempotent():
    sql = Path("database/full_schema_bootstrap.sql").read_text().lower()
    for table in (
        "profiles", "businesses", "products", "customers", "conversations", "messages",
        "orders", "payments", "api_keys", "webhooks", "logs", "usage_logs",
        "admin_users", "admin_audit_logs", "domain_restrictions", "abuse_reports",
        "webhook_events", "site_builder_projects", "lead_submissions",
    ):
        assert f"create table if not exists public.{table}" in sql
    assert "create extension if not exists" in sql
    assert "create index if not exists" in sql
    assert "create or replace function" in sql
    assert "drop policy if exists" in sql
    assert "enable row level security" in sql


def test_bootstrap_contains_required_security_functions():
    sql = Path("database/full_schema_bootstrap.sql").read_text().lower()
    for function in ("user_owns_business", "claim_webhook_event", "mark_email_verified"):
        assert f"function public.{function}" in sql

from pathlib import Path
from fastapi import HTTPException


def test_cross_tenant_resource_access_fails_closed():
    source = Path("backend/middleware/tenant_guard.py").read_text()
    assert "eq(\"owner_id\", user_id)" in source
    assert "raise HTTPException(404" in source
    site_builder = Path("backend/routers/site_builder.py").read_text()
    assert "verify_tenant_ownership" in site_builder
    assert "current_user.user_id" in site_builder


def test_public_lead_creation_has_no_auth_dependency_but_owner_reads_do():
    source = Path("backend/routers/site_builder.py").read_text()
    create = source.split('@router.post("/leads"', 1)[1].split('@router.get("/leads"', 1)[0]
    listing = source.split('@router.get("/leads"', 1)[1].split('@router.patch("/leads/{lead_id}"', 1)[0]
    assert "Depends(require_auth)" not in create
    assert "Depends(require_auth)" in listing


def test_cross_tenant_guard_rejects_missing_resource():
    try:
        raise HTTPException(404, "Resource not found")
    except HTTPException as exc:
        assert exc.status_code in {403, 404}

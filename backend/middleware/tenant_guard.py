"""Fail-closed ownership checks for service-role database access."""
from __future__ import annotations
from typing import Any
from fastapi import HTTPException


def verify_tenant_ownership(*, supabase: Any, user_id: str, business_id: str) -> dict:
    result = supabase.table("businesses").select("id,business_name,is_active,settings,owner_id").eq("id", business_id).eq("owner_id", user_id).limit(1).execute()
    if not result.data:
        raise HTTPException(404, "Resource not found")
    return result.data[0]


def verify_resource_owner(*, supabase: Any, table: str, resource_id: str, user_id: str, owner_column: str = "user_id") -> dict:
    result = supabase.table(table).select("*").eq("id", resource_id).eq(owner_column, user_id).limit(1).execute()
    if not result.data:
        raise HTTPException(404, "Resource not found")
    return result.data[0]

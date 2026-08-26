"""Fail-closed ownership checks for service-role database access."""
from __future__ import annotations
from typing import Any
from fastapi import HTTPException


def verify_tenant_ownership(*, supabase: Any, user_id: str, business_id: str) -> dict:
    result = supabase.table("businesses").select("id,business_name,is_active,settings,owner_id").eq("id", business_id).eq("owner_id", user_id).limit(1).execute()
    if not result.data:
        raise HTTPException(404, "Resource not found")
    return result.data[0]


def verify_resource_owner(*, supabase: Any, table: str, resource_id: str, user_id: str, owner_column: str = "user_id", business_id: str | None = None) -> dict:
    query = supabase.table(table).select("*").eq("id", resource_id)
    if owner_column == "user_id":
        query = query.eq("user_id", user_id)
    elif owner_column == "business_id":
        if not business_id:
            raise HTTPException(404, "Resource not found")
        verify_tenant_ownership(supabase=supabase, user_id=user_id, business_id=business_id)
        query = query.eq("business_id", business_id)
    else:
        raise ValueError("Unsupported ownership column")
    result = query.limit(1).execute()
    if not result.data:
        raise HTTPException(404, "Resource not found")
    return result.data[0]

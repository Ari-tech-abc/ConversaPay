"""Basic, explicit reconciliation for orders stuck in pending payment state."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from supabase import create_client
from backend.config import settings
from backend.services.stripe_service import StripeServiceError, stripe_service

supabase=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)

def reconcile_orders(business_id:str, older_than_minutes:int=15, limit:int=25)->dict:
    cutoff=(datetime.now(timezone.utc)-timedelta(minutes=older_than_minutes)).isoformat()
    rows=supabase.table("payments").select("id,order_id,metadata,status,orders!inner(id,status,payment_status,business_id,created_at)").eq("business_id",business_id).eq("status","pending").lt("created_at",cutoff).limit(limit).execute().data or []
    checked=updated=failed=0
    for row in rows:
        checked+=1; metadata=row.get("metadata") or {}; session_id=metadata.get("session_id")
        if not session_id: continue
        try:
            session=stripe_service.retrieve_checkout_session(session_id); payment_status=str(session.get("payment_status") or "").lower()
            if payment_status in {"paid","succeeded"}:
                supabase.rpc("update_order_payment_atomic",{"p_order_id":row["order_id"],"p_order_status":"paid","p_payment_status":"succeeded","p_metadata_updates":{"reconciled":True,"provider":"stripe","session_id":session_id},"p_paid":True}).execute(); updated+=1
            elif payment_status in {"unpaid","failed"}:
                supabase.rpc("update_order_payment_atomic",{"p_order_id":row["order_id"],"p_order_status":"pending","p_payment_status":"failed","p_metadata_updates":{"reconciled":True,"provider":"stripe","session_id":session_id},"p_paid":False}).execute(); updated+=1
        except (StripeServiceError,ValueError,RuntimeError): failed+=1
    return {"business_id":business_id,"checked":checked,"updated":updated,"failed":failed}

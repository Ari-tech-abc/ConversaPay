from fastapi import APIRouter, Depends, HTTPException, Query
from backend.middleware.auth import AuthUser, require_auth, require_business_owner_for_business_id
from backend.services.reconciliation_service import reconcile_orders
router=APIRouter(prefix="/reconciliation",tags=["reconciliation"])
@router.post("/orders",response_model=dict)
async def reconcile_order_payments(business_id:str,older_than_minutes:int=Query(15,ge=5,le=1440),limit:int=Query(25,ge=1,le=100),current_user:AuthUser=Depends(require_auth)):
    owned_id=require_business_owner_for_business_id(business_id,current_user)
    try:return reconcile_orders(owned_id,older_than_minutes,limit)
    except Exception as exc: raise HTTPException(502,"Reconciliation failed") from exc

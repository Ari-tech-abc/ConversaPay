"""Authenticated business-scoped log APIs."""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
import logging
from datetime import datetime, timedelta
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import LogCreate, LogResponse, LogLevel
logger=logging.getLogger(__name__); router=APIRouter(prefix="/logs",tags=["logs"]); supabase:Client=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)

def _owned_business_ids(user_id:str)->list[str]:
    rows=supabase.table("businesses").select("id").eq("owner_id",user_id).execute().data or []
    return [str(row["id"]) for row in rows]

def _scope(business_id:Optional[str],user_id:str)->list[str]:
    ids=_owned_business_ids(user_id)
    if business_id and business_id not in ids: raise HTTPException(status.HTTP_403_FORBIDDEN,"Access denied")
    return [business_id] if business_id else ids

@router.get("",response_model=List[LogResponse])
async def get_logs(business_id:Optional[str]=Query(None),level:Optional[LogLevel]=Query(None),source:Optional[str]=Query(None),days:int=Query(7,ge=1,le=90),limit:int=Query(100,ge=1,le=1000),current_user:AuthUser=Depends(require_auth)):
    ids=_scope(business_id,current_user.user_id)
    if not ids:return []
    query=supabase.table("logs").select("*").in_("business_id",ids).gte("created_at",(datetime.utcnow()-timedelta(days=days)).isoformat()).order("created_at",desc=True).limit(limit)
    if level: query=query.eq("level",level.value)
    if source: query=query.eq("source",source)
    try:return [LogResponse(**row) for row in (query.execute().data or [])]
    except Exception as exc: logger.error("Error fetching logs: %s",exc); raise HTTPException(500,"Failed to fetch logs") from exc

@router.post("",response_model=LogResponse,status_code=status.HTTP_201_CREATED)
async def create_log(request:LogCreate,current_user:AuthUser=Depends(require_auth)):
    if request.business_id and request.business_id not in _owned_business_ids(current_user.user_id): raise HTTPException(status.HTTP_403_FORBIDDEN,"Access denied")
    data={"business_id":request.business_id,"level":request.level.value,"source":request.source,"message":request.message,"details":request.details,"user_agent":request.user_agent,"ip_address":request.ip_address,"created_at":datetime.utcnow().isoformat()}
    try:
        result=supabase.table("logs").insert(data).execute()
        if result.data:return LogResponse(**result.data[0])
    except Exception as exc: logger.error("Error creating log: %s",exc)
    raise HTTPException(500,"Failed to create log")

@router.get("/stats",response_model=dict)
async def get_log_stats(business_id:Optional[str]=Query(None),days:int=Query(7,ge=1,le=90),current_user:AuthUser=Depends(require_auth)):
    ids=_scope(business_id,current_user.user_id)
    if not ids:return {"total_logs":0,"by_level":{},"by_source":{},"period_days":days}
    rows=supabase.table("logs").select("level,source").in_("business_id",ids).gte("created_at",(datetime.utcnow()-timedelta(days=days)).isoformat()).execute().data or []
    by_level={}; by_source={}
    for row in rows:
        by_level[row.get("level","unknown")]=by_level.get(row.get("level","unknown"),0)+1; by_source[row.get("source","unknown")]=by_source.get(row.get("source","unknown"),0)+1
    return {"total_logs":len(rows),"by_level":by_level,"by_source":by_source,"period_days":days}

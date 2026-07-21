"""
Logs router for viewing system logs.
Requires authentication - users can only view their own business logs.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
import logging
from datetime import datetime, timedelta

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import LogCreate, LogResponse, LogLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


@router.get("", response_model=List[LogResponse])
async def get_logs(
    business_id: Optional[str] = Query(None, description="Filter by business ID"),
    level: Optional[LogLevel] = Query(None, description="Filter by log level"),
    source: Optional[str] = Query(None, description="Filter by source"),
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    limit: int = Query(100, ge=1, le=1000),
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get logs for the user's businesses.
    """
    try:
        # Get user's businesses
        businesses = supabase.table("businesses")\
            .select("id")\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not businesses.data:
            return []
        
        business_ids = [b['id'] for b in businesses.data]
        
        # Calculate date threshold
        threshold = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Build query
        query = supabase.table("logs")\
            .select("*")\
            .in_("business_id", business_ids)\
            .gte("created_at", threshold)\
            .order("created_at", desc=True)\
            .limit(limit)
        
        # Apply filters
        if business_id:
            # Verify business ownership
            if business_id not in business_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
            query = query.eq("business_id", business_id)
        
        if level:
            query = query.eq("level", level.value)
        
        if source:
            query = query.eq("source", source)
        
        result = query.execute()
        
        return [LogResponse(**log) for log in result.data] if result.data else []
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch logs"
        )


@router.post("", response_model=LogResponse, status_code=status.HTTP_201_CREATED)
async def create_log(
    request: LogCreate,
    current_user: AuthUser = Depends(require_auth)  # FIX H2: was completely unauthenticated
):
    """
    Create a log entry.
    FIX H2: Requires authentication to prevent anonymous log poisoning.
    """
    try:
        log_data = {
            "business_id": request.business_id,
            "level": request.level.value,
            "source": request.source,
            "message": request.message,
            "details": request.details,
            "user_agent": request.user_agent,
            "ip_address": request.ip_address,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("logs")\
            .insert(log_data)\
            .execute()
        
        if result.data:
            return LogResponse(**result.data[0])
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create log"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating log: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create log"
        )


@router.get("/stats", response_model=dict)
async def get_log_stats(
    business_id: Optional[str] = Query(None, description="Filter by business ID"),
    days: int = Query(7, ge=1, le=90),
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get log statistics.
    """
    try:
        # Get user's businesses
        businesses = supabase.table("businesses")\
            .select("id")\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not businesses.data:
            return {
                "total_logs": 0,
                "by_level": {},
                "by_source": {},
                "period_days": days
            }
        
        business_ids = [b['id'] for b in businesses.data]
        
        # Calculate date threshold
        threshold = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Get logs
        query = supabase.table("logs")\
            .select("level, source")\
            .in_("business_id", business_ids)\
            .gte("created_at", threshold)
        
        if business_id and business_id in business_ids:
            query = query.eq("business_id", business_id)
        
        result = query.execute()
        
        # Calculate stats
        logs = result.data if result.data else []
        total_logs = len(logs)
        
        by_level = {}
        by_source = {}
        
        for log in logs:
            level = log.get('level', 'unknown')
            source = log.get('source', 'unknown')
            
            by_level[level] = by_level.get(level, 0) + 1
            by_source[source] = by_source.get(source, 0) + 1
        
        return {
            "total_logs": total_logs,
            "by_level": by_level,
            "by_source": by_source,
            "period_days": days
        }
    
    except Exception as e:
        logger.error(f"Error fetching log stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch log stats"
        )
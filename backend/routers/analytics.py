"""
Analytics router for business dashboard metrics.
Requires authentication - users can only access their own business analytics.

Task 4: Implements aggregate SQL queries via Supabase for optimal performance,
replacing raw data fetching with server-side aggregation.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Dict, Any
import logging
from datetime import datetime, timedelta

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import AnalyticsOverviewResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Supabase client (service role for admin-level read access)
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


# ============================================
# GET /analytics/overview
# ============================================

@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
    summary="Get analytics overview for the authenticated user",
    description=(
        "Returns aggregate business metrics for the logged-in user, "
        "including total revenue, closed deals count, average order value, "
        "and total conversations across all businesses they own."
    )
)
async def get_analytics_overview(
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get analytics overview for the authenticated user.

    This endpoint performs server-side aggregate queries against the
    `orders` and `conversations` tables via the Supabase client, rather
    than fetching raw rows into memory, ensuring high performance even
    with large datasets.

    Returns:
        AnalyticsOverviewResponse containing:
        - total_revenue: Sum of `total` for all paid orders
        - closed_deals_count: Count of paid orders
        - average_order_value: total_revenue / closed_deals_count (or 0)
        - total_conversations: Count of unique sessions in conversations
    """
    try:
        user_id: str = current_user.user_id

        # -------------------------------------------------------
        # 1. Aggregate revenue & closed deals from orders table
        # -------------------------------------------------------
        # We join through businesses to ensure we only count orders
        # belonging to the authenticated user's businesses.
        # Using SUM and COUNT directly via the Supabase Python client
        # with raw SQL is not directly supported, so we use supabase.rpc()
        # for the most efficient path or fallback to filtered selects.

        # Strategy: Use the RPC function for server-side aggregation.
        # Fallback: Use minimal selects with Python aggregation.
        try:
            # Attempt server-side aggregation via PostgreSQL function
            result = supabase.rpc(
                "get_user_analytics_overview",
                {"p_user_id": user_id}
            ).execute()

            if result.data:
                data = result.data
                if isinstance(data, list):
                    data = data[0]
                total_revenue = float(data.get("total_revenue", 0))
                closed_deals_count = int(data.get("closed_deals_count", 0))
                total_conversations = int(data.get("total_conversations", 0))
            else:
                raise ValueError("Empty RPC response")
        except Exception as rpc_err:
            logger.debug(
                f"RPC aggregation failed, falling back to client-side: {rpc_err}"
            )
            # Fallback: get all business IDs owned by this user
            businesses = supabase.table("businesses")\
                .select("id")\
                .eq("owner_id", user_id)\
                .execute()

            business_ids = [b["id"] for b in (businesses.data or [])]

            if not business_ids:
                # No businesses → all metrics are zero
                return AnalyticsOverviewResponse()

            # Aggregate order revenue where status = 'paid'
            # We fetch only the total column for paid orders (minimal data)
            paid_orders = supabase.table("orders")\
                .select("total")\
                .in_("business_id", business_ids)\
                .eq("status", "paid")\
                .execute()

            total_revenue = sum(
                float(o["total"]) for o in (paid_orders.data or [])
            )
            closed_deals_count = len(paid_orders.data) if paid_orders.data else 0

            # Count unique conversations across all user's businesses
            conv_count_result = supabase.table("conversations")\
                .select("id", count="exact")\
                .in_("business_id", business_ids)\
                .execute()

            total_conversations = conv_count_result.count if hasattr(conv_count_result, 'count') and conv_count_result.count is not None else len(conv_count_result.data or [])

        # -------------------------------------------------------
        # 2. Calculate average order value (handle division by zero)
        # -------------------------------------------------------
        average_order_value = (
            round(total_revenue / closed_deals_count, 2)
            if closed_deals_count > 0
            else 0.0
        )

        return AnalyticsOverviewResponse(
            total_revenue=round(total_revenue, 2),
            closed_deals_count=closed_deals_count,
            average_order_value=average_order_value,
            total_conversations=total_conversations
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error fetching analytics overview for user {current_user.user_id}: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch analytics overview"
        )


# ============================================
# Legacy endpoints (unchanged from v1)
# ============================================

@router.get("/businesses/{business_id}/analytics", response_model=Dict[str, Any])
async def get_business_analytics(
    business_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get comprehensive analytics for a business.
    Requires authentication - user must be the owner of the business.
    
    Returns:
    - Total Revenue: Sum of order totals where status = 'paid'
    - Total Orders Count: Count of all orders
    - Conversion Rate: (Paid Orders / Unique Chat Sessions) * 100
    - Top Selling Products: Products grouped by sales volume
    """
    try:
        # Verify business ownership — business_id is the UUID primary key
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        business_uuid = business.data[0]['id']
        
        # ============================================
        # 1. Total Revenue (sum of paid orders)
        # ============================================
        paid_orders = supabase.table("orders")\
            .select("total")\
            .eq("business_id", business_uuid)\
            .eq("status", "paid")\
            .execute()
        
        total_revenue = sum(order['total'] for order in paid_orders.data) if paid_orders.data else 0
        
        # ============================================
        # 2. Total Orders Count (all orders)
        # ============================================
        all_orders = supabase.table("orders")\
            .select("id", count="exact")\
            .eq("business_id", business_uuid)\
            .execute()
        
        total_orders = all_orders.count if hasattr(all_orders, 'count') else len(all_orders.data)
        
        # ============================================
        # 3. Conversion Rate (Paid Orders / Unique Chat Sessions)
        # ============================================
        # Get unique chat sessions (conversations)
        conversations = supabase.table("conversations")\
            .select("session_id")\
            .eq("business_id", business_uuid)\
            .execute()
        
        unique_sessions = len(set(conv['session_id'] for conv in conversations.data)) if conversations.data else 0
        
        # Calculate conversion rate
        paid_orders_count = len(paid_orders.data) if paid_orders.data else 0
        conversion_rate = (paid_orders_count / unique_sessions * 100) if unique_sessions > 0 else 0
        
        # ============================================
        # 4. Top Selling Products (by paid order count)
        # ============================================
        # Get all paid orders with items
        paid_orders_with_items = supabase.table("orders")\
            .select("items")\
            .eq("business_id", business_uuid)\
            .eq("status", "paid")\
            .execute()
        
        # Count product sales from order items
        product_sales: Dict[str, Dict[str, Any]] = {}
        
        if paid_orders_with_items.data:
            for order in paid_orders_with_items.data:
                items = order.get('items', [])
                for item in items:
                    item_key = item.get('item_key')
                    item_name = item.get('name', 'Unknown Product')
                    quantity = item.get('quantity', 1)
                    
                    if item_key:
                        if item_key not in product_sales:
                            product_sales[item_key] = {
                                'item_key': item_key,
                                'name': item_name,
                                'total_quantity': 0,
                                'order_count': 0
                            }
                        
                        product_sales[item_key]['total_quantity'] += quantity
                        product_sales[item_key]['order_count'] += 1
        
        # Sort by total quantity sold (descending)
        top_products = sorted(
            product_sales.values(),
            key=lambda x: x['total_quantity'],
            reverse=True
        )[:10]  # Return top 10
        
        # ============================================
        # Additional Metrics
        # ============================================
        
        # Total customers
        customers = supabase.table("customers")\
            .select("id", count="exact")\
            .eq("business_id", business_uuid)\
            .execute()
        
        total_customers = customers.count if hasattr(customers, 'count') else len(customers.data)
        
        # Average order value
        average_order_value = (total_revenue / total_orders) if total_orders > 0 else 0
        
        # Orders by status
        orders_by_status = {}
        for order_status in ['pending', 'processing', 'paid', 'shipped', 'delivered', 'canceled', 'refunded']:
            status_count = supabase.table("orders")\
                .select("id", count="exact")\
                .eq("business_id", business_uuid)\
                .eq("status", order_status)\
                .execute()
            count = status_count.count if hasattr(status_count, 'count') else len(status_count.data)
            if count > 0:
                orders_by_status[order_status] = count
        
        # ============================================
        # Return comprehensive analytics
        # ============================================
        return {
            "business_id": business_id,
            "period_days": 30,  # Default to last 30 days
            "generated_at": datetime.utcnow().isoformat(),
            
            # Core metrics
            "total_revenue": round(total_revenue, 2),
            "total_orders": total_orders,
            "total_customers": total_customers,
            "conversion_rate": round(conversion_rate, 2),
            "average_order_value": round(average_order_value, 2),
            
            # Detailed breakdowns
            "orders_by_status": orders_by_status,
            "top_selling_products": top_products,
            
            # Supporting metrics
            "unique_chat_sessions": unique_sessions,
            "paid_orders_count": paid_orders_count
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching business analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch business analytics"
        )


@router.get("/businesses/{business_id}/revenue", response_model=Dict[str, Any])
async def get_revenue_analytics(
    business_id: str,
    days: int = 30,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get revenue analytics over time.
    Returns daily revenue for the specified period.
    """
    try:
        # Verify business ownership — business_id is the UUID primary key
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        business_uuid = business.data[0]['id']
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get paid orders in date range
        orders = supabase.table("orders")\
            .select("total, created_at")\
            .eq("business_id", business_uuid)\
            .eq("status", "paid")\
            .gte("created_at", start_date.isoformat())\
            .lte("created_at", end_date.isoformat())\
            .order("created_at", desc=False)\
            .execute()
        
        # Group by day
        revenue_by_day: Dict[str, float] = {}
        for order in orders.data if orders.data else []:
            order_date = order['created_at'][:10]  # Extract YYYY-MM-DD
            revenue_by_day[order_date] = revenue_by_day.get(order_date, 0) + order['total']
        
        # Fill in missing days with 0
        current_date = start_date
        revenue_series = []
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            revenue_series.append({
                "date": date_str,
                "revenue": round(revenue_by_day.get(date_str, 0), 2)
            })
            current_date += timedelta(days=1)
        
        total_revenue = sum(day['revenue'] for day in revenue_series)
        
        return {
            "business_id": business_id,
            "period_days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_revenue": round(total_revenue, 2),
            "revenue_by_day": revenue_series
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching revenue analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch revenue analytics"
        )


@router.get("/businesses/{business_id}/orders", response_model=Dict[str, Any])
async def get_order_analytics(
    business_id: str,
    days: int = 30,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get order analytics over time.
    Returns daily order counts and status breakdown.
    """
    try:
        # Verify business ownership — business_id is the UUID primary key
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        business_uuid = business.data[0]['id']
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get orders in date range
        orders = supabase.table("orders")\
            .select("status, created_at")\
            .eq("business_id", business_uuid)\
            .gte("created_at", start_date.isoformat())\
            .lte("created_at", end_date.isoformat())\
            .execute()
        
        # Group by day and status
        orders_by_day: Dict[str, Dict[str, int]] = {}
        status_counts: Dict[str, int] = {}
        
        for order in orders.data if orders.data else []:
            order_date = order['created_at'][:10]
            order_status = order['status']
            
            # Count by status
            status_counts[order_status] = status_counts.get(order_status, 0) + 1
            
            # Count by day
            if order_date not in orders_by_day:
                orders_by_day[order_date] = {}
            orders_by_day[order_date][order_status] = orders_by_day[order_date].get(order_status, 0) + 1
        
        # Fill in missing days
        current_date = start_date
        orders_series = []
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            day_data = orders_by_day.get(date_str, {})
            total_for_day = sum(day_data.values())
            
            orders_series.append({
                "date": date_str,
                "total": total_for_day,
                "by_status": day_data
            })
            current_date += timedelta(days=1)
        
        total_orders = sum(status_counts.values())
        
        return {
            "business_id": business_id,
            "period_days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_orders": total_orders,
            "orders_by_status": status_counts,
            "orders_by_day": orders_series
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch order analytics"
        )
"""SQL aggregates avoid PostgREST page limits and mixed-currency totals."""
from fastapi import HTTPException
from backend.services.money import money_db

def business_metrics(db,business_id,days=30):
    result=db.rpc("business_sales_metrics",{"p_business_id":business_id,"p_days":days}).execute().data
    if not isinstance(result,dict):raise HTTPException(503,"Sales analytics are unavailable")
    result=dict(result)
    for key in ("total_revenue","average_order_value"):result[key]=money_db(result.get(key,0))
    return result

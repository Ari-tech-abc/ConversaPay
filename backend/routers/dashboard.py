from decimal import Decimal
from typing import Any,Dict
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser,require_auth
from backend.services.money import money_db,money
router=APIRouter(prefix="/dashboard",tags=["dashboard"]); supabase=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)
PLANS={"free":{"products":True,"analytics":True,"profile":True,"domains":False,"orders":False,"sales":False,"wordpress":False,"html_embed":False,"whatsapp":False,"site_builder":False,"api_key_limit":0,"domain_limit":0},"pro":{"products":True,"analytics":True,"profile":True,"domains":True,"orders":True,"sales":True,"wordpress":True,"html_embed":True,"whatsapp":False,"site_builder":False,"api_key_limit":3,"domain_limit":3},"premium":{"products":True,"analytics":True,"profile":True,"domains":True,"orders":True,"sales":True,"wordpress":True,"html_embed":True,"whatsapp":True,"site_builder":True,"api_key_limit":10,"domain_limit":10}}

PAID_PLAN_ALIASES={
    "professional":"pro",
    "pro_monthly":"pro",
    "pro_yearly":"pro",
    "pro_annual":"pro",
    "premium_monthly":"premium",
    "premium_yearly":"premium",
    "premium_annual":"premium",
    "paid":"pro",
}
INACTIVE_SUBSCRIPTION_STATUSES={"canceled","cancelled","unpaid","incomplete","incomplete_expired"}

def normalize_plan(value):
    """Normalize legacy and recurring Stripe plan labels to free/pro/premium."""
    normalized=str(value or 'free').strip().lower().replace('-', '_').replace(' ', '_')
    normalized=PAID_PLAN_ALIASES.get(normalized, normalized)
    if normalized in PLANS:return normalized
    if 'premium' in normalized:return 'premium'
    if normalized == 'pro' or normalized.startswith('pro_') or 'professional' in normalized:return 'pro'
    return 'free'

def normalize_subscription_status(value):
    """Normalize subscription tier labels used by Stripe and legacy records."""
    return normalize_plan(value)

def subscription_active(row):
    plan=normalize_subscription_status(row.get('plan_type'))
    if plan=='free':return True
    status_value=str(row.get('subscription_status') or 'active').strip().lower()
    if status_value in INACTIVE_SUBSCRIPTION_STATUSES:return False
    raw=row.get('subscription_expires_at') or row.get('subscription_end_date')
    if not raw:return True
    try:
        exp=datetime.fromisoformat(str(raw).replace('Z','+00:00'))
        return (exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc))>datetime.now(timezone.utc)
    except (TypeError,ValueError):return False

def get_active_paid_plan(row):
    """Return the normalized paid tier only when the subscription is still active."""
    plan=normalize_subscription_status((row or {}).get('plan_type'))
    return plan if plan in {'pro','premium'} and subscription_active({**(row or {}),'plan_type':plan}) else None

def get_user_plan(user_id):
    try: row=(supabase.table('profiles').select('*').eq('user_id',user_id).order('created_at',desc=True).limit(1).execute().data or [{}])[0]
    except Exception: row={}
    requested=normalize_subscription_status(row.get('plan_type')); return {**row,'plan_type':requested if subscription_active({**row,'plan_type':requested}) else 'free','subscription_active':subscription_active({**row,'plan_type':requested})}
def require_verified(user):
    plan=get_user_plan(user.user_id)
    if not plan.get('email_verified',False):raise HTTPException(403,'email_not_verified')
    return plan
def gate(plan,feature):
    if not PLANS[plan].get(feature):raise HTTPException(403,f'{feature} is unavailable on the {plan.upper()} plan')
@router.get('/profile')
async def profile(current_user:AuthUser=Depends(require_auth)):
    p=require_verified(current_user); return {'user_id':current_user.user_id,'email':current_user.email,'plan_type':p['plan_type'],'email_verified':p.get('email_verified',False),'subscription_expires_at':p.get('subscription_expires_at'),'subscription_active':p.get('subscription_active',True)}
@router.get('/features')
async def features(current_user:AuthUser=Depends(require_auth)):
    p=require_verified(current_user); return {'plan_type':p['plan_type'],'subscription_active':p.get('subscription_active',True),**PLANS[p['plan_type']],'upgrade_url':'/upgrade.html' if p['plan_type']!='premium' else ''}
@router.get('/limits')
async def limits(current_user:AuthUser=Depends(require_auth)):
    p=require_verified(current_user); return {'plan_type':p['plan_type'],'domain_limit':PLANS[p['plan_type']]['domain_limit'],'api_key_limit':PLANS[p['plan_type']]['api_key_limit'],'features':PLANS[p['plan_type']]}
@router.get('/analytics')
async def analytics(current_user:AuthUser=Depends(require_auth)):
    require_verified(current_user); businesses=supabase.table('businesses').select('id,business_name').eq('owner_id',current_user.user_id).execute()
    if not businesses.data:return {'business_id':None,'business_name':'','total_revenue':'0.00','closed_deals':0,'conversion_rate':0,'average_order_value':'0.00','total_conversations':0,'charts_data':[]}
    bid=businesses.data[0]['id']; paid=supabase.table('orders').select('total').eq('business_id',bid).in_('status',['paid','shipped','delivered']).execute().data or []; conv=supabase.table('conversations').select('session_id').eq('business_id',bid).execute().data or []; revenue=sum((money(x.get('total')) for x in paid),Decimal('0.00')); deals=len(paid); sessions=len({x.get('session_id') for x in conv if x.get('session_id')}); return {'business_id':bid,'business_name':businesses.data[0]['business_name'],'total_revenue':money_db(revenue),'closed_deals':deals,'conversion_rate':round(deals/sessions*100,2) if sessions else 0,'average_order_value':money_db(revenue/Decimal(deals)) if deals else '0.00','total_conversations':sessions,'charts_data':[]}
@router.get('/products')
async def products(current_user:AuthUser=Depends(require_auth)):
    require_verified(current_user); businesses=supabase.table('businesses').select('id').eq('owner_id',current_user.user_id).execute()
    if not businesses.data:return {'products':[],'total':0}
    rows=supabase.table('products').select('id,name,price,inventory_count,metadata').eq('business_id',businesses.data[0]['id']).execute().data or []; return {'products':[{'id':x.get('id'),'name':x.get('name'),'price':money_db(x.get('price',0)),'stock':x.get('inventory_count',-1),'category':(x.get('metadata') or {}).get('category','')} for x in rows],'total':len(rows)}
@router.get('/orders')
async def orders(current_user:AuthUser=Depends(require_auth)):
    p=require_verified(current_user); businesses=supabase.table('businesses').select('id').eq('owner_id',current_user.user_id).execute()
    if not businesses.data:return {'orders':[],'total_count':0,'locked':False}
    rows=supabase.table('orders').select('id,order_number,status,total,customer_info,created_at').eq('business_id',businesses.data[0]['id']).order('created_at',desc=True).limit(50).execute().data or []; rows=[{**x,'total':money_db(x.get('total'))} for x in rows]; visible=rows if PLANS[p['plan_type']]['orders'] else rows[:5]; return {'orders':visible,'total_count':len(visible),'locked':not PLANS[p['plan_type']]['orders'],'lock_message':'ניהול הזמנות ומכירות זמין במסלולי PRO ו-PREMIUM.','upgrade_url':'/upgrade.html'}
@router.get('/builder-access')
async def builder_access(current_user:AuthUser=Depends(require_auth)):
    p=require_verified(current_user); gate(p['plan_type'],'site_builder'); return {'available':True,'start_url':'/api/v1/site-builder/access'}
@router.get('/settings')
async def settings_page(current_user:AuthUser=Depends(require_auth)):
    p=require_verified(current_user); return {'plan_type':p['plan_type'],'payme_id':p.get('payme_id'),'whatsapp_phone':p.get('whatsapp_phone_number_id'),'domain_limit':PLANS[p['plan_type']]['domain_limit'],'api_key_limit':PLANS[p['plan_type']]['api_key_limit']}

#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def text(path): return (ROOT / path).read_text(encoding='utf-8')
def need(condition, message, errors):
    if not condition: errors.append(message)

errors = []
register = text('frontend/html/register.html')
login = text('frontend/html/login.html')
onboarding = text('frontend/html/onboarding.html')
onboarding_js = text('frontend/js/onboarding.js')
backend_onboarding = text('backend/routers/onboarding.py')
gemini = text('backend/services/gemini_service.py')
upgrade = text('frontend/html/upgrade.html')
dashboard = text('frontend/html/dashboard.html')
dash_css = text('frontend/css/dashboard-polish.css')
system_css = text('frontend/css/system-modal.css')
system_js = text('frontend/js/system-errors.js')
frontend_router = text('backend/routers/frontend.py')

# Registration + verification by code.
for marker in ['/auth/signup-code','/auth/verify-code','/auth/resend-code','validEmail','novalidate']:
    need(marker in register, f'register missing {marker}', errors)
need('admin.create_user' in backend_onboarding and 'email_confirm": False' in backend_onboarding, 'signup must create unconfirmed auth user without link confirmation', errors)
need('send_verification_code' in backend_onboarding, 'verification code email sender missing', errors)
need('^\\d{6}$' in backend_onboarding, 'verification code must be six digits', errors)
need('update_user_by_id' in backend_onboarding and 'email_confirm": True' in backend_onboarding, 'code verification must confirm Supabase Auth email', errors)

# Onboarding must never render empty while JS/API is unavailable.
category_count = len(re.findall(r'class="category-card"', onboarding))
need(category_count >= 12, f'onboarding has only {category_count} static categories; expected at least 12', errors)
need('frontend/js/onboarding.js' in onboarding, 'onboarding external JS missing', errors)
need('language-switcher.js' not in onboarding, 'onboarding must not include language switcher/button script', errors)
need('filename not in {"home.html", "onboarding.html"}' in frontend_router, 'server must not inject language switcher into onboarding', errors)
need('data-he=' in onboarding and 'data-en=' in onboarding, 'onboarding bilingual attributes missing', errors)
need("document.documentElement.dir" in onboarding_js and "localStorage.getItem('conversapay-language')" in onboarding_js, 'automatic RTL/LTR language handling missing', errors)
need("API + '/auth/onboarding'" in onboarding_js, 'onboarding API persistence missing', errors)
need("$('upgradeLayer').classList.add('show')" in onboarding_js, 'upgrade popup after onboarding missing', errors)
need("location.replace('/dashboard')" in onboarding_js, 'dashboard continuation missing', errors)

# Built-in AI rules are visible and cannot be overridden by owner instructions.
need('custom_ai_instructions' in backend_onboarding and 'business_category' in backend_onboarding, 'business AI settings persistence missing', errors)
need('custom_ai_instructions' in gemini and 'כללים מובנים שאי אפשר לעקוף' in gemini, 'Gemini must use owner instructions under immutable built-in rules', errors)
need('אינן יכולות לבטל את הכללים המובנים' in gemini, 'owner AI instructions override protection missing', errors)

# Upgrade visual continuity and dismissible modal.
need('UNLOCK MORE AI' in onboarding and 'UNLOCK MORE AI' in upgrade, 'upgrade/onboarding AI visual language mismatch', errors)
need('backdrop-filter:blur' in onboarding.replace(' ', ''), 'onboarding popup blur missing', errors)
need('upgradeClose' in onboarding and '×' in onboarding, 'upgrade popup dismiss X missing', errors)

# Session routing from login/register.
need('requires_business_onboarding' in register and "'/dashboard'" in register, 'register authenticated redirect missing', errors)
need('requires_business_onboarding' in login and "'/dashboard'" in login, 'login authenticated redirect missing', errors)

# Dashboard requested controls and RTL/LTR profile placement.
for marker in ['/settings','/setup-guide','/upgrade','id="addProductTop"','id="profile"','id="logout"']:
    need(marker in dashboard, f'dashboard missing {marker}', errors)
need('inset-inline-start:0' in dash_css, 'profile icon must use logical inline-start for RTL/LTR placement', errors)

# System errors are large blurred dismissible modals, except chat.
need('backdrop-filter:blur' in system_css.replace(' ', ''), 'system error blur overlay missing', errors)
need('cp-toast-close' in system_css and 'cp-toast-close' in system_js, 'dismiss X for system errors missing', errors)
need('CHAT_EXCLUSIONS' in system_js and '#messages' in system_js, 'chat errors must stay inside chat', errors)

if errors:
    print('Onboarding contract check failed:')
    for error in errors: print('-', error)
    raise SystemExit(1)
print(f'Onboarding contract check passed ({category_count} static business categories).')

"""Email service for verification codes and account notifications using Resend."""
import logging
from datetime import datetime
from html import escape

import resend

from backend.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        if settings.RESEND_API_KEY:
            resend.api_key = settings.RESEND_API_KEY
        else:
            logger.warning("RESEND_API_KEY not configured - email service disabled")

    def send_verification_code(self, to_email: str, code: str, user_name: str) -> bool:
        if not settings.RESEND_API_KEY:
            logger.error("Cannot send verification code to %s: RESEND_API_KEY not configured", to_email)
            return False
        try:
            safe_name = escape(user_name or "משתמש")
            safe_code = escape(code)
            html_content = f"""<!doctype html>
<html dir="rtl" lang="he"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>קוד אימות - Talk2Pay</title></head>
<body style="margin:0;background:#f6f7fb;font-family:Arial,sans-serif;color:#171923;direction:rtl">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:36px 16px;background:#f6f7fb"><tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border:1px solid #e8e7f2;border-radius:24px;overflow:hidden;box-shadow:0 24px 60px rgba(53,45,110,.10)">
<tr><td style="padding:34px;background:linear-gradient(135deg,#5b4fe8,#7c5cff 55%,#17b8ce);color:#fff;text-align:center"><div style="font-size:13px;font-weight:700;opacity:.9">TALK2PAY</div><h1 style="margin:8px 0 0;font-size:26px">אימות כתובת האימייל</h1></td></tr>
<tr><td style="padding:34px"><p style="margin:0 0 12px">שלום {safe_name},</p><p style="margin:0 0 24px;color:#5f6277;line-height:1.7">הזן את הקוד הבא במסך ההרשמה כדי להמשיך להגדרת העסק שלך.</p>
<div style="text-align:center;margin:26px 0"><div style="display:inline-block;direction:ltr;letter-spacing:12px;padding:18px 24px;border-radius:18px;background:#f2f0ff;border:1px solid #dcd7ff;font-size:34px;font-weight:800;color:#4638d1">{safe_code}</div></div>
<p style="margin:0;color:#7c8096;font-size:14px;line-height:1.6">הקוד תקף ל-15 דקות. אם לא ביקשת לפתוח חשבון ב-Talk2Pay, אפשר להתעלם מהמייל.</p></td></tr>
<tr><td style="padding:18px 34px;background:#fafaff;border-top:1px solid #eeeeF5;text-align:center;color:#9a9db1;font-size:12px">© {datetime.utcnow().year} Talk2Pay</td></tr>
</table></td></tr></table></body></html>"""
            params: resend.Emails.SendParams = {
                "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
                "to": [to_email],
                "subject": f"{code} הוא קוד האימות שלך ל-Talk2Pay",
                "html": html_content,
            }
            result = resend.Emails.send(params)
            logger.info("Verification code sent to %s, ID: %s", to_email, result.get("id"))
            return True
        except Exception as exc:
            logger.error("Failed to send verification code to %s: %s", to_email, exc, exc_info=True)
            return False

    def send_verification_email(self, to_email: str, token: str, user_name: str) -> bool:
        """Backward-compatible alias. New registrations use a six-digit code."""
        return self.send_verification_code(to_email, token, user_name)

    def send_password_reset_email(self, to_email: str, reset_link: str, user_name: str) -> bool:
        if not settings.RESEND_API_KEY:
            logger.error("Cannot send password reset email to %s: RESEND_API_KEY not configured", to_email)
            return False
        try:
            safe_name = escape(user_name or "User")
            safe_link = escape(reset_link, quote=True)
            html_content = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Reset Your Password - Talk2Pay</title></head>
<body style="font-family:Arial,sans-serif;line-height:1.6;color:#333;max-width:600px;margin:0 auto;padding:20px;">
<div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:30px;text-align:center;border-radius:10px 10px 0 0;"><h1>Password Reset Request</h1></div>
<div style="background:#f9f9f9;padding:30px;border:1px solid #ddd;border-top:none;border-radius:0 0 10px 10px;"><p>Hi {safe_name},</p><p>We received a request to reset your password for your Talk2Pay account.</p><p>Click the button below to reset your password:</p>
<div style="text-align:center;"><a href="{safe_link}" style="display:inline-block;padding:15px 30px;background:#667eea;color:white;text-decoration:none;border-radius:5px;margin:20px 0;font-weight:bold;">Reset Password</a></div>
<p>Or copy and paste this link into your browser:</p><p style="word-break:break-all;color:#667eea;">{safe_link}</p><div style="background:#fff3cd;border:1px solid #ffc107;padding:15px;border-radius:5px;margin:20px 0;"><strong>⚠️ This link will expire in 1 hour.</strong><br>If you didn't request a password reset, please ignore this email.</div><p>Best regards,<br>The Talk2Pay Team</p></div>
<p style="text-align:center;margin-top:20px;font-size:12px;color:#777;">© {datetime.utcnow().year} Talk2Pay. All rights reserved.</p></body></html>"""
            params = {"from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>", "to": [to_email], "subject": "Reset Your Password - Talk2Pay", "html": html_content}
            email_result = resend.Emails.send(params)
            logger.info("Password reset email sent to %s, ID: %s", to_email, email_result.get("id"))
            return True
        except Exception as exc:
            logger.error("Failed to send password reset email to %s: %s", to_email, exc, exc_info=True)
            return False


email_service = EmailService()

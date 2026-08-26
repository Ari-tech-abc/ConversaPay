"""Email service for sending verification and notification emails using Resend SDK."""
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

    def send_verification_email(self, to_email: str, token: str, user_name: str) -> bool:
        if not settings.RESEND_API_KEY:
            logger.error("Cannot send verification email to %s: RESEND_API_KEY not configured", to_email)
            return False
        try:
            verification_link = f"{settings.BASE_URL.rstrip('/')}/api/v1/auth/verify?token={escape(token, quote=True)}"
            safe_name = escape(user_name or "משתמש")
            safe_link = escape(verification_link, quote=True)
            html_content = f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>אימות אימייל - Talk2Pay</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:system-ui,-apple-system,sans-serif;direction:rtl">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 16px">
<tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px">
  <tr><td align="center" style="padding-bottom:24px">
    <div style="display:inline-flex;align-items:center;gap:10px;text-decoration:none">
      <div style="width:42px;height:42px;border-radius:14px;background:linear-gradient(135deg,#6366f1,#00b8d9);display:inline-block;vertical-align:middle"></div>
      <span style="font-size:1.2rem;font-weight:800;color:#0f172a;vertical-align:middle">Talk2Pay</span>
    </div>
  </td></tr>
  <tr><td style="background:#fff;border-radius:24px;border:1px solid #e2e8f0;box-shadow:0 4px 24px rgba(15,23,42,.07);overflow:hidden">
    <div style="background:linear-gradient(135deg,#6366f1 0%,#00b8d9 100%);padding:36px 40px;text-align:center">
      <div style="font-size:2.5rem;margin-bottom:12px">✉️</div>
      <h1 style="margin:0;color:#fff;font-size:1.5rem;font-weight:800;letter-spacing:-.02em">ברוכים הבאים!</h1>
      <p style="margin:8px 0 0;color:rgba(255,255,255,.85);font-size:.95rem">צעד אחד לפני שמתחילים</p>
    </div>
    <div style="padding:36px 40px">
      <p style="margin:0 0 8px;color:#475569;font-size:.95rem">שלום {safe_name},</p>
      <p style="margin:0 0 28px;color:#0f172a;font-size:1rem;line-height:1.6">נשמח שהצטרפת אלינו! לחץ על הכפתור כדי לאמת את כתובת האימייל שלך ולהתחיל לעבוד עם Talk2Pay.</p>
      <div style="text-align:center;margin-bottom:28px">
        <a href="{safe_link}" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#6366f1,#4f46e5);color:#fff;text-decoration:none;border-radius:14px;font-weight:800;font-size:1rem;box-shadow:0 8px 20px rgba(99,102,241,.3)">אמת אימייל →</a>
      </div>
      <div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:24px;border:1px solid #e2e8f0">
        <p style="margin:0 0 6px;font-size:.8rem;color:#94a3b8;font-weight:700">אם הכפתור לא עובד, העתק את הקישור:</p>
        <p style="margin:0;font-size:.82rem;color:#6366f1;word-break:break-all;direction:ltr;text-align:left">{safe_link}</p>
      </div>
      <div style="background:#fef9ec;border:1px solid #fcd34d;border-radius:12px;padding:14px 16px;display:flex;align-items:center;gap:10px">
        <span style="font-size:1.1rem">⏰</span>
        <p style="margin:0;font-size:.88rem;color:#92400e;font-weight:600">הקישור יפוג תוך 24 שעות.</p>
      </div>
    </div>
    <div style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:20px 40px;text-align:center">
      <p style="margin:0;font-size:.8rem;color:#94a3b8">אם לא נרשמת ל-Talk2Pay, פשוט התעלם מאימייל זה.</p>
    </div>
  </td></tr>
  <tr><td style="padding:20px;text-align:center">
    <p style="margin:0;font-size:.78rem;color:#94a3b8">&copy; {datetime.utcnow().year} Talk2Pay. כל הזכויות שמורות.</p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
            params: resend.Emails.SendParams = {"from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>", "to": [to_email], "subject": "אמת את האימייל שלך - Talk2Pay", "html": html_content}
            email = resend.Emails.send(params)
            logger.info("Verification email sent to %s, ID: %s", to_email, email["id"])
            return True
        except Exception as exc:
            logger.error("Failed to send verification email to %s: %s", to_email, exc, exc_info=True)
            return False

    def send_password_reset_email(self, to_email: str, reset_link: str, user_name: str) -> bool:
        if not settings.RESEND_API_KEY:
            logger.error("Cannot send password reset email to %s: RESEND_API_KEY not configured", to_email)
            return False
        try:
            safe_name = escape(user_name or "User")
            safe_link = escape(reset_link, quote=True)
            html_content = f"""
            <!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Reset Your Password - Talk2Pay</title></head>
            <body style="font-family:Arial,sans-serif;line-height:1.6;color:#333;max-width:600px;margin:0 auto;padding:20px;">
              <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:30px;text-align:center;border-radius:10px 10px 0 0;"><h1>Password Reset Request</h1></div>
              <div style="background:#f9f9f9;padding:30px;border:1px solid #ddd;border-top:none;border-radius:0 0 10px 10px;">
                <p>Hi {safe_name},</p><p>We received a request to reset your password for your Talk2Pay account.</p><p>Click the button below to reset your password:</p>
                <div style="text-align:center;"><a href="{safe_link}" style="display:inline-block;padding:15px 30px;background:#667eea;color:white;text-decoration:none;border-radius:5px;margin:20px 0;font-weight:bold;">Reset Password</a></div>
                <p>Or copy and paste this link into your browser:</p><p style="word-break:break-all;color:#667eea;">{safe_link}</p>
                <div style="background:#fff3cd;border:1px solid #ffc107;padding:15px;border-radius:5px;margin:20px 0;"><strong>⚠️ This link will expire in 1 hour.</strong><br>If you didn't request a password reset, please ignore this email.</div>
                <p>Best regards,<br>The Talk2Pay Team</p>
              </div>
              <p style="text-align:center;margin-top:20px;font-size:12px;color:#777;">© {datetime.utcnow().year} Talk2Pay. All rights reserved.</p>
            </body></html>"""
            params = {"from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>", "to": [to_email], "subject": "Reset Your Password - Talk2Pay", "html": html_content}
            email_result = resend.Emails.send(params)
            logger.info("Password reset email sent to %s, ID: %s", to_email, email_result.get("id"))
            return True
        except Exception as exc:
            logger.error("Failed to send password reset email to %s: %s", to_email, exc, exc_info=True)
            return False


email_service = EmailService()

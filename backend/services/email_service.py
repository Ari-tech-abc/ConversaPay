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
            html_content = f"""
            <!DOCTYPE html><html><head><meta charset="utf-8"><title>Verify Your Email - Talk2Pay</title></head>
            <body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
              <div style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:30px;text-align:center;border-radius:10px 10px 0 0;"><h1>ברוך הבא ל-Talk2Pay!</h1></div>
              <div style="background:#f9f9f9;padding:30px;border:1px solid #ddd;border-top:none;border-radius:0 0 10px 10px;">
                <p>שלום {safe_name},</p><p>לחץ על הכפתור למטה כדי לאמת את כתובת האימייל שלך:</p>
                <div style="text-align:center;margin:30px 0;"><a href="{safe_link}" style="display:inline-block;padding:15px 30px;background:#667eea;color:white;text-decoration:none;border-radius:5px;font-weight:bold;">אמת אימייל</a></div>
                <p style="word-break:break-all;color:#667eea;">{safe_link}</p><p style="background:#fff3cd;border:1px solid #ffc107;padding:15px;border-radius:5px;">⏰ הקישור יפוג תוך 24 שעות.</p>
              </div>
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

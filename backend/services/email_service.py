"""
Email service for sending verification and notification emails using Resend SDK.
"""
import os
import logging
from typing import Optional
import resend
from datetime import datetime

from backend.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via Resend."""
    
    def __init__(self):
        """Initialize Resend client."""
        if settings.RESEND_API_KEY:
            resend.api_key = settings.RESEND_API_KEY
        else:
            logger.warning("RESEND_API_KEY not configured - email service disabled")
    
    def send_verification_email(self, to_email: str, token: str, user_name: str) -> bool:
        """
        Send email verification email to user.
        
        Args:
            to_email: Recipient email address
            token: Verification token
            user_name: User's full name
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not settings.RESEND_API_KEY:
            logger.error("Cannot send verification email: RESEND_API_KEY not configured")
            return False
        
        try:
            # Build verification link
            verification_link = f"{settings.BASE_URL}/api/v1/auth/verify?token={token}"
            
            # HTML email template
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Verify Your Email - ConversaPay</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 30px;
                        text-align: center;
                        border-radius: 10px 10px 0 0;
                    }}
                    .content {{
                        background: #f9f9f9;
                        padding: 30px;
                        border: 1px solid #ddd;
                        border-top: none;
                        border-radius: 0 0 10px 10px;
                    }}
                    .button {{
                        display: inline-block;
                        padding: 15px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 20px 0;
                        font-weight: bold;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 20px;
                        font-size: 12px;
                        color: #777;
                    }}
                    .warning {{
                        background: #fff3cd;
                        border: 1px solid #ffc107;
                        padding: 15px;
                        border-radius: 5px;
                        margin: 20px 0;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Welcome to ConversaPay!</h1>
                </div>
                <div class="content">
                    <p>Hi {user_name},</p>
                    
                    <p>Thank you for signing up for ConversaPay! We're excited to help you transform your customer service with AI-powered automation.</p>
                    
                    <p>To complete your registration and activate your account, please verify your email address by clicking the button below:</p>
                    
                    <div style="text-align: center;">
                        <a href="{verification_link}" class="button">Verify Email Address</a>
                    </div>
                    
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #667eea;">{verification_link}</p>
                    
                    <div class="warning">
                        <strong>⏰ This link will expire in 24 hours.</strong>
                    </div>
                    
                    <p>If you didn't create an account with ConversaPay, you can safely ignore this email.</p>
                    
                    <p>Best regards,<br>The ConversaPay Team</p>
                </div>
                <div class="footer">
                    <p>© {datetime.utcnow().year} ConversaPay. All rights reserved.</p>
                    <p>This email was sent to {to_email}</p>
                </div>
            </body>
            </html>
            """
            
            # Send email via Resend
            params = {
                "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
                "to": [to_email],
                "subject": "Verify Your Email - ConversaPay",
                "html": html_content
            }
            
            email_result = resend.Emails.send(params)
            
            logger.info(f"Verification email sent to {to_email}, ID: {email_result.get('id')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send verification email to {to_email}: {str(e)}", exc_info=True)
            return False
    
    def send_password_reset_email(self, to_email: str, reset_link: str, user_name: str) -> bool:
        """
        Send password reset email to user.
        
        Args:
            to_email: Recipient email address
            reset_link: Password reset link
            user_name: User's full name
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not settings.RESEND_API_KEY:
            logger.error("Cannot send password reset email: RESEND_API_KEY not configured")
            return False
        
        try:
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Reset Your Password - ConversaPay</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 30px;
                        text-align: center;
                        border-radius: 10px 10px 0 0;
                    }}
                    .content {{
                        background: #f9f9f9;
                        padding: 30px;
                        border: 1px solid #ddd;
                        border-top: none;
                        border-radius: 0 0 10px 10px;
                    }}
                    .button {{
                        display: inline-block;
                        padding: 15px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 20px 0;
                        font-weight: bold;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 20px;
                        font-size: 12px;
                        color: #777;
                    }}
                    .warning {{
                        background: #fff3cd;
                        border: 1px solid #ffc107;
                        padding: 15px;
                        border-radius: 5px;
                        margin: 20px 0;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Password Reset Request</h1>
                </div>
                <div class="content">
                    <p>Hi {user_name},</p>
                    
                    <p>We received a request to reset your password for your ConversaPay account.</p>
                    
                    <p>Click the button below to reset your password:</p>
                    
                    <div style="text-align: center;">
                        <a href="{reset_link}" class="button">Reset Password</a>
                    </div>
                    
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #667eea;">{reset_link}</p>
                    
                    <div class="warning">
                        <strong>⚠️ This link will expire in 1 hour.</strong><br>
                        If you didn't request a password reset, please ignore this email or contact support if you have concerns.
                    </div>
                    
                    <p>Best regards,<br>The ConversaPay Team</p>
                </div>
                <div class="footer">
                    <p>© {datetime.utcnow().year} ConversaPay. All rights reserved.</p>
                    <p>This email was sent to {to_email}</p>
                </div>
            </body>
            </html>
            """
            
            params = {
                "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
                "to": [to_email],
                "subject": "Reset Your Password - ConversaPay",
                "html": html_content
            }
            
            email_result = resend.Emails.send(params)
            logger.info(f"Password reset email sent to {to_email}, ID: {email_result.get('id')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send password reset email to {to_email}: {str(e)}", exc_info=True)
            return False


# Global email service instance
email_service = EmailService()
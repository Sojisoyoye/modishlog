"""Transactional email sending (verification links, password resets).

Uses Resend when RESEND_API_KEY is configured. Otherwise send_email()
logs the email instead of sending it -- keeps local dev, CI, and pytest
working with zero email-provider configuration (mirrors the pattern used
for optional infra elsewhere in this codebase, e.g. REDIS_URL).
"""

import html as html_lib

import resend
import structlog

from src.core.config import settings

logger = structlog.get_logger()


def send_email(*, email_to: str, subject: str, html_content: str) -> None:
    """Send a transactional email, or log it if Resend isn't configured."""
    if not settings.emails_enabled:
        logger.info(
            "email_not_sent_no_provider_configured",
            email_to=email_to,
            subject=subject,
        )
        return

    resend.api_key = settings.RESEND_API_KEY
    from_address = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
    result = resend.Emails.send(
        {
            "from": from_address,
            "to": [email_to],
            "subject": subject,
            "html": html_content,
        }
    )
    logger.info("email_sent", email_to=email_to, resend_id=(result or {}).get("id"))


def render_verification_email(email_to: str, token: str) -> tuple[str, str]:
    """Return (subject, html) for the email-verification link email."""
    subject = f"{settings.EMAILS_FROM_NAME} - Verify your email address"
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    safe_email = html_lib.escape(email_to)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Verify your email</title></head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #2c3e50;">Welcome to {settings.EMAILS_FROM_NAME}!</h1>
            <p>Please verify your email address ({safe_email}) by clicking the button below:</p>
            <p style="text-align: center; margin: 30px 0;">
                <a href="{link}"
                   style="background-color: #3498db; color: white; padding: 12px 30px;
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    Verify Email
                </a>
            </p>
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #3498db;">{link}</p>
            <p style="color: #666; font-size: 14px;">This link will expire in 24 hours.</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
            <p style="color: #999; font-size: 12px;">
                If you didn't create an account with {settings.EMAILS_FROM_NAME}, please ignore this email.
            </p>
        </div>
    </body>
    </html>
    """
    return subject, html_content


def render_reset_password_email(email_to: str, token: str) -> tuple[str, str]:
    """Return (subject, html) for the password-reset link email."""
    subject = f"{settings.EMAILS_FROM_NAME} - Reset your password"
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    safe_email = html_lib.escape(email_to)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Password Reset</title></head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #2c3e50;">{settings.EMAILS_FROM_NAME} - Password Reset</h1>
            <p>We received a request to reset the password for {safe_email}. Click the button below to create a new password:</p>
            <p style="text-align: center; margin: 30px 0;">
                <a href="{link}"
                   style="background-color: #e74c3c; color: white; padding: 12px 30px;
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    Reset Password
                </a>
            </p>
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #3498db;">{link}</p>
            <p style="color: #e74c3c; font-size: 14px; font-weight: bold;">This link will expire in 1 hour.</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
            <p style="color: #999; font-size: 12px;">
                If you didn't request a password reset, please ignore this email. Your password will remain unchanged.
            </p>
        </div>
    </body>
    </html>
    """
    return subject, html_content

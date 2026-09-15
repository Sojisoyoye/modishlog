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


_BRAND_PRIMARY = "#059669"
_BRAND_PRIMARY_LIGHT = "#ECFDF5"
_BRAND_TEXT = "#111827"
_BRAND_MUTED = "#6B7280"
_BRAND_BORDER = "#E5E7EB"
_FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def _render_email_shell(*, title: str, preheader: str, body_html: str) -> str:
    """Wrap email body content in ModishLog's shared branded shell.

    Inline styles + a table-based header are used throughout because email
    clients (Outlook especially) don't reliably support modern CSS.
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>{title}</title></head>
    <body style="margin: 0; padding: 0; background-color: {_BRAND_PRIMARY_LIGHT}; font-family: {_FONT_STACK};">
        <span style="display: none; max-height: 0; overflow: hidden;">{preheader}</span>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: {_BRAND_PRIMARY_LIGHT}; padding: 32px 16px;">
            <tr>
                <td align="center">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width: 480px; background-color: #FFFFFF; border-radius: 12px; overflow: hidden;">
                        <tr>
                            <td style="padding: 32px 32px 0 32px;">
                                <table role="presentation" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="width: 32px; height: 32px; background-color: {_BRAND_PRIMARY}; border-radius: 8px; text-align: center; vertical-align: middle;">
                                            <span style="color: #FFFFFF; font-size: 16px; font-weight: 700; line-height: 32px;">M</span>
                                        </td>
                                        <td style="padding-left: 10px;">
                                            <span style="color: {_BRAND_PRIMARY}; font-size: 18px; font-weight: 700;">ModishLog</span>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 24px 32px 32px 32px; color: {_BRAND_TEXT}; font-size: 14px; line-height: 1.6;">
                                {body_html}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 20px 32px; border-top: 1px solid {_BRAND_BORDER};">
                                <p style="margin: 0; color: {_BRAND_MUTED}; font-size: 12px;">
                                    &copy; 2026 ModishLog &middot; Lagos, Nigeria
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """


def _render_button(link: str, label: str) -> str:
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin: 24px 0;">
        <tr>
            <td style="background-color: {_BRAND_PRIMARY}; border-radius: 8px;">
                <a href="{link}"
                   style="display: inline-block; padding: 12px 28px; color: #FFFFFF;
                          font-size: 14px; font-weight: 600; text-decoration: none;">
                    {label}
                </a>
            </td>
        </tr>
    </table>
    """


def render_verification_email(email_to: str, token: str) -> tuple[str, str]:
    """Return (subject, html) for the email-verification link email."""
    subject = f"{settings.EMAILS_FROM_NAME} - Verify your email address"
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    safe_email = html_lib.escape(email_to)

    body_html = f"""
    <h1 style="margin: 0 0 12px 0; color: {_BRAND_TEXT}; font-size: 20px; font-weight: 700;">
        Welcome to ModishLog!
    </h1>
    <p style="margin: 0 0 8px 0;">
        Please verify your email address ({safe_email}) by clicking the button below:
    </p>
    {_render_button(link, "Verify Email")}
    <p style="margin: 0 0 4px 0; color: {_BRAND_MUTED}; font-size: 13px;">
        Or copy and paste this link into your browser:
    </p>
    <p style="margin: 0 0 16px 0; color: {_BRAND_PRIMARY}; font-size: 13px; word-break: break-all;">{link}</p>
    <p style="margin: 0; color: {_BRAND_MUTED}; font-size: 13px;">This link will expire in 24 hours.</p>
    <hr style="border: none; border-top: 1px solid {_BRAND_BORDER}; margin: 24px 0;">
    <p style="margin: 0; color: {_BRAND_MUTED}; font-size: 12px;">
        If you didn't create an account with ModishLog, please ignore this email.
    </p>
    """
    html_content = _render_email_shell(
        title="Verify your email",
        preheader="Verify your email address to finish setting up your ModishLog account.",
        body_html=body_html,
    )
    return subject, html_content


def render_reset_password_email(email_to: str, token: str) -> tuple[str, str]:
    """Return (subject, html) for the password-reset link email."""
    subject = f"{settings.EMAILS_FROM_NAME} - Reset your password"
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    safe_email = html_lib.escape(email_to)

    body_html = f"""
    <h1 style="margin: 0 0 12px 0; color: {_BRAND_TEXT}; font-size: 20px; font-weight: 700;">
        Reset your password
    </h1>
    <p style="margin: 0 0 8px 0;">
        We received a request to reset the password for {safe_email}. Click the button below to create a new password:
    </p>
    {_render_button(link, "Reset Password")}
    <p style="margin: 0 0 4px 0; color: {_BRAND_MUTED}; font-size: 13px;">
        Or copy and paste this link into your browser:
    </p>
    <p style="margin: 0 0 16px 0; color: {_BRAND_PRIMARY}; font-size: 13px; word-break: break-all;">{link}</p>
    <p style="margin: 0; color: #DC2626; font-size: 13px; font-weight: 600;">This link will expire in 1 hour.</p>
    <hr style="border: none; border-top: 1px solid {_BRAND_BORDER}; margin: 24px 0;">
    <p style="margin: 0; color: {_BRAND_MUTED}; font-size: 12px;">
        If you didn't request a password reset, please ignore this email. Your password will remain unchanged.
    </p>
    """
    html_content = _render_email_shell(
        title="Password Reset",
        preheader="Reset your ModishLog password. This link expires in 1 hour.",
        body_html=body_html,
    )
    return subject, html_content


def render_business_deletion_scheduled_email(
    email_to: str, business_name: str, purge_at_display: str
) -> tuple[str, str]:
    """Return (subject, html) for the deletion-scheduled confirmation email."""
    subject = f"{settings.EMAILS_FROM_NAME} - Account deletion scheduled"
    safe_name = html_lib.escape(business_name)

    body_html = f"""
    <h1 style="margin: 0 0 12px 0; color: {_BRAND_TEXT}; font-size: 20px; font-weight: 700;">
        Account deletion scheduled
    </h1>
    <p style="margin: 0 0 8px 0;">
        Deletion has been scheduled for <strong>{safe_name}</strong>. Your
        account and all business users are logged out immediately, and
        login is blocked until this is either cancelled or the deletion
        completes.
    </p>
    <p style="margin: 0 0 16px 0; color: #DC2626; font-size: 13px; font-weight: 600;">
        Your account will be permanently deleted on {purge_at_display} unless you cancel before then.
    </p>
    <p style="margin: 0; color: {_BRAND_MUTED}; font-size: 13px;">
        If you didn't request this, contact support immediately — anyone with
        Owner access to your account can cancel this from the Danger Zone in
        Settings before the deletion date above.
    </p>
    """
    html_content = _render_email_shell(
        title="Account Deletion Scheduled",
        preheader=f"Your ModishLog account will be deleted on {purge_at_display} unless cancelled.",
        body_html=body_html,
    )
    return subject, html_content


def render_business_deletion_cancelled_email(
    email_to: str, business_name: str
) -> tuple[str, str]:
    """Return (subject, html) for the deletion-cancelled confirmation email."""
    subject = f"{settings.EMAILS_FROM_NAME} - Account deletion cancelled"
    safe_name = html_lib.escape(business_name)

    body_html = f"""
    <h1 style="margin: 0 0 12px 0; color: {_BRAND_TEXT}; font-size: 20px; font-weight: 700;">
        Account deletion cancelled
    </h1>
    <p style="margin: 0 0 8px 0;">
        The scheduled deletion for <strong>{safe_name}</strong> has been
        cancelled. Your account is fully active again and login has been
        restored for all business users.
    </p>
    """
    html_content = _render_email_shell(
        title="Account Deletion Cancelled",
        preheader="Your ModishLog account deletion has been cancelled.",
        body_html=body_html,
    )
    return subject, html_content

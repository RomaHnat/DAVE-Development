import asyncio
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "noreply@dave.ie")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "emails"

def _render_template(name: str, **kwargs) -> Optional[str]:
    path = TEMPLATES_DIR / name
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    for key, val in kwargs.items():
        content = content.replace(f"{{{{{key}}}}}", str(val))
    return content

def _send_smtp(to: str, subject: str, plain_body: str, html_body: Optional[str]) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = to
    msg.attach(MIMEText(plain_body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.sendmail(SMTP_FROM_EMAIL, [to], msg.as_string())

async def send_email(
    to: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
) -> None:
    if not (SMTP_USERNAME and SMTP_PASSWORD):
        logger.info("[email] SMTP not configured – skipping. to=%s subject=%s", to, subject)
        return

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _send_smtp, to, subject, body, html)
        logger.info("[email] Sent to=%s subject=%s", to, subject)
    except Exception as exc:
        logger.warning("[email] Failed to send to=%s: %s", to, exc)


async def send_welcome_email(email: str, full_name: str) -> None:
    subject = "Welcome to DAVE \u2013 Documents and Applications Validation Engine"
    body = (
        f"Hello {full_name},\n\n"
        "Welcome to DAVE! Your account has been created successfully.\n"
        "You can now log in and start managing your applications and documents.\n\n"
        "Best regards,\nThe DAVE Team"
    )
    html = _render_template("welcome.html", full_name=full_name)
    await send_email(email, subject, body, html)


async def send_password_reset_email(
    email: str, full_name: str, reset_token: str
) -> None:
    reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"
    subject = "DAVE \u2013 Password Reset Request"
    body = (
        f"Hello {full_name},\n\n"
        f"You requested a password reset. Use the token below:\n\n"
        f"  {reset_token}\n\n"
        f"Or visit: {reset_link}\n\n"
        "This token expires in 24 hours.\n"
        "If you did not request this, please ignore this email.\n\n"
        "Best regards,\nThe DAVE Team"
    )
    html = _render_template(
        "password_reset.html",
        full_name=full_name,
        reset_token=reset_token,
        reset_link=reset_link,
    )
    await send_email(email, subject, body, html)

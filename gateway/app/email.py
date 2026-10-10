# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Outbound email, through whichever SMTP relay the settings name.

The live deployment is meant to use Brevo. Until `SMTP_HOST` and `MAIL_FROM` are
set nothing is sent: `configured()` is false and `send()` logs what would have
gone out and returns False. Anything that must not act as though a message was
delivered checks `configured()`, or the result of `send()`, first.

Port 465 speaks TLS from the start; anything else upgrades with STARTTLS, which
is what Brevo recommends on 587.
"""

import logging
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings

logger = logging.getLogger("visdom.email")

_background = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email")


def configured() -> bool:
    return bool(settings.SMTP_HOST.strip() and settings.MAIL_FROM.strip())


def _message(to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((settings.MAIL_FROM_NAME, settings.MAIL_FROM))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def send(to: str, subject: str, body: str) -> bool:
    """Send one message now. Returns whether it was handed to the relay."""
    if not configured():
        logger.info("[email not configured] would send %r to %s", subject, to)
        return False
    message = _message(to, subject, body)
    context = ssl.create_default_context()
    try:
        if settings.SMTP_PORT == 465:
            relay = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10, context=context)
        else:
            relay = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        with relay:
            if settings.SMTP_PORT != 465:
                relay.starttls(context=context)
            if settings.SMTP_USERNAME:
                relay.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            relay.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("could not send %r to %s: %s", subject, to, exc)
        return False
    return True


def send_later(to: str, subject: str, body: str) -> None:
    """Send without making the caller wait on the relay."""
    _background.submit(send, to, subject, body)


def send_workspace_invite_email(to_email: str, workspace_name: str, invite_url: str) -> None:
    send_later(
        to_email,
        f"You have been invited to {workspace_name} on Visdom",
        (
            f"You have been invited to join the workspace \"{workspace_name}\" on Visdom.\n\n"
            f"Sign in or create an account with this email address to accept:\n{invite_url}\n\n"
            "If you were not expecting this, you can ignore this message."
        ),
    )


def send_password_reset_email(to_email: str, reset_url: str, minutes: int) -> None:
    send_later(
        to_email,
        "Reset your Visdom password",
        (
            "Someone asked to reset the password for the Visdom account that uses this email address.\n\n"
            f"Choose a new password here within the next {minutes} minutes:\n{reset_url}\n\n"
            "The link works once. If you did not ask for this, you can ignore this message "
            "and your password stays as it is."
        ),
    )


def build_share_link_url(link_id) -> str:
    return f"{settings.FRONTEND_URL}/share/{link_id}"

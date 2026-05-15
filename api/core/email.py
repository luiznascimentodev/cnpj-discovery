from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx
from loguru import logger

from core.config import settings


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:  # pragma: no cover
        ...


class LogOnlySender:
    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        logger.info("Email suppressed: to={} subject={}", to, subject)


class MailpitSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        username: str = "",
        password: str = "",
    ):
        self._host = host
        self._port = port
        self._sender = sender
        self._username = username
        self._password = password

    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(html, subtype="html")

        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)


class ResendSender:
    def __init__(self, *, api_key: str, sender: str):
        self._api_key = api_key
        self._sender = sender

    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "from": self._sender,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
            )
            response.raise_for_status()


def make_email_sender() -> EmailSender:
    if settings.environment == "production":
        if settings.resend_api_key:
            return ResendSender(api_key=settings.resend_api_key, sender=settings.email_from)
        return LogOnlySender()
    return MailpitSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        sender=settings.email_from,
        username=settings.smtp_username,
        password=settings.smtp_password,
    )

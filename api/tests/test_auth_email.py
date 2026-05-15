from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from core.email import LogOnlySender, MailpitSender, ResendSender, make_email_sender
from modules.auth.emails import send_reset_email, send_verification_email
from modules.auth.schemas import UserRecord


class FakeSender:
    def __init__(self):
        self.messages = []

    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        self.messages.append({"to": to, "subject": subject, "html": html, "text": text})


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.response = kwargs.pop("response", None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        FakeAsyncClient.last_call = {"args": args, "kwargs": kwargs}
        return FakeAsyncClient.response


class FakeResponse:
    def __init__(self):
        self.raised = False

    def raise_for_status(self):
        self.raised = True


def user_record():
    now = datetime.now(timezone.utc)
    return UserRecord(
        id=uuid4(),
        email="user@example.com",
        password_hash="hash",
        name="User",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_auth_email_templates_render_links():
    sender = FakeSender()
    user = user_record()

    await send_verification_email(user, "verify-token", sender)
    await send_reset_email(user, "reset-token", sender)

    assert sender.messages[0]["to"] == "user@example.com"
    assert "verify-token" in sender.messages[0]["html"]
    assert "verify-token" in sender.messages[0]["text"]
    assert "reset-token" in sender.messages[1]["html"]


@pytest.mark.asyncio
async def test_log_only_sender_does_not_raise():
    await LogOnlySender().send(to="a@b.com", subject="S", html="<p>x</p>", text="x")


@pytest.mark.asyncio
async def test_mailpit_sender_builds_multipart_message():
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.__exit__.return_value = False

    with patch("core.email.smtplib.SMTP", return_value=smtp) as smtp_cls:
        sender = MailpitSender(
            host="mailpit",
            port=1025,
            sender="noreply@example.com",
            username="user",
            password="pass",
        )
        await sender.send(to="to@example.com", subject="Subject", html="<b>html</b>", text="text")

    smtp_cls.assert_called_once_with("mailpit", 1025, timeout=10)
    smtp.login.assert_called_once_with("user", "pass")
    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "to@example.com"
    assert message["Subject"] == "Subject"


@pytest.mark.asyncio
async def test_resend_sender_posts_payload():
    response = FakeResponse()
    FakeAsyncClient.response = response

    with patch("core.email.httpx.AsyncClient", FakeAsyncClient):
        sender = ResendSender(api_key="key", sender="from@example.com")
        await sender.send(to="to@example.com", subject="Subject", html="<b>html</b>", text="text")

    assert response.raised
    assert FakeAsyncClient.last_call["args"] == ("https://api.resend.com/emails",)
    assert FakeAsyncClient.last_call["kwargs"]["headers"]["Authorization"] == "Bearer key"
    assert FakeAsyncClient.last_call["kwargs"]["json"]["to"] == ["to@example.com"]


def test_make_email_sender_selects_by_environment():
    with patch("core.email.settings.environment", "production"), \
         patch("core.email.settings.resend_api_key", "key"):
        assert isinstance(make_email_sender(), ResendSender)

    with patch("core.email.settings.environment", "production"), \
         patch("core.email.settings.resend_api_key", ""):
        assert isinstance(make_email_sender(), LogOnlySender)

    with patch("core.email.settings.environment", "development"):
        assert isinstance(make_email_sender(), MailpitSender)

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.config import settings
from core.email import EmailSender, make_email_sender
from modules.auth.schemas import UserRecord

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "email"
_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def _url(path: str, token: str) -> str:
    base = settings.app_base_url.rstrip("/")
    return f"{base}{path}?token={token}"


def _render_pair(template_name: str, **context) -> tuple[str, str]:
    html = _ENV.get_template(f"{template_name}.html").render(**context)
    text = _ENV.get_template(f"{template_name}.txt").render(**context)
    return html, text


async def send_verification_email(
    user: UserRecord,
    token_raw: str,
    sender: EmailSender | None = None,
) -> None:
    verify_url = _url("/verificar-email", token_raw)
    html, text = _render_pair("verify_email", name=user.name, verify_url=verify_url)
    await (sender or make_email_sender()).send(
        to=str(user.email),
        subject="Confirme seu e-mail no CNPJ Discovery",
        html=html,
        text=text,
    )


async def send_reset_email(
    user: UserRecord,
    token_raw: str,
    sender: EmailSender | None = None,
) -> None:
    reset_url = _url("/redefinir-senha", token_raw)
    html, text = _render_pair("reset_password", name=user.name, reset_url=reset_url)
    await (sender or make_email_sender()).send(
        to=str(user.email),
        subject="Redefina sua senha no CNPJ Discovery",
        html=html,
        text=text,
    )

"""Cliente BrasilAPI para dados RF em tempo real.

Consulta /api/cnpj/v1/{cnpj14} para obter email, telefone e QSA atualizados.
Retorna None em qualquer falha — sempre usado como fallback opcional.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx


@dataclass(frozen=True)
class BrasilAPIResult:
    email: str | None
    ddd_telefone_1: str | None
    ddd_telefone_2: str | None
    qsa_names: list[str] = field(default_factory=list)


async def fetch_cnpj(
    cnpj14: str,
    *,
    client: httpx.AsyncClient,
    base_url: str = "https://brasilapi.com.br/api",
) -> BrasilAPIResult | None:
    """Consulta BrasilAPI para um CNPJ de 14 dígitos. Retorna None em qualquer erro."""
    url = f"{base_url}/cnpj/v1/{cnpj14}"
    try:
        response = await client.get(url, timeout=httpx.Timeout(8.0))
    except httpx.HTTPError:
        return None

    if response.status_code != 200:
        return None

    try:
        data = response.json()
    except Exception:
        return None

    qsa = data.get("qsa") or []
    qsa_names = [
        m["nome_socio"]
        for m in qsa
        if isinstance(m, dict) and m.get("nome_socio", "").strip()
    ]

    return BrasilAPIResult(
        email=data.get("email") or None,
        ddd_telefone_1=data.get("ddd_telefone_1") or None,
        ddd_telefone_2=data.get("ddd_telefone_2") or None,
        qsa_names=qsa_names,
    )

"""Query builder para descoberta de domínio por mecanismos de busca.

Estratégia de prioridade (confidence_bonus):
  +30  CNPJ formatado — site com CNPJ é quase certamente o oficial
  +15  trade name + city — alta precisão para empresas locais
  +10  legal name (sem sufixos) + city
  + 5  sócio + company name — útil para MEI e firmas individuais
  + 3  legal name sozinho (fallback)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_LEGAL_SUFFIXES_RE = re.compile(
    r"\b(LTDA|EIRELI|ME|SA|S\.A|EPP|INDUSTRIA|INDUSTRIAS|COMERCIO|SERVICOS|"
    r"EMPREENDIMENTOS|SOLUCOES|PARTICIPACOES|HOLDING|FILIAL)\b",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s{2,}")


@dataclass(frozen=True)
class SearchQuery:
    text: str
    confidence_bonus: int
    reason: str


def format_cnpj14(cnpj14: str) -> str:
    if len(cnpj14) != 14 or not cnpj14.isdigit():
        return cnpj14
    return f"{cnpj14[:2]}.{cnpj14[2:5]}.{cnpj14[5:8]}/{cnpj14[8:12]}-{cnpj14[12:]}"


def _strip_legal_suffixes(name: str) -> str:
    result = _LEGAL_SUFFIXES_RE.sub("", name)
    return _WHITESPACE_RE.sub(" ", result).strip(" ,./")


def _normalize_for_dedup(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return ascii_only.lower().strip()


def build_search_queries(
    cnpj14: str,
    legal_name: str | None,
    trade_name: str | None,
    city: str | None,
    partner_names: list[str],
) -> list[SearchQuery]:
    queries: list[SearchQuery] = []
    seen: set[str] = set()

    def _add(text: str, bonus: int, reason: str) -> None:
        key = _normalize_for_dedup(text)
        if key not in seen:
            seen.add(key)
            queries.append(SearchQuery(text=text, confidence_bonus=bonus, reason=reason))

    formatted_cnpj = format_cnpj14(cnpj14)
    _add(f'"{formatted_cnpj}"', 30, "cnpj_exact")

    if trade_name:
        clean_trade = trade_name.strip()
        if city:
            _add(f'"{clean_trade}" {city}', 15, "trade_name_city")
        _add(f'"{clean_trade}" site oficial', 8, "trade_name")

    if legal_name:
        short_legal = _strip_legal_suffixes(legal_name)
        if len(short_legal) >= 4:
            if city:
                _add(f'"{short_legal}" {city} CNPJ', 10, "legal_name_city")
            _add(f'"{short_legal}" contato', 3, "legal_name")

    for partner in partner_names[:2]:
        name = partner.strip()
        if len(name) >= 5:
            base = trade_name or _strip_legal_suffixes(legal_name or "")
            if base:
                _add(f'"{name}" "{base}"', 5, "partner_name")

    return sorted(queries, key=lambda q: -q.confidence_bonus)

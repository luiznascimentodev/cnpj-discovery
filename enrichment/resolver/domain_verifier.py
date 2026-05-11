"""Verificação de domínio: pontua sinais de identidade e atualiza status.

Sinais são derivados do HTML/texto da página oficial candidata e dos
dados RF do CNPJ alvo. A tabela de pesos segue o spec.
"""
from dataclasses import dataclass
import re
import unicodedata

VERIFIED_THRESHOLD = 80
CANDIDATE_THRESHOLD = 40

_DIGIT_RE = re.compile(r"\D+")


@dataclass(frozen=True)
class DomainScoreResult:
    score: int
    status: str
    signals: tuple[str, ...]


def _strip_diacritics(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalize_text(value: str) -> str:
    return _strip_diacritics(value).lower()


def _name_match(html_norm: str, name: str | None, full_score: int, kind: str) -> tuple[int, str | None]:
    if not name:
        return 0, None
    key = _normalize_text(name).strip()
    if not key:
        return 0, None
    if key in html_norm:
        return full_score, f"{kind}_exact"
    tokens = [token for token in key.split() if len(token) >= 4]
    if not tokens:
        return 0, None
    matched = sum(1 for token in tokens if token in html_norm)
    if matched == len(tokens):
        return full_score, f"{kind}_all_tokens"
    if matched >= max(1, len(tokens) // 2):
        return full_score // 2, f"{kind}_partial"
    return 0, None


def _classify(score: int) -> str:
    if score >= VERIFIED_THRESHOLD:
        return "verified"
    if score >= CANDIDATE_THRESHOLD:
        return "candidate"
    return "rejected"


def score_domain_evidence(
    html: str,
    *,
    domain: str,
    cnpj: str,
    legal_name: str | None = None,
    fantasy_name: str | None = None,
    rf_email_domain: str | None = None,
    rf_phone_normalized: str | None = None,
    cep: str | None = None,
    city: str | None = None,
    uf: str | None = None,
    partner_names: list[str] | None = None,
    is_directory: bool = False,
    is_parked: bool = False,
) -> DomainScoreResult:
    score = 0
    signals: list[str] = []

    digits_only = _DIGIT_RE.sub("", html)
    if cnpj and cnpj in digits_only:
        score += 60
        signals.append("cnpj_exact")

    if rf_email_domain and rf_email_domain.lower() == domain.lower():
        score += 35
        signals.append("rf_email_domain_match")

    html_norm = _normalize_text(html)

    legal_pts, legal_signal = _name_match(html_norm, legal_name, 30, "legal")
    if legal_signal:
        score += legal_pts
        signals.append(legal_signal)

    fantasy_pts, fantasy_signal = _name_match(html_norm, fantasy_name, 25, "fantasy")
    if fantasy_signal:
        score += fantasy_pts
        signals.append(fantasy_signal)

    # Partner name signal — at most one match, +20 pts
    for name in (partner_names or [])[:5]:
        pts, signal = _name_match(html_norm, name, 20, "partner_name")
        if signal:
            score += pts
            signals.append(signal)
            break  # only count the first matching partner

    if cep:
        cep_digits = _DIGIT_RE.sub("", cep)
        if cep_digits and cep_digits in digits_only:
            score += 20
            signals.append("cep_match")

    if city:
        city_norm = _normalize_text(city).strip()
        if city_norm and re.search(rf"\b{re.escape(city_norm)}\b", html_norm):
            score += 5
            signals.append("city_match")

    if uf and re.search(rf"\b{re.escape(uf.lower())}\b", html_norm):
        score += 5
        signals.append("uf_match")

    if rf_phone_normalized and rf_phone_normalized in digits_only:
        score += 20
        signals.append("rf_phone_match")

    if is_directory:
        score -= 40
        signals.append("directory_penalty")

    if is_parked:
        score -= 60
        signals.append("parked_penalty")

    bounded = max(0, min(score, 100))
    return DomainScoreResult(
        score=bounded,
        status=_classify(bounded),
        signals=tuple(signals),
    )


_SQL_UPDATE_DOMAIN_STATUS = """
    UPDATE paid_enrichment.company_domains
    SET confidence = $5,
        status = $6,
        last_seen = now()
    WHERE cnpj_basico = $1
      AND cnpj_ordem = $2
      AND cnpj_dv = $3
      AND domain = $4
"""


async def update_domain_status(
    pool,
    *,
    cnpj_basico: str,
    cnpj_ordem: str,
    cnpj_dv: str,
    domain: str,
    score: int,
    status: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_UPDATE_DOMAIN_STATUS,
            cnpj_basico,
            cnpj_ordem,
            cnpj_dv,
            domain,
            score,
            status,
        )

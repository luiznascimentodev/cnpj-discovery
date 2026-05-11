"""Orquestra fontes externas de descoberta de domínio.

Cadeia de fallback por custo crescente e precisão decrescente:
  1. BrasilAPI  — email RF corporativo (grátis, sem quota, alta precisão)
  2. SearXNG    — metabusca self-hosted (grátis, ilimitado, Google+Bing+DDG)
  3. Brave      — queries CNPJ-first (2.000/mês grátis, se configurado)
  4. Google CSE — fallback de alta qualidade (100/dia grátis, se configurado)
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from discovery.brasilapi import fetch_cnpj
from discovery.brave_search import search_with_queries
from discovery.google_cse import search_google_cse
from discovery.search_queries import build_search_queries
from discovery.searxng import search_searxng
from domain_discovery import DomainCandidate, domains_from_rf_email
from rf_baseline import normalize_rf_email


@dataclass
class ExternalSearchClient:
    brasilapi_enabled: bool = True
    brave_api_key: str = ""
    google_cse_api_key: str = ""
    google_cse_cx: str = ""
    searxng_url: str = ""
    brasilapi_base_url: str = "https://brasilapi.com.br/api"
    brave_base_url: str = "https://api.search.brave.com"
    google_cse_base_url: str = "https://www.googleapis.com/customsearch/v1"

    async def enrich_candidates(
        self,
        cnpj14: str,
        legal_name: str | None,
        trade_name: str | None,
        city: str | None,
        partner_names: list[str],
        client: httpx.AsyncClient,
    ) -> list[DomainCandidate]:
        """Retorna candidatos extras via fontes externas.

        Ordem: BrasilAPI email → SearXNG → Brave → Google CSE.
        Retorna na primeira fonte que produzir candidatos não-diretório.
        """
        # 1. BrasilAPI — email corporativo RF (fonte mais precisa, sem quota)
        if self.brasilapi_enabled:
            api_result = await fetch_cnpj(
                cnpj14, client=client, base_url=self.brasilapi_base_url
            )
            if api_result and api_result.email:
                email_contact = normalize_rf_email(api_result.email)
                if email_contact and email_contact.classification == "corporate_domain":
                    candidates = domains_from_rf_email(email_contact)
                    if candidates:
                        return candidates
            if api_result and api_result.qsa_names and not partner_names:
                partner_names = api_result.qsa_names

        # 2. SearXNG — metabusca local ilimitada (Google+Bing+DDG via proxy)
        if self.searxng_url and (legal_name or trade_name):
            queries = build_search_queries(
                cnpj14=cnpj14,
                legal_name=legal_name,
                trade_name=trade_name,
                city=city,
                partner_names=partner_names,
            )
            for query in queries[:2]:
                candidates = await search_searxng(
                    query, client=client, base_url=self.searxng_url
                )
                if candidates:
                    return candidates

        # 3. Brave Search — queries priorizadas por CNPJ
        if self.brave_api_key and (legal_name or trade_name):
            queries = build_search_queries(
                cnpj14=cnpj14,
                legal_name=legal_name,
                trade_name=trade_name,
                city=city,
                partner_names=partner_names,
            )
            candidates = await search_with_queries(
                queries,
                client=client,
                api_key=self.brave_api_key,
                base_url=self.brave_base_url,
            )
            if candidates:
                return candidates

        # 4. Google CSE — fallback de alta qualidade
        if self.google_cse_api_key and self.google_cse_cx and (legal_name or trade_name):
            queries = build_search_queries(
                cnpj14=cnpj14,
                legal_name=legal_name,
                trade_name=trade_name,
                city=city,
                partner_names=partner_names,
            )
            for query in queries[:3]:
                candidates = await search_google_cse(
                    query,
                    client=client,
                    api_key=self.google_cse_api_key,
                    cx=self.google_cse_cx,
                    base_url=self.google_cse_base_url,
                )
                if candidates:
                    return candidates

        return []

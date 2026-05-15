# Auth + Backend Refactor — Implementation Plan

**Data:** 2026-05-15
**Spec:** [`../specs/2026-05-15-auth-design.md`](../specs/2026-05-15-auth-design.md)
**Sub-projeto #2** (Auth) + refator preparatório do backend para arquitetura **Modular Monolith + Vertical Slice**.

---

## Princípios de execução

1. **Tests sempre verdes.** Cada fase termina com `pytest --cov` em 100% e `npm test` 100%. Não há fase "intermediária quebrada".
2. **Refator é mecânico antes de funcional.** R1–R2 só movem código existente; nenhum comportamento muda. Só depois disso adicionamos Auth (R3+).
3. **Boundaries enforced via `import-linter`** desde R1. Violações quebram CI.
4. **Confirmação após R2.** Antes de começar Auth (R3), verifico que a refatoração ficou estável.
5. **Sem destrutivo sem commit.** Cada R-fase é 1 commit atômico.

---

## R — Refator backend (Modular Monolith + Vertical Slice)

### R0. Inventário (read-only, sem commit)

Antes de mover qualquer coisa, mapear:

- **Módulos a criar:** `prospecting`, `enrichment`, `billing`, `bairros`, `cnaes`, `empresa`, `export`, `status` (cada router atual vira um módulo)
- **Cross-cutting → `core/`:** `database.py`, `cache.py`, `config.py`, `dependencies.py`, `middleware/`
- **Tests atuais:** mapear quais tests passam a viver dentro de `modules/<x>/tests/` e quais ficam em `core/tests/`

Resultado: nada commitado. Só lista interna para guiar R1/R2.

### R1. Scaffold da arquitetura

**O que muda:**
- Cria diretórios `api/core/` e `api/modules/` (vazios, com `__init__.py`)
- Cria `api/.importlinter` (config inicial sem regras estritas — só registra os contracts)
- Adiciona dep dev: `import-linter`
- CI roda `lint-imports` (entra no pipeline backend)
- **Nenhum código existente movido ainda.** R1 é só scaffolding.

**Saída:** commit `refactor(backend): scaffold modular monolith structure`. Tests verdes (nada movido).

### R2. Mover cross-cutting para `core/`

**Movimentos:**
```
api/database.py     → api/core/db.py
api/cache.py        → api/core/cache.py
api/config.py       → api/core/config.py
api/dependencies.py → api/core/dependencies.py
api/middleware/     → api/core/middleware/   (mantém subdir)
```

**O que muda:**
- Move arquivos. Re-aponta todos os imports (`from api.database import …` → `from api.core.db import …`).
- Cria `api/core/__init__.py` re-exportando símbolos públicos quando útil.
- Tests verdes.

**Saída:** commit `refactor(backend): move cross-cutting to api.core`.

### R3. Mover features para `modules/`

Uma feature por commit, ordem: a mais simples primeiro.

| Sub-fase | Feature | Origem | Destino |
|---|---|---|---|
| R3.1 | status | `routers/status.py` | `modules/status/router.py` |
| R3.2 | empresa | `routers/empresa.py` + `models/empresa.py` | `modules/empresa/{router,schemas}.py` |
| R3.3 | bairros | `routers/bairros.py` | `modules/bairros/router.py` |
| R3.4 | cnaes | `routers/cnaes.py` + `services/cnae_segments.py` | `modules/cnaes/{router,service}.py` |
| R3.5 | export | `routers/export.py` | `modules/export/router.py` |
| R3.6 | prospecting | `routers/prospecting.py` + `services/query_builder.py` + `models/filters.py` + `models/detail.py` | `modules/prospecting/{router,service,schemas}.py` |
| R3.7 | enrichment (read) | `routers/paid_enrichment.py` + `services/{entitlements,enrichment_*}.py` + `models/enrichment*.py` | `modules/enrichment/{router,service,schemas}.py` |
| R3.8 | billing | `routers/billing_webhook.py` + `services/{billing,stripe_signature}.py` | `modules/billing/{router,service}.py` |

Cada sub-fase: commit atômico, tests verdes, lint-imports verde. Convenção interna de cada módulo:

```
modules/<feature>/
├── __init__.py        # interface pública (re-exporta o router e tipos compartilháveis)
├── router.py          # FastAPI APIRouter — endpoints HTTP
├── service.py         # casos de uso (chamáveis em testes sem HTTP)
├── repository.py      # acesso a dados (Postgres + cache)
├── schemas.py         # Pydantic in/out
├── dependencies.py    # DI específica desse módulo
└── tests/             # tests vivem ao lado da feature
```

Nem todo módulo precisa de todas as camadas (ex.: `status` só tem `router.py`). A regra é: **se a camada existe, ela fica nesse layout**.

### R4. Boundaries reais via `import-linter`

Depois que tudo está nos módulos, ativa contracts estritos:

```ini
# api/.importlinter
[importlinter]
root_package = api

[importlinter:contract:modules-isolation]
name = Modules cannot import other modules directly
type = independence
modules =
    api.modules.auth
    api.modules.prospecting
    api.modules.enrichment
    api.modules.billing
    api.modules.bairros
    api.modules.cnaes
    api.modules.empresa
    api.modules.export
    api.modules.status

[importlinter:contract:layers]
name = Module internals follow router → service → repository
type = layers
layers =
    router
    service
    repository
containers =
    api.modules.auth
    api.modules.prospecting
    ...
```

**Cross-module talk:** se módulo A precisar de B, fala via `from api.modules.b import public_function` — onde `public_function` está exportado no `__init__.py` de B. Para Auth, isso quase nunca acontece (Auth é injetado via dependency, não chamado por outros módulos).

**Saída:** commit `chore(backend): enforce module boundaries via import-linter`.

---

## B — Auth backend

Agora a estrutura está pronta. Adicionamos `modules/auth/` seguindo o layout.

### B1. Migração + módulos de domínio

- `db/migrations/016_auth.sql` (DDL do spec §5.2)
- `modules/auth/repository.py`:
  - `UserRepository` (insert, get_by_email, get_by_id, mark_verified, update_password)
  - `EmailVerificationRepo`, `PasswordResetRepo`, `AuthEventRepo`
- `modules/auth/service.py` — funções puras + chamadas a repo:
  - `hash_password(plain) -> str` (argon2id)
  - `verify_password(plain, hash) -> bool`
  - `check_pwned(plain) -> bool` (HIBP k-anonymity, com timeout curto e fallback "allow")
  - `make_token() -> (raw, hash)` (32 bytes random; hash via SHA-256)
- `core/security/sessions.py`:
  - `create_session(user_id, ip, ua) -> session_id`
  - `read_session(session_id) -> SessionData | None`
  - `touch_session(session_id)` (renova TTL — sliding)
  - `destroy_session(session_id)`
- Tests unit pra tudo isso. **Sem endpoints ainda.**

**Saída:** commit `feat(auth): domain + repository + session primitives`.

### B2. E-mail

- `core/email.py`:
  - `Protocol EmailSender`
  - `MailpitSender` (SMTP)
  - `ResendSender` (HTTP)
  - `LogOnlySender`
  - Factory que escolhe baseado em `settings.environment` e `RESEND_API_KEY`
- `modules/auth/emails.py`:
  - `send_verification_email(user, token_raw)`
  - `send_reset_email(user, token_raw)`
- Templates `api/templates/email/{verify_email,reset_password}.{html,txt}` (Jinja2)
- Tests com `LogOnlySender` mockado

**Saída:** commit `feat(auth): email sender + templates`.

### B3. Rate-limit + CSRF + middleware

- `core/rate_limit.py`:
  - `RateLimiter(redis, bucket_key, window, max_count)` — `try_acquire() -> RateLimitResult(ok, remaining, retry_after)`
- `core/csrf.py`:
  - `generate_csrf_token()`, `verify_csrf(cookie_value, header_value)` (compare_digest)
  - `csrf_dependency(request)` — falha 403 se inválido
- `core/middleware/auth.py`:
  - `get_current_user(request, response, repo) -> User` — lê cookie, valida sessão Redis, renova TTL, injeta user. Dispara `HTTPException(401)` se ausente.
  - `optional_user` (mesmo, mas retorna None se ausente)
- Tests de unit + integration (testcontainers Redis ou fakeredis)

**Saída:** commit `feat(auth): rate limit, csrf, get_current_user middleware`.

### B4. Endpoints público: register + verify + resend

- `modules/auth/router.py` ganha:
  - `POST /v1/auth/register`
  - `POST /v1/auth/verify-email`
  - `POST /v1/auth/resend-verification`
  - `GET /v1/auth/csrf`
- `schemas.py` com modelos request/response
- Auditoria via `AuthEventRepo` em cada handler
- Tests endpoint-by-endpoint (httpx) + coverage 100%

**Saída:** commit `feat(auth): register + email verification endpoints`.

### B5. Endpoints autenticado: login + logout + me

- `POST /v1/auth/login`: valida senha, rate-limit, cria sessão, set-cookie
- `POST /v1/auth/logout`
- `GET /v1/auth/me`
- Atenção a timing-attack: `verify_password` roda mesmo se user não existe (com hash dummy)
- Tests + coverage 100%

**Saída:** commit `feat(auth): login + logout + me endpoints`.

### B6. Endpoints reset password

- `POST /v1/auth/forgot-password` — sempre 200 OK (não vaza existência)
- `POST /v1/auth/reset-password`
- Após reset bem-sucedido, **invalidar todas as sessões ativas do user** (revoga via padrão de chave `sess:*` + lookup reverso por user) — ou marcar `password_updated_at` no User e validar contra sessão.

  **Decisão simplificadora:** após reset, varrer Redis com `SCAN` para chaves `sess:*` que pertençam ao user e deletar. Em volume pequeno é OK. Em volume médio (> 1000 sessões/user), mantemos um set `user_sessions:{user_id}` no Redis para lookup O(1) — adicionamos esse índice já agora.

- Tests + coverage 100%

**Saída:** commit `feat(auth): password reset endpoints`.

### B7. Infraestrutura

- `docker-compose.yml`: serviço `mailpit` (porta 8025 UI, 1025 SMTP)
- `docker-compose.prod.yml`: sem mailpit, espera variáveis `RESEND_API_KEY` + `EMAIL_FROM`
- `Makefile`: comando `make mailpit` opcional
- Update `README.md` mencionando Mailpit em dev

**Saída:** commit `chore(auth): docker-compose mailpit service`.

---

## F — Auth frontend

### F1. `shared/api` apiClient

- Cria `frontend/src/shared/api/client.ts`:
  - axios instance com `baseURL`, `withCredentials: true`
  - Request interceptor: lê cookie `cnpj_csrf` e injeta header `X-CSRF-Token` em métodos mutativos
  - Response interceptor: 401 → invalida cache `session` no QueryClient e dispara `window.location` redirect (ou expõe callback)
- Cria `frontend/src/shared/api/errors.ts`: `ApiError` class normalizada
- Tests unit + msw para mock de servidor

**Saída:** commit `feat(fe): shared/api client with CSRF and 401 handling`.

### F2. `features/auth` hooks

- `frontend/src/features/auth/api.ts` — funções que chamam apiClient
- `frontend/src/features/auth/useSession.ts`
- `useLogin.ts`, `useRegister.ts`, `useLogout.ts`, `useForgotPassword.ts`, `useResetPassword.ts`, `useVerifyEmail.ts`, `useResendVerification.ts`
- `frontend/src/features/auth/schemas.ts` — zod schemas
- `frontend/src/entities/session/model/types.ts` — `Session`, `AuthError`
- Tests para hooks via msw + RTL

**Saída:** commit `feat(fe): features/auth hooks + entities/session`.

### F3. Páginas Login e Registro funcionais

- `pages/login/ui/LoginPage.tsx` ganha form react-hook-form + zodResolver
- `pages/registro/ui/RegistroPage.tsx` idem
- Após login bem-sucedido: invalida `session` query e navega para `?next=` ou `/app/prospeccao`
- Após register: navega para `/verificar-email-enviado?email=...`
- Form fields acessíveis (label, aria-describedby para erros)
- Tests RTL + axe

**Saída:** commit `feat(fe): login + register pages with real forms`.

### F4. Páginas verify-email + reset-password

- Nova page `pages/verificar-email/` — lê `?token=` da URL, dispara POST, mostra resultado (loading / success / error / expired)
- Nova page `pages/verificar-email-enviado/` — confirma envio e tem botão "reenviar"
- `pages/recuperar-senha/ui/RecuperarSenhaPage.tsx` ganha form (e-mail) + mensagem sempre genérica
- Nova page `pages/redefinir-senha/` — lê `?token=`, form de nova senha
- Tests + axe

**Saída:** commit `feat(fe): email verification + password reset pages`.

### F5. ProtectedRoute real

- `app/router/ProtectedRoute.tsx`:
  - Usa `useSession()`. Loading → spinner. Sucesso → children. Erro/401 → `<Navigate to="/login?next={pathname}" replace />`.
- Remove flag `AUTH_ENABLED=false`
- Tests RTL para ProtectedRoute

**Saída:** commit `feat(fe): real ProtectedRoute via useSession`.

### F6. Playwright smoke

- `e2e/auth-flow.spec.ts`:
  - Register → ver e-mail em Mailpit (via API HTTP do Mailpit: `GET http://localhost:8025/api/v1/messages`) → extrair token → verify → login → access /app → logout → confirma redirect

**Saída:** commit `test(fe): e2e auth-flow via mailpit`.

### F7. CI verde + merge

- `npm run lint`, `npm test`, `npm run build`, `npm run check:bundle`
- `pytest --cov` 100%
- Push develop, merge → main

**Saída:** commit final `chore: release sub-projeto 2 (Auth)`.

---

## Cronograma estimado de commits

| Fase | Commits | Descrição curta |
|---|---|---|
| R1 | 1 | scaffold modular monolith |
| R2 | 1 | move cross-cutting to core |
| R3 | 8 | mover 8 features para modules |
| R4 | 1 | import-linter contracts |
| B1–B7 | 7 | Auth backend (domain → endpoints → infra) |
| F1–F7 | 7 | Auth frontend (api → hooks → pages → e2e) |
| **Total** | **~25** | |

Branch: criar `feature/auth-and-backend-refactor` a partir de `develop`. Cada fase = 1 commit. No final, merge para `develop` → `main` (sem PR, conforme combinado).

---

## Riscos identificados

1. **Refator R3 quebrar tests por imports antigos** — Mitigação: tests rodam em cada commit; rollback é trivial (commit atômico).
2. **HIBP API offline** — Mitigação: timeout 1s, fallback `allow` (não bloqueia signup), logamos warning.
3. **Mailpit não vir up em CI** — Mitigação: tests backend não dependem de Mailpit real; usam `LogOnlySender`. E2E Playwright só roda local (não em CI por enquanto).
4. **Coverage cair em adapters de e-mail externos** — Mitigação: mocka `ResendSender` em tests; coverage do `ResendSender` real fica em test de integration opcional (skip se sem `RESEND_API_KEY`).
5. **Vite cache stale no frontend após mudança em apiClient** — Mitigação: `rm -rf node_modules/.vite` documentado, conhecido do bug anterior.

---

## Após este sub-projeto

- Memória do roadmap deve ser atualizada: `#2 ✅`, próximos #3 (Landing pública) ou #4 (Pipeline backend).
- Documentar a nova arquitetura em `frontend/README.md` (backend) — adicionar seção "Backend architecture: Modular Monolith + Vertical Slice".

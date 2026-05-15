# Auth (backend + frontend)

**Data:** 2026-05-15
**Projeto:** CNPJ Discovery
**Status:** Draft aguardando aprovação do usuário
**Sub-projeto #2 de 6** no plano de embelezamento (ver `2026-05-14-design-system-foundation-design.md` §1)

---

## 1. Objetivo

Trazer autenticação real ao produto: usuários se cadastram, confirmam e-mail, fazem login, recuperam senha. O frontend deixa de usar `AUTH_ENABLED=false` e passa a proteger `/app/*` de verdade.

**Sucesso ao terminar = um usuário consegue:**

1. Criar conta em `/registro` com e-mail + senha forte
2. Receber e-mail de verificação (Mailpit em dev, Resend em prod)
3. Clicar no link, ativar a conta, ser redirecionado para `/login`
4. Logar em `/login` e cair em `/app/prospeccao`
5. Recuperar senha esquecida em `/recuperar-senha` → e-mail com link → tela de redefinição
6. Deslogar voluntariamente
7. Sessão expira sozinha após 7 dias de inatividade

Todos os endpoints com tests, 100% coverage backend mantido.

## 2. Princípios de segurança (não-negociáveis)

1. **Senha nunca cruza nenhum log.** Hashing com **argon2id** (parâmetros OWASP). Plaintext só na request body, imediatamente descartado após hash.
2. **Sessão é server-side em Redis.** Cookie carrega só um session id opaco (UUIDv7). Revogação é instantânea (delete da chave Redis).
3. **Cookie httpOnly + Secure + SameSite=Lax.** Imune a XSS exfiltrar token. SameSite=Lax permite navegação top-level (necessário pro link de verificação por e-mail).
4. **CSRF via double-submit cookie + custom header.** Detalhado em §7.
5. **Rate-limit em Redis** por IP **e** por e-mail em login/registro/reset. Captcha hCaptcha entra só quando dispara (lazy).
6. **Senhas verificadas contra HIBP pwned-passwords** via k-anonymity (não envia senha completa). Reject senhas comprometidas.
7. **Não vazamos existência de conta.** Reset de senha e reenvio de verificação respondem 200 OK mesmo se e-mail não existe.
8. **Tokens de e-mail são single-use, expiram em 24h** (verificação) e **1h** (reset), guardados como hash no banco.

## 3. Decisões fechadas (do brainstorm com usuário, 2026-05-15)

| Tema | Decisão |
|---|---|
| Mecanismo de sessão | Cookie httpOnly + sessão em Redis |
| Signup | Self-signup aberto + e-mail verification obrigatório |
| Providers | Só e-mail/senha por agora |
| E-mail (dev) | Mailpit local (`smtp://mailpit:1025`) |
| E-mail (prod) | Resend API (`RESEND_API_KEY`) |
| TTL de sessão | Sliding 7 dias, sem "lembre-me" |
| Política de senha | Mín. 12 chars + HIBP pwned check (sem complexidade arbitrária) |
| Anti brute-force | Rate-limit Redis por IP+email, captcha hCaptcha após N falhas |
| Cookie name | `cnpj_session` |
| Domínio do cookie | host-only em dev, `.dominio.com.br` em prod |

## 4. Decisões abertas (a fechar antes de implementar)

| Tema | Default proposto | Pergunta |
|---|---|---|
| Captcha provider | hCaptcha (sem tracking, sem Google) | Confirmar? Alternativa: Cloudflare Turnstile |
| Domínio de e-mail em prod | placeholder até definir | Tem domínio para `noreply@…`? |
| Suporte a mudança de e-mail | Fora de escopo (depois) | OK adiar? |
| Logout from all devices | Fora de escopo (depois) | OK adiar? |
| Admin role | Fora de escopo (depois) | OK adiar? Não é blocker pra outros sub-projetos. |

## 5. Arquitetura — backend

Backend hoje é `api/` (FastAPI) com módulos `routers/`, `services/`, `models/`. Auth segue o mesmo padrão.

### 5.1 Estrutura

```
api/
├── routers/auth.py           # endpoints HTTP (POST /v1/auth/*, GET /v1/auth/me)
├── services/
│   ├── auth_passwords.py     # hash, verify, HIBP check
│   ├── auth_sessions.py      # criar/validar/destruir sessão Redis
│   ├── auth_tokens.py        # gerar/validar tokens de verify + reset (postgres)
│   ├── auth_emails.py        # render + send (verify / reset)
│   ├── auth_rate_limit.py    # bucket por IP+email
│   └── email_sender.py       # interface + impls (Mailpit SMTP, Resend HTTP)
├── models/auth.py            # User, Session, EmailVerification, PasswordReset (Pydantic)
├── middleware/auth.py        # depend: get_current_user, require_user
└── tests/test_auth_*.py
```

### 5.2 Data model (PostgreSQL)

Migração nova: `db/migrations/016_auth.sql`

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email CITEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  name TEXT NOT NULL,
  email_verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX users_email_active ON users (email) WHERE deleted_at IS NULL;

CREATE TABLE email_verifications (
  token_hash BYTEA PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ
);
CREATE INDEX email_verifications_user ON email_verifications (user_id) WHERE used_at IS NULL;

CREATE TABLE password_resets (
  token_hash BYTEA PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ
);
CREATE INDEX password_resets_user ON password_resets (user_id) WHERE used_at IS NULL;

-- Auditoria mínima (não-PII)
CREATE TABLE auth_events (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  event TEXT NOT NULL, -- 'login_ok','login_fail','register','verify','reset_req','reset_ok','logout'
  ip INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX auth_events_user_time ON auth_events (user_id, created_at DESC);
CREATE INDEX auth_events_recent ON auth_events (created_at DESC);
```

Sessões **não** vão pro Postgres — vivem só em Redis (chave `sess:{uuid}` → JSON `{user_id, csrf_token, ip, ua, created_at, last_seen_at, expires_at}` com `EXPIRE` 7d).

### 5.3 Endpoints

Todos sob `/v1/auth/`. Schemas request/response em `models/auth.py`. Códigos HTTP explícitos.

| Método | Rota | Auth? | Descrição | Rate-limit |
|---|---|---|---|---|
| POST | `/v1/auth/register` | público | Cria user, envia e-mail de verificação | 5/IP/h, 3/email/h |
| POST | `/v1/auth/login` | público | Valida senha, cria sessão, set-cookie | 10/IP/15min, 5/email/15min |
| POST | `/v1/auth/logout` | autenticado | Destrói sessão Redis, clear cookie | — |
| POST | `/v1/auth/verify-email` | público | Body `{token}`, marca `email_verified_at` | 20/IP/h |
| POST | `/v1/auth/resend-verification` | público | Body `{email}`, gera novo token. Sempre 200. | 3/email/h |
| POST | `/v1/auth/forgot-password` | público | Body `{email}`. Sempre 200 (não vaza existência). | 5/IP/h, 3/email/h |
| POST | `/v1/auth/reset-password` | público | Body `{token, new_password}`. | 10/IP/h |
| GET | `/v1/auth/me` | autenticado | Retorna `{id, email, name, email_verified_at}` | — |
| GET | `/v1/auth/csrf` | público | Retorna CSRF token e seta cookie `cnpj_csrf` | — |

### 5.4 CSRF strategy (double-submit + custom header)

- Endpoint `GET /v1/auth/csrf` retorna `{csrf: "<random>"}` e seta cookie `cnpj_csrf` (não-httpOnly, SameSite=Lax).
- Toda request mutativa (POST/PUT/PATCH/DELETE) deve carregar header `X-CSRF-Token` igual ao valor do cookie. Backend compara (constant-time).
- Endpoints públicos pré-sessão (register, login, forgot-password) **também exigem CSRF** para evitar formulário malicioso de terceiros disparando ações.
- Frontend: `axios` interceptor pega cookie e injeta header automaticamente.

### 5.5 Cookies

```
cnpj_session  HttpOnly  Secure(prod)  SameSite=Lax  Path=/  Max-Age=604800 (7d, sliding via re-set)
cnpj_csrf                Secure(prod)  SameSite=Lax  Path=/  Max-Age=604800
```

Em dev (HTTP localhost), `Secure` é omitido. Configurado via `settings.environment`.

## 6. Arquitetura — frontend

Segue FSD strict já estabelecido no sub-projeto 1.

### 6.1 Camadas afetadas

- `entities/user/` — já existe `User` type. Adicionar `email_verified_at?: string` se faltar.
- `entities/session/` — **novo**. Tipos `Session`, `AuthError`. **Sem** lógica de regra.
- `features/auth/` — **novo**. `useSession`, `useLogin`, `useRegister`, `useLogout`, `useForgotPassword`, `useResetPassword`, `useVerifyEmail`. Cada um é hook TanStack Query (`useQuery` ou `useMutation`).
- `shared/api/` — **novo**. `apiClient` axios instance com `withCredentials: true`, interceptor de CSRF, interceptor de 401 → invalida sessão.
- `app/router/ProtectedRoute.tsx` — passa a usar `useSession` real; redireciona pra `/login` se 401, com `?next=`.
- `pages/login/`, `pages/registro/`, `pages/recuperar-senha/` — já existem como stubs, ganham forms react-hook-form + zod.
- `pages/verificar-email/` — **novo**, lê `?token=` da URL, dispara POST e mostra resultado.
- `pages/redefinir-senha/` — **novo**, lê `?token=` da URL, form de nova senha.

### 6.2 Forms

`react-hook-form` + `zodResolver`. Schemas em `features/auth/schemas.ts`:

```ts
export const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
})

export const registerSchema = z.object({
  name: z.string().min(2).max(120),
  email: z.string().email(),
  password: z.string().min(12, 'Mínimo 12 caracteres'),
})
```

Validação de senha "pwned" é **server-side**. Frontend só valida comprimento. Resultado do servidor (`{error: 'pwned'}`) vira mensagem inline no campo.

### 6.3 useSession + ProtectedRoute

```ts
export function useSession() {
  return useQuery({
    queryKey: ['session'],
    queryFn: () => apiClient.get<Session>('/v1/auth/me').then(r => r.data),
    retry: false,
    staleTime: 60_000,
  })
}
```

`ProtectedRoute` usa `useSession`. Enquanto carrega → `<Spinner/>` centralizado. Se erro/401 → `<Navigate to="/login?next={pathname}" replace/>`.

## 7. E-mail

### 7.1 Interface

```python
class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, html: str, text: str) -> None: ...
```

Implementações:

- `MailpitSender` (dev): SMTP local `mailpit:1025`. Mailpit roda como service no `docker-compose.yml`.
- `ResendSender` (prod): HTTP POST `https://api.resend.com/emails` com `RESEND_API_KEY`.
- `LogOnlySender` (testes / fallback): só loga. Usado em pytest.

Selecionado em `dependencies.py` via `settings.environment` + presença de `RESEND_API_KEY`.

### 7.2 Templates

2 templates iniciais em `api/templates/email/`:

- `verify_email.{html,txt}` — link `${APP_URL}/verificar-email?token=…`
- `reset_password.{html,txt}` — link `${APP_URL}/redefinir-senha?token=…`

Markup mínimo, sem imagens externas, dark-mode safe. Texto em PT-BR.

## 8. Rate-limit e abuse

Module `services/auth_rate_limit.py` com `RateLimiter` usando Redis `INCR` + `EXPIRE`. Buckets:

- `rl:login:ip:{ip}` (15min)
- `rl:login:email:{sha256(email)}` (15min)
- `rl:register:ip:{ip}` (1h)
- `rl:register:email:{sha256(email)}` (1h)
- `rl:reset:ip:{ip}` (1h)
- `rl:reset:email:{sha256(email)}` (1h)

Resposta: HTTP 429 com `Retry-After`. **Captcha** entra quando IP excede metade do orçamento — frontend recebe `{require_captcha: true}` e renderiza hCaptcha widget.

## 9. Testing strategy

### Backend (mantém 100% coverage)
- Unit: hash/verify, HIBP mock, session create/validate/expire, token hash/single-use, rate-limit buckets, CSRF compare.
- Integration: cada endpoint end-to-end com Redis real (testcontainers ou redis fake) + Postgres real (já temos fixtures).
- Concurrência: dois logins simultâneos não geram race em rate-limit.
- Segurança: cookie flags corretos, headers de erro consistentes (não vazam), tempo de resposta entre login válido/inválido é constante (timing-attack mitigation).

### Frontend
- Unit: `useSession` retorna user, 401 limpa cache. ProtectedRoute redireciona.
- Forms: validação Zod, submit chama mutation, erro server vira mensagem.
- Axe: páginas login/registro/recuperar-senha passam axe.
- Playwright smoke: register → login → access /app/prospeccao → logout → redirect to /.

## 10. Out of scope (sub-projeto 2)

- Trocar e-mail (precisa de fluxo de verificação dupla)
- Logout em todos os dispositivos / listar sessões ativas
- 2FA (TOTP / WebAuthn)
- OAuth (Google/Microsoft) — adiado pra fase 2
- Convites / multi-tenancy
- Roles e permissions (admin, user)
- Privacy: data export e account deletion (LGPD) — sub-projeto separado

## 11. Roadmap interno (fases)

Quando o spec for aprovado, plan vai detalhar passo-a-passo. Esboço:

| Fase | Conteúdo |
|---|---|
| **B1** | Migração 016, módulos passwords + sessions + tokens (sem endpoint) + tests unit |
| **B2** | email_sender (Mailpit + LogOnly), templates, auth_emails |
| **B3** | rate_limit + CSRF service + middleware get_current_user |
| **B4** | Endpoints: register + verify-email + resend (com tests) |
| **B5** | Endpoints: login + logout + me + csrf (com tests) |
| **B6** | Endpoints: forgot-password + reset-password (com tests) |
| **B7** | Integração: docker-compose adiciona Mailpit, ResendSender para prod |
| **F1** | `shared/api` apiClient + CSRF interceptor + 401 handler |
| **F2** | `features/auth` hooks (useSession, useLogin, etc) |
| **F3** | Páginas login + registro com forms reais (substitui stubs) |
| **F4** | Páginas verificar-email + redefinir-senha + recuperar-senha forms |
| **F5** | ProtectedRoute real + flip `AUTH_ENABLED=true` |
| **F6** | Playwright smoke end-to-end |
| **F7** | Lint + tests + bundle budget verde, merge para develop → main |

## 12. Sobre a memória "API only does GET"

A memória antiga registrava "API só faz GET" como regra. Inspecionando o código atual, o backend **já tem POST** (`billing_webhook`, `paid_enrichment`, `enrichment_jobs`). A regra real é:

> **Regra de negócio sempre no backend. Frontend só exibe. Mutations só por endpoints autenticados e auditados.**

Auth se enquadra perfeitamente: todos os POSTs são auditados (tabela `auth_events`), com rate-limit e CSRF. Atualizar a memória pra refletir a regra real.

# CNPJ Discovery — Frontend

SPA React 19 + TypeScript + Vite, organizada em **Feature-Sliced Design v2** com um
design system próprio (tokens W3C → shadcn-style primitives → componentes de domínio).

## Stack

- **React 19 + Vite 7** com HMR
- **Tailwind v4** (`@theme` directive, sem `tailwind.config.ts`)
- **Radix UI** primitives + `class-variance-authority` (cva) — padrão shadcn/ui
- **TanStack Query** (estado de servidor) e **TanStack Table v8** + `@tanstack/react-virtual`
- **React Router v7** em modo data router (`createBrowserRouter`)
- **React Hook Form + Zod**
- **Sonner** (toasts), **cmdk** (command palette), **Framer Motion** (animação)
- **lucide-react** via barrel curado em `@/shared/ui/icons` (ESLint impede imports diretos)
- **Vitest + RTL + vitest-axe** (unitário/a11y) e **Playwright** (e2e smoke)

## Arquitetura: Feature-Sliced Design (FSD)

Camadas (ordem de dependência — uma só pode importar das de baixo):

```
app       → bootstrap, providers, router, estilos globais
pages     → composição por rota; pode usar widgets/features/entities/shared
widgets   → blocos visuais auto-contidos (ex.: AppShell)
features  → fluxos com lógica (ex.: prospeccao/filter, pipeline/move-card)
entities  → modelos de domínio (User, Empresa, Pipeline)
shared    → UI sem domínio (primitives/data/feedback/layout, hooks, api, lib)
```

`eslint-plugin-boundaries` impede violações (ex.: `shared` importar de `entities`).

Detalhes completos em [docs/architecture.md](docs/architecture.md).

## Design system

- **Tokens**: 3 camadas (`primitive → semantic → component`) em `src/app/styles/tokens.css`,
  expostos como CSS variables consumíveis por Tailwind `bg-[var(--color-action)]`.
- **Identidade visual** moderna gov.br-adjacent: navy `#0c326f`, action blue `#1351b4`,
  amarelo brand `#FFCD07`, tipografia Inter, densidade compacta (base 14px).
- **A11y AA**: contraste verificado, focus-ring tokenizado, `prefers-reduced-motion`.
- **Componentes**: 24 primitives + data layer (DataTable virtualizado, Stat, Skeleton…) +
  feedback (Toaster, Alert, Banner, ConfirmDialog) + layout (Container, Stack, Inline, PageHeader).

## Scripts

```sh
npm run dev              # vite dev server (porta 5173)
npm run build            # tsc -b && vite build
npm run lint
npm run test             # vitest run
npm run test:coverage    # com thresholds (80/80/80/75)
npm run e2e              # playwright (chromium)
npm run check:bundle     # gate de bundle gzip (default 350 kB)
```

## CI

`.github/workflows/frontend.yml` roda lint → test (coverage) → build → bundle budget
em todo PR que toca `frontend/**`. Threshold inicial: 350 kB gzip total.

## Segurança

- `nginx.conf` aplica CSP estrita (no `unsafe-eval`, no inline scripts), HSTS,
  X-Frame-Options DENY, Referrer-Policy, Permissions-Policy.
- Regras de negócio **somente no backend**; frontend exibe.
- `dangerouslySetInnerHTML` bloqueado por `no-restricted-syntax`.

## Legacy

O módulo de prospecção pré-FSD vive isolado em `src/pages/prospeccao/legacy/`
(`ProspeccaoPage` é um wrapper fino sobre ele). Será reescrito em cima do
design system em sub-projetos futuros.

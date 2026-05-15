# Design System Foundation + App Shell

**Data:** 2026-05-14
**Projeto:** CNPJ Discovery
**Status:** Spec aprovado pelo usuário — pronto pra writing-plans
**Sub-projeto #1 de 6** no plano de embelezamento (ver "Plano macro" abaixo)

---

## 1. Plano macro (contexto)

O embelezamento foi decomposto em 6 sub-projetos independentes, cada um com spec → plano → execução próprios:

| # | Sub-projeto | Dependências |
|---|---|---|
| **1** | **Design System foundation + App Shell** (este spec) | — |
| 2 | Auth backend + frontend (users, sessões, login/registro/recovery) | #1 |
| 3 | Landing page pública | #1 |
| 4 | Pipeline backend (tabelas + endpoints write) | #2 |
| 5 | Pipeline frontend (kanban, drag-drop, batch import) | #1, #4 |
| 6 | Refatoração da página Prospecting atual | #1, #4 (botão "adicionar ao pipeline") |

Este spec cobre **apenas o #1**. Resto fica fora de escopo aqui.

## 2. Objetivo deste sub-projeto

Estabelecer a base sobre a qual todos os outros sub-projetos vão construir:

- Arquitetura frontend canônica (FSD strict)
- Sistema de design tokens (W3C-style 3-layer)
- Biblioteca de componentes base (`shared/ui/`)
- App shell autenticado (TopBar + SideNav)
- Roteamento (React Router v7) com rotas públicas/privadas
- Padrões transversais (loading, erro, empty, toast, modal)
- Budget de performance, acessibilidade (WCAG AA), e regras de não-vazamento de regra de negócio

**Sucesso = ao terminar este sub-projeto:**
- Existe um app rodando com landing stub, login stub, home stub e prospecting placeholder, todos usando o design system
- Qualquer novo dev pode criar uma feature nova seguindo regras explícitas de import e composição
- ESLint bloqueia violações de FSD e violações de "regra de negócio no front"
- Lighthouse Performance ≥ 90 em desktop

## 3. Princípios

1. **Regra de negócio mora no backend.** O frontend só recebe, exibe, e envia inputs. `entities/` no FSD contém **tipos e formatadores** apenas — nunca cálculo de regra.
2. **Tokens semânticos, sempre.** Componentes nunca usam cor crua ou valor primitivo direto; só consomem semantic tokens. Trocar tema = trocar valor de tokens, não tocar componente.
3. **Acessibilidade não é opcional.** WCAG 2.2 AA é o mínimo. Cada PR roda axe automatizado.
4. **Sem emoji em UI.** Todo ícone é lucide line (SVG, stroke 1.5px).
5. **Microinterações discretas-a-médias** (Framer Motion), respeitando `prefers-reduced-motion`.
6. **Sem regressão de performance.** Bundle inicial ≤ 200kb gz, LCP ≤ 2s em 4G simulado.
7. **Padrões canônicos nomeados, sempre.** Sem híbridos sem justificativa.

## 4. Decisões fechadas

| Tema | Decisão | Padrão de referência |
|---|---|---|
| Arquitetura de pastas | Feature-Sliced Design (FSD) v2 strict | feature-sliced.design |
| State server | TanStack Query (já no projeto) | tanstack.com/query |
| State client local | Hooks React + Context onde necessário | — |
| Roteamento | React Router v7 (data router mode) | reactrouter.com |
| Tabela | TanStack Table v8 + virtualização (`@tanstack/react-virtual`) | — |
| Componentes base | shadcn/ui pattern (copy-paste) sobre Radix UI primitives + class-variance-authority | ui.shadcn.com |
| Estilização | Tailwind v4 (`@theme`) | tailwindcss.com |
| Ícones | lucide-react (curado em `shared/ui/icons`) | lucide.dev |
| Animação | Framer Motion (lazy-loaded em rotas que usam) | framer.com/motion |
| Forms | React Hook Form + Zod | — |
| HTTP client | axios com interceptors | (já no projeto) |
| Testing | Vitest + React Testing Library + axe-core | — |
| Build | Vite 8 + Rolldown (já no projeto) | — |
| Identidade visual | Inspirado em Receita Federal + polimento SaaS | — |
| Paleta | "Moderna gov.br-adjacent": primary `#0c326f`, action `#1351b4`, brand `#FFCD07` | govbr-ds (inspiração, não cópia) |
| Tipografia | Inter (Google Fonts, `font-display: swap`) | — |
| Densidade | Compacta (base 14px, row 30px) | — |
| Theme | Light only agora; tokens prontos pra dark mode futuro | — |
| Devices | Desktop-first + tablet (≥1024px) | — |

## 5. Arquitetura: Feature-Sliced Design

### 5.1 Estrutura

```
frontend/src/
├── app/                      ← bootstrap
│   ├── providers/            ← QueryClientProvider, RouterProvider, ThemeProvider, ToastProvider
│   ├── styles/               ← tokens.css, reset.css
│   ├── router.tsx            ← config React Router v7 (públicas + privadas + ErrorBoundary)
│   └── index.tsx             ← entry
│
├── pages/                    ← composição de widgets por rota (1 page = 1 rota top-level)
│   ├── landing/              ← stub neste sub-projeto, completa em #3
│   ├── login/                ← stub neste sub-projeto, completa em #2
│   ├── prospecting/          ← placeholder neste sub-projeto, refatorada em #6
│   ├── pipeline/             ← placeholder, completa em #5
│   ├── not-found/
│   └── index.ts
│
├── widgets/                  ← blocos grandes compostos
│   ├── app-shell/            ← TopBar + SideNav + <Outlet/> (este sub-projeto)
│   ├── (outros vão entrando nos sub-projetos seguintes)
│   └── index.ts
│
├── features/                 ← casos de uso atômicos do usuário (vazio neste sub-projeto)
│   └── index.ts
│
├── entities/                 ← modelos de domínio puros (tipos + formatters)
│   ├── user/                 ← User type + UserAvatar (necessário pro TopBar mostrar avatar)
│   └── index.ts
│
└── shared/                   ← reutilizável, zero domínio
    ├── ui/                   ← primitivos + compostos do design system
    ├── api/                  ← axios client + interceptors
    ├── lib/                  ← cn, formatCnpj, formatDate, formatCurrency
    ├── hooks/                ← useDebounce, useMediaQuery, useFocusTrap, useKeyboardShortcut
    ├── config/               ← env constants (API_URL, etc)
    └── types/                ← Pagination, ApiError, etc
```

### 5.2 Regras de import (enforçadas via `@feature-sliced/eslint-config`)

| Camada | Pode importar de |
|---|---|
| `app` | tudo |
| `pages` | `widgets`, `features`, `entities`, `shared` |
| `widgets` | `features`, `entities`, `shared` |
| `features` | `entities`, `shared` |
| `entities` | `shared` |
| `shared` | (nada) |

**Slices irmãos não se importam** (ex.: `features/auth-by-credentials` ↛ `features/filter-companies`). Comunicação entre features é via composição na camada superior (`widgets` ou `pages`).

### 5.3 Public API por slice

Cada slice expõe somente o que está em seu `index.ts`. Imports externos consomem só esse barrel:

```ts
// ✅ correto
import { Button } from '@/shared/ui'
// ❌ proibido (acessa interno do slice)
import { Button } from '@/shared/ui/primitives/Button/Button.tsx'
```

Regra adicional ESLint: `no-restricted-imports` proibindo paths "profundos" em slices.

### 5.4 Aliases TS

```jsonc
// tsconfig.json paths
{ "@/app/*": ["./src/app/*"], "@/pages/*": ["./src/pages/*"],
  "@/widgets/*": ["./src/widgets/*"], "@/features/*": ["./src/features/*"],
  "@/entities/*": ["./src/entities/*"], "@/shared/*": ["./src/shared/*"] }
```

## 6. Design Tokens (sistema W3C-style 3 camadas)

### 6.1 Modelo

1. **Primitives** (Layer 1) — raw values, não usados em componentes
2. **Semantic** (Layer 2) — intent-based, **única camada que componentes consomem**
3. **Component** (Layer 3, opcional) — overrides locais

### 6.2 Arquivo `app/styles/tokens.css`

```css
@theme {
  /* === COLOR PRIMITIVES === */
  --color-navy-900: #071d41;
  --color-navy-800: #0c326f;
  --color-navy-700: #14438a;
  --color-blue-600: #1351b4;
  --color-blue-500: #2563cf;
  --color-blue-100: #e8efff;
  --color-blue-50:  #f4f7fd;

  --color-yellow-500: #ffcd07;
  --color-yellow-400: #ffd633;
  --color-yellow-100: #fff8db;

  --color-gray-900: #1a2333;
  --color-gray-700: #2a3950;
  --color-gray-600: #4a5878;
  --color-gray-500: #6c7a8c;
  --color-gray-400: #9aa6b8;
  --color-gray-300: #c8d0dc;
  --color-gray-200: #e3e7ef;
  --color-gray-100: #eef1f6;
  --color-gray-50:  #f6f8fb;

  --color-green-600: #1e7e34;
  --color-green-100: #e6f4ea;
  --color-red-600:   #c0392b;
  --color-red-100:   #fbeae6;
  --color-amber-600: #92590a;
  --color-amber-100: #fff4e0;

  /* === COLOR SEMANTIC (consumido por componentes) === */
  --color-bg-app:        var(--color-gray-50);
  --color-bg-surface:    #ffffff;
  --color-bg-subtle:     var(--color-gray-100);
  --color-bg-inverse:    var(--color-navy-800);

  --color-fg-primary:    var(--color-gray-900);
  --color-fg-secondary:  var(--color-gray-600);
  --color-fg-muted:      var(--color-gray-500);
  --color-fg-on-inverse: #ffffff;

  --color-action:        var(--color-blue-600);
  --color-action-hover:  var(--color-navy-700);
  --color-action-fg:     #ffffff;

  --color-brand:         var(--color-yellow-500);
  --color-brand-fg:      var(--color-gray-900);

  --color-border:        var(--color-gray-200);
  --color-border-strong: var(--color-gray-300);
  --color-focus-ring:    var(--color-blue-500);

  --color-success: var(--color-green-600); --color-success-bg: var(--color-green-100);
  --color-danger:  var(--color-red-600);   --color-danger-bg:  var(--color-red-100);
  --color-warning: var(--color-amber-600); --color-warning-bg: var(--color-amber-100);
  --color-info:    var(--color-blue-600);  --color-info-bg:    var(--color-blue-100);

  /* === SPACING (4px base) === */
  --spacing-0: 0; --spacing-1: 4px; --spacing-2: 8px; --spacing-3: 12px;
  --spacing-4: 16px; --spacing-5: 20px; --spacing-6: 24px; --spacing-8: 32px;
  --spacing-10: 40px; --spacing-12: 48px; --spacing-16: 64px;

  /* === TYPOGRAPHY === */
  --font-sans: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;

  --text-xs:   11px;   --text-xs-lh:   16px;
  --text-sm:   12.5px; --text-sm-lh:   18px;
  --text-base: 14px;   --text-base-lh: 20px;
  --text-md:   16px;   --text-md-lh:   24px;
  --text-lg:   18px;   --text-lg-lh:   26px;
  --text-xl:   22px;   --text-xl-lh:   30px;
  --text-2xl:  28px;   --text-2xl-lh:  36px;
  --text-3xl:  36px;   --text-3xl-lh:  44px;

  --font-weight-regular:  400;
  --font-weight-medium:   500;
  --font-weight-semibold: 600;
  --font-weight-bold:     700;

  /* === RADIUS === */
  --radius-none: 0; --radius-sm: 4px; --radius-md: 6px;
  --radius-lg: 8px; --radius-xl: 12px; --radius-pill: 999px;

  /* === SHADOW === */
  --shadow-sm: 0 1px 2px rgba(7,29,65,.06), 0 0 0 1px rgba(7,29,65,.04);
  --shadow-md: 0 4px 8px rgba(7,29,65,.08), 0 0 0 1px rgba(7,29,65,.05);
  --shadow-lg: 0 12px 24px rgba(7,29,65,.12), 0 0 0 1px rgba(7,29,65,.06);
  --shadow-focus: 0 0 0 3px rgba(37,99,207,.35);

  /* === MOTION === */
  --motion-duration-fast: 120ms;
  --motion-duration-base: 200ms;
  --motion-duration-slow: 320ms;
  --motion-easing-standard:   cubic-bezier(.2, 0, 0, 1);
  --motion-easing-emphasized: cubic-bezier(.3, 0, 0, 1);

  /* === Z-INDEX === */
  --z-base: 0; --z-dropdown: 1000; --z-sticky: 1100;
  --z-modal-backdrop: 1200; --z-modal: 1300; --z-popover: 1400;
  --z-tooltip: 1500; --z-toast: 1600;
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --motion-duration-fast: 0ms;
    --motion-duration-base: 0ms;
    --motion-duration-slow: 0ms;
  }
}
```

### 6.3 Contraste WCAG (validado em CI com axe-core)

| Par | Ratio | Nível |
|---|---|---|
| fg-primary sobre bg-app | 13.4:1 | AAA |
| fg-secondary sobre bg-app | 6.8:1 | AAA |
| fg-muted sobre bg-app | 4.7:1 | AA |
| action-fg sobre action | 6.0:1 | AA |
| brand-fg sobre brand | 12.6:1 | AAA |
| action sobre bg-surface | 6.0:1 | AA |

## 7. Inventário de componentes (`shared/ui/`)

Cada componente é construído com Radix UI como base (acessibilidade), estilizado com Tailwind v4, variantes com `class-variance-authority` (cva), animações com Framer Motion onde aplicável.

### 7.1 `shared/ui/primitives/`

| Componente | Base | Variantes |
|---|---|---|
| Button | `<button>` | variant: primary/secondary/ghost/danger/link · size: sm/md/lg · icon-only · loading |
| IconButton | Button + size:icon | tooltip obrigatório |
| Input | `<input>` | size: sm/md · invalid · com leading/trailing icon |
| Textarea | `<textarea>` | autosize opcional |
| Select | Radix Select | size: sm/md · com search opcional |
| Combobox | Radix Popover + cmdk | async search |
| Checkbox | Radix Checkbox | — |
| RadioGroup | Radix RadioGroup | — |
| Switch | Radix Switch | — |
| Slider | Radix Slider | range opcional |
| Label | `<label>` | required-marker, associado por id |
| FormField | composição (Label + Input + HelperText + ErrorText) | usa RHF context |
| Tooltip | Radix Tooltip | delay default 400ms |
| Popover | Radix Popover | — |
| DropdownMenu | Radix DropdownMenu | — |
| Dialog | Radix Dialog | size: sm/md/lg/xl/fullscreen · Framer enter/exit |
| AlertDialog | Radix AlertDialog | destructive variant |
| Tabs | Radix Tabs | underline/segmented variants |
| Badge | `<span>` | variant: neutral/info/success/warning/danger/brand · com leading icon |
| Avatar | Radix Avatar | fallback iniciais |
| Separator | Radix Separator | horizontal/vertical |
| Spinner | SVG | sizes |
| VisuallyHidden | Radix VisuallyHidden | acessibilidade |
| Kbd | `<kbd>` styled | — |

### 7.2 `shared/ui/data/`

| Componente | Notas |
|---|---|
| DataTable | TanStack Table v8 + `@tanstack/react-virtual` para virtualização. Suporta column visibility, sorting, sticky header, row selection. Não conhece domínio. |
| Pagination | cursor-based (compatível com a API existente) + page-size |
| EmptyState | composição: ícone + título + descrição + CTA opcional |
| Skeleton | block-level + text-line variants |
| Stat | número grande + label + delta opcional |

### 7.3 `shared/ui/feedback/`

| Componente | Base | Notas |
|---|---|---|
| Toast | sonner (lib) com tema customizado | success/error/warning/info; auto-dismiss configurável |
| Alert | inline | mesmas variants do Badge |
| Banner | full-width | dismissible, persistente em localStorage opcional |
| ConfirmDialog | composição sobre AlertDialog | api imperativa: `confirm({title, body, ...})` |

### 7.4 `shared/ui/layout/`

| Componente | Notas |
|---|---|
| AppShell | layout autenticado: TopBar + SideNav + Outlet + opcional Aside |
| TopBar | logo + search global (cmdk) + nav direita (ajuda, notificações, avatar) |
| SideNav | sidebar fina 56px com ícones + tooltip; rota ativa marca barra amarela |
| PageHeader | título + breadcrumb + actions à direita |
| Container | max-width + padding responsivo |
| Stack/Inline | composições de flex com gap tokens |

### 7.5 `shared/ui/icons/`

Re-export curado de lucide-react. **Só os ícones em uso** ficam no barrel (tree-shaking garantido). Isto evita que devs importem 1000+ ícones por engano.

```ts
// shared/ui/icons/index.ts
export { Search, Plus, Eye, LayoutGrid, Bookmark, BarChart3,
         Settings, Bell, CircleHelp, Check, CircleAlert,
         Star, X, ChevronDown, ... } from 'lucide-react'
```

## 8. App Shell

### 8.1 Layout

```
┌─────────────────────────────────────────────────────────────┐
│ TopBar (56px)  Logo · ⌘K Search · Ajuda · 🔔 · Avatar       │ ← bg-inverse
├──────┬──────────────────────────────────────────────────────┤
│ Side │                                                       │
│ Nav  │                                                       │
│ (56) │              <Outlet />                               │ ← bg-app
│  🔍  │           (renderiza a Page atual)                    │
│  ▦   │                                                       │
│  ⛁   │                                                       │
│  📊  │                                                       │
│  ⚙   │                                                       │
└──────┴──────────────────────────────────────────────────────┘
```

### 8.2 Comportamento

- **Logo (TopBar)**: link pra `/app` (home autenticada)
- **Search ⌘K**: abre `cmdk` Dialog com busca global (hook futuro `useGlobalSearch`); neste sub-projeto fica stub
- **SideNav ícones** com `aria-label` + Tooltip. Itens: Prospecting, Pipeline, Listas, Relatórios, Configurações (Configurações fica no rodapé do SideNav, demais no topo)
- **Indicador de rota ativa**: barra amarela vertical 3px à esquerda do ícone ativo (não-só-cor por WCAG)
- **Hover/foco**: bg `rgba(255,255,255,.10)`, ícone passa de cinza pra branco
- **Hit area 40×40** (acima do mínimo WCAG 24×24, próximo do recomendado 44×44)
- **Avatar**: dropdown com nome + email + sair (item "sair" só após sub-projeto #2)
- **Notificações**: dropdown stub neste sub-projeto

### 8.3 Acessibilidade

- TopBar e SideNav são `<header>` e `<nav aria-label="Navegação principal">`
- Pulo de navegação: link "Pular para o conteúdo" visível ao focar (primeiro tab)
- Foco trap em modais e popovers (Radix faz nativamente)
- Atalho `Esc` fecha popovers/modais (Radix)
- Atalho `/` foca a busca global (custom hook `useKeyboardShortcut`)

## 9. Roteamento (React Router v7, data router mode)

### 9.1 Estrutura

```
/                         ← landing pública (lazy)
/login                    ← stub (sub-projeto #2)
/registro                 ← stub
/recuperar-senha          ← stub
─────────── protected ───────────
/app                      ← dashboard home (placeholder)
/app/prospecting          ← página atual (placeholder neste sub-projeto)
/app/pipeline             ← placeholder
/app/listas               ← placeholder
/app/relatorios           ← placeholder
/app/configuracoes        ← placeholder
*                         ← 404
```

### 9.2 ProtectedRoute (stub para #2 plugar auth real)

```ts
// app/router.tsx
const isAuthenticated = () => true  // stub; substituído em #2

const protectedLoader: LoaderFunction = () => {
  if (!isAuthenticated()) throw redirect('/login')
  return null
}
```

### 9.3 Code-splitting

Toda `pages/*` é importada via `React.lazy()`. Suspense boundary em volta do `<Outlet />` mostra Skeleton genérico durante carregamento.

### 9.4 ErrorBoundary por rota

`errorElement` em cada rota usando RouteErrorBoundary do React Router v7. Mostra mensagem amigável + botão "Recarregar" + link "Voltar ao início". Erros 5xx são reportados a um endpoint `POST /v1/client-errors` (será criado em #2).

## 10. Padrões transversais

### 10.1 Loading states

- **Skeleton-first.** Sem spinners de página inteira. Cada DataTable/Card mostra seu próprio Skeleton.
- **Spinner inline pequeno** apenas em ações (botão durante submit).
- **Suspense + lazy** para rotas; Suspense fallback é Skeleton.

### 10.2 Empty states

- Sempre composto: `<EmptyState icon title description action />`
- 3 variants pré-prontas:
  - `no-results` (busca/filtro retornou vazio): ícone `SearchX`, sugere "ajustar filtros"
  - `not-started` (usuário ainda não criou nada): ícone contextual + CTA primário
  - `error` (falha na API): ícone `CircleAlert`, botão "Tentar novamente"

### 10.3 Error handling

- **Axios interceptor** mapeia erros HTTP pra `ApiError` tipado: `{ code, message, fieldErrors? }`
- TanStack Query usa `useQuery({ onError })` → toast `danger` automático para 5xx
- 4xx (validação) volta pra componente lidar (form mostra inline)
- 401/403 redireciona pra `/login` (em #2)
- ErrorBoundary global no `app/` captura crashes não tratados, mostra fallback + reporta

### 10.4 Toasts

- Lib: `sonner` (acessível, leve, customizável)
- Posição: top-right (padrão SaaS)
- Auto-dismiss: 4s para info/success, 8s para warning, manual-dismiss para danger
- Stack máx 3 (excesso fica em fila)

### 10.5 Modais e diálogos

- Padrão Radix Dialog (focus trap, escape close, click-outside close, scroll lock)
- Animação Framer: scale 0.95→1 + fade, 200ms, easing-standard
- Confirmações destrutivas via `ConfirmDialog` (api imperativa)

### 10.6 Formulários

- React Hook Form + Zod resolver
- Validação **só de formato** (regex CNPJ, email, comprimento mín) — **nunca regra de negócio**, que mora no backend
- Erros do backend (4xx) mapeados pra `setError` por campo
- Estado de submit: botão `loading` + disabled
- Foco automático no primeiro campo inválido

## 11. Performance

### 11.1 Budget

| Métrica | Alvo |
|---|---|
| Bundle inicial (gz) | ≤ 200 kB |
| JS por rota (gz) | ≤ 80 kB |
| Largest Contentful Paint (LCP) | ≤ 2.0s (4G simulado) |
| First Input Delay / INP | ≤ 200ms |
| Cumulative Layout Shift (CLS) | ≤ 0.05 |
| Lighthouse Performance | ≥ 90 (desktop) |

### 11.2 Técnicas

- Route-level code-splitting (`React.lazy`)
- Framer Motion lazy-load (importação dinâmica em widgets que usam)
- Imagens via `<img loading="lazy">` + AVIF/WebP quando aplicável
- Fonts: Inter via Google Fonts com `font-display: swap`, preconnect e preload do woff2 principal
- Tailwind v4 (compilação no Vite, sem PostCSS overhead)
- TanStack Query: staleTime padrão 60s, cacheTime 5min, sem refetch on window focus em queries de prospecção (pesadas)
- Virtualização obrigatória em qualquer lista > 100 itens (`@tanstack/react-virtual`)

### 11.3 CI checks

- `vite build --report` → falha se bundle inicial > 220 kB gz (margem 10%)
- Lighthouse CI em PR → falha se Performance < 85

## 12. Acessibilidade (WCAG 2.2 AA)

### 12.1 Garantias

- Todos os componentes Radix-based herdam ARIA correto, foco gerenciado, navegação por teclado
- Cor nunca é o único portador de informação (rota ativa = cor + barra; badge = cor + ícone + texto)
- Contrastes mínimos validados em CI (ver §6.3)
- Foco visível em todos os elementos interativos (anel `--shadow-focus`)
- Idioma na raiz: `<html lang="pt-BR">`
- Landmarks: `<header>`, `<nav>`, `<main>`, `<footer>`
- Skip link "Pular para o conteúdo" visível ao primeiro tab
- `prefers-reduced-motion` respeitado (tokens zerados; Framer `useReducedMotion`)
- Hit area mínima 40×40 em controles principais (44×44 onde possível)

### 12.2 CI

- `vitest-axe` roda em cada componente de `shared/ui/`
- Playwright + `@axe-core/playwright` em rotas principais (smoke)

### 12.3 Manual checklist por PR

- Navegar com Tab/Shift+Tab até o fim — ordem faz sentido?
- Acionar com Enter/Space funciona?
- Esc fecha modais e popovers?
- Screen reader (VoiceOver/NVDA) lê o suficiente?

## 13. Segurança do frontend

### 13.1 Princípio "regra de negócio não vaza"

- **Nada de cálculo de preço, regra de elegibilidade, regra de filtro, etc no client.** Tudo isso vem da API.
- `entities/` no FSD contém tipos e formatadores; **proibido** lógica condicional baseada em dado de domínio sem chamar API.
- ESLint rule customizada (ou code review checklist) bloqueia constantes de regra (ex.: `const PREMIUM_PRICE = 49.90` em `entities/`).
- Variáveis de ambiente no Vite são prefixadas `VITE_*` e expostas — só endpoints e flags públicas vão por aí; jamais secrets.

### 13.2 CSP (Content Security Policy)

Configurado no Nginx (já existe):

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'wasm-unsafe-eval';
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
  font-src 'self' https://fonts.gstatic.com;
  img-src 'self' data: https:;
  connect-src 'self' [API_URL];
  frame-ancestors 'none';
  object-src 'none';
  base-uri 'self';
```

Headers adicionais:
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`

(HSTS já presumido em produção; vai ser revisto no sub-projeto de auth #2.)

### 13.3 Dependency hygiene

- `npm audit` em CI (falha em high+critical)
- Renovate bot ou Dependabot semanal
- Sem libs com manutenção parada; preferir libs com release recente (≤ 6 meses)
- Lock file versionado, `npm ci` no CI

### 13.4 Storage

- Nada de PII em localStorage. Preferência de usuário (densidade futura) → ok. Token de auth não — fica em cookie httpOnly secure samesite=strict (sub-projeto #2).

### 13.5 Input sanitization

- React já escapa por default; nunca usar `dangerouslySetInnerHTML`. Lint rule bloqueia.
- HTML rico (se necessário no futuro): DOMPurify obrigatório.
- URLs vindas do backend usadas em `<a href>`: validar protocolo `http/https` antes de renderizar.

## 14. Testes

### 14.1 Pirâmide (Test Trophy adaptado)

- **Static**: TypeScript strict + ESLint (FSD plugin + react-hooks + a11y + import/no-restricted-paths)
- **Unit**: Vitest para formatters/hooks/utils em `shared/lib`, `shared/hooks`
- **Component**: Vitest + RTL para cada componente de `shared/ui/` (render, interação, a11y via vitest-axe)
- **Integration**: RTL para widgets compostos (`widgets/app-shell` com router mockado)
- **E2E**: Playwright smoke em rotas principais (login stub → home → navegar tabs → 404)

### 14.2 Cobertura

- Repo Python já tem 100% (não baixar)
- Frontend novo: alvo **80%** para `shared/ui/`, `shared/lib`, `shared/hooks`. Pages e widgets em smoke E2E.

### 14.3 Visual regression (opcional, fase 2)

- Avaliar Playwright snapshots em CI depois que UI estabilizar; fora de escopo neste sub-projeto.

## 15. Migração da página Prospecting atual

Esta refatoração completa fica para **sub-projeto #6**. No #1, a página é movida intacta para `pages/prospecting/` como placeholder, mas embrulhada pelo novo `AppShell`. Não tocar em filtros/tabela/lógica de domínio aqui.

Componentes atuais (`BairroAutocomplete`, `CnaeSelector`, `FilterPanel`, `ResultsTable`, etc.) ficam onde estão até #6 reescrevê-los com o novo design system.

## 16. Dependências novas (a adicionar em #1)

| Pacote | Por quê |
|---|---|
| `react-router` ^7 | roteamento data router |
| `@radix-ui/*` (vários) | primitives a11y |
| `class-variance-authority` | variantes tipadas |
| `clsx` + `tailwind-merge` | helper `cn()` |
| `@tanstack/react-table` ^8 | DataTable |
| `@tanstack/react-virtual` | virtualização |
| `react-hook-form` + `zod` + `@hookform/resolvers` | forms |
| `framer-motion` | animações |
| `sonner` | toasts |
| `cmdk` | command palette |
| `@feature-sliced/eslint-config` | enforça FSD |
| `vitest-axe` + `@axe-core/playwright` | a11y |

## 17. Fora de escopo (explícito)

- ❌ Auth real (login backend, JWT, recovery) → #2
- ❌ Landing page com conteúdo completo → #3
- ❌ Pipeline backend (tabelas, endpoints write) → #4
- ❌ Pipeline frontend (kanban, drag-drop) → #5
- ❌ Refatorar Prospecting com novo DS → #6
- ❌ Dark mode (tokens prontos, mas tema escuro fica pra depois)
- ❌ Mobile (≤ 1023px); só desktop+tablet
- ❌ Visual regression testing
- ❌ i18n (só pt-BR neste momento)

## 18. Sucesso = checklist

- [ ] Estrutura FSD criada com ESLint plugin configurado
- [ ] `app/styles/tokens.css` completo
- [ ] Todos os componentes de `shared/ui/` listados em §7 entregues com testes (≥80% cov)
- [ ] `widgets/app-shell` funcionando: TopBar + SideNav + Outlet
- [ ] React Router v7 configurado com 9 rotas (5 placeholder, 4 stub)
- [ ] Página atual de Prospecting movida para `pages/prospecting/` sem regressão funcional
- [ ] CSP + headers de segurança no Nginx
- [ ] Lighthouse Performance ≥ 90 desktop
- [ ] axe-core 0 violações em smoke E2E
- [ ] Bundle inicial ≤ 200 kB gz

## 19. Riscos

| Risco | Mitigação |
|---|---|
| Tailwind v4 ainda recente, mudanças breaking | Pinning de versão exata, smoke teste em CI |
| FSD strict frustra desenvolvedores no início | Doc de onboarding (`docs/architecture.md`) + exemplos em PR review |
| Bundle estourar com Radix + Framer | Lazy-load Framer; tree-shake Radix por import nomeado; budget no CI |
| Inter no Google Fonts pode falhar em produção | `font-display: swap` + fallback system-ui; considerar self-hosting na fase 2 |
| Refatoração tocar Prospecting atual e quebrar features | #1 só **move** Prospecting; refactor real fica em #6 com testes regressivos |

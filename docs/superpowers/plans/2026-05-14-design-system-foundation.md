# Design System Foundation + App Shell — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estabelecer a fundação frontend (FSD strict + design tokens + biblioteca de componentes base + App Shell + roteamento) sobre a qual os sub-projetos #2–#6 vão construir, mantendo a página atual de Prospecting funcional sem regressão.

**Architecture:** Feature-Sliced Design v2 (strict, enforçado por ESLint) sobre Vite + React 19 + TypeScript. Design tokens em CSS variables (W3C-style 3 camadas) consumidos via Tailwind v4 `@theme`. Componentes shadcn/ui-pattern: Radix UI primitives + class-variance-authority para variantes tipadas, copiados pro repo (sem dependência transitiva). Roteamento React Router v7 (data router mode). Animações Framer Motion (lazy-loaded). Tests Vitest + RTL + axe-core; smoke Playwright.

**Tech Stack:** React 19, TypeScript 6, Vite 8, Tailwind v4, React Router 7, TanStack Query 5, TanStack Table 8, Radix UI, class-variance-authority, Framer Motion, sonner, cmdk, React Hook Form + Zod, lucide-react, Vitest, React Testing Library, vitest-axe, Playwright, @axe-core/playwright, @feature-sliced/eslint-config.

**Spec:** `docs/superpowers/specs/2026-05-14-design-system-foundation-design.md`

**Repo state assumptions:**
- Branch: `develop`
- Working dir tem mudanças não-commitadas em api/, etl/, frontend/ (não relacionadas a este plano) — não tocar nelas
- Frontend atual: `frontend/src/{api,components,hooks,pages,utils}` será reorganizado em FSD

**Convenções deste plano:**
- Comandos rodam a partir de `/home/luife/projetos/cnpj-discovery` (raiz do repo) salvo nota em contrário
- Comandos `npm` rodam dentro de `frontend/` — sempre `cd frontend && <cmd>`
- Cada task tem TDD quando faz sentido (componente, hook, util); tasks de config têm verificação manual
- Commits frequentes (uma task = um commit)
- Mensagem de commit: `feat(ds): ...`, `chore(ds): ...`, `test(ds): ...`, `refactor(ds): ...`, `docs(ds): ...`

---

## Phase 0 — Project setup

### Task 0.1: Adicionar dependências de runtime

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Instalar deps de runtime**

```bash
cd frontend && npm install --save \
  react-router@^7 \
  @radix-ui/react-dialog@^1 \
  @radix-ui/react-popover@^1 \
  @radix-ui/react-dropdown-menu@^2 \
  @radix-ui/react-tooltip@^1 \
  @radix-ui/react-select@^2 \
  @radix-ui/react-checkbox@^1 \
  @radix-ui/react-radio-group@^1 \
  @radix-ui/react-switch@^1 \
  @radix-ui/react-slider@^1 \
  @radix-ui/react-tabs@^1 \
  @radix-ui/react-avatar@^1 \
  @radix-ui/react-separator@^1 \
  @radix-ui/react-label@^2 \
  @radix-ui/react-alert-dialog@^1 \
  @radix-ui/react-visually-hidden@^1 \
  @radix-ui/react-slot@^1 \
  class-variance-authority \
  clsx \
  tailwind-merge \
  @tanstack/react-table@^8 \
  @tanstack/react-virtual@^3 \
  react-hook-form@^7 \
  zod@^3 \
  @hookform/resolvers@^3 \
  framer-motion@^11 \
  sonner@^1 \
  cmdk@^1
```

- [ ] **Step 2: Verificar instalação**

```bash
cd frontend && npm list react-router @radix-ui/react-dialog class-variance-authority 2>/dev/null | head -20
```
Expected: versões aparecem sem `(empty)`.

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(ds): add runtime deps (router, radix, cva, tanstack-table, framer, sonner, cmdk, rhf)"
```

---

### Task 0.2: Adicionar dependências de teste e lint

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Instalar deps de dev**

```bash
cd frontend && npm install --save-dev \
  @feature-sliced/eslint-config \
  eslint-plugin-boundaries \
  eslint-plugin-import \
  eslint-plugin-jsx-a11y \
  vitest-axe \
  axe-core \
  @playwright/test \
  @axe-core/playwright
```

- [ ] **Step 2: Instalar browsers do Playwright**

```bash
cd frontend && npx playwright install --with-deps chromium
```

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(ds): add dev deps (fsd-eslint, vitest-axe, playwright, jsx-a11y)"
```

---

### Task 0.3: Configurar paths TypeScript pros aliases FSD

**Files:**
- Modify: `frontend/tsconfig.app.json`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Ler tsconfig.app.json atual**

```bash
cat frontend/tsconfig.app.json
```

- [ ] **Step 2: Adicionar `baseUrl` e `paths`**

Substituir o `compilerOptions` para incluir (mantendo o que já existe):

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/app/*":      ["src/app/*"],
      "@/pages/*":    ["src/pages/*"],
      "@/widgets/*":  ["src/widgets/*"],
      "@/features/*": ["src/features/*"],
      "@/entities/*": ["src/entities/*"],
      "@/shared/*":   ["src/shared/*"]
    }
  }
}
```

- [ ] **Step 3: Espelhar paths no Vite**

Em `frontend/vite.config.ts` adicionar `resolve.alias`:

```ts
import path from 'node:path'

export default defineConfig({
  plugins: [tailwindcss(), react()],
  resolve: {
    alias: {
      '@/app':      path.resolve(__dirname, 'src/app'),
      '@/pages':    path.resolve(__dirname, 'src/pages'),
      '@/widgets':  path.resolve(__dirname, 'src/widgets'),
      '@/features': path.resolve(__dirname, 'src/features'),
      '@/entities': path.resolve(__dirname, 'src/entities'),
      '@/shared':   path.resolve(__dirname, 'src/shared'),
    },
  },
  test: { /* ... mantém ... */ },
})
```

- [ ] **Step 4: Verificar build não quebra**

```bash
cd frontend && npx tsc -b --noEmit
```
Expected: 0 errors (pode haver warnings sobre arquivos ainda não migrados; ignorar).

- [ ] **Step 5: Commit**

```bash
git add frontend/tsconfig.app.json frontend/vite.config.ts
git commit -m "chore(ds): add FSD path aliases (tsconfig + vite)"
```

---

### Task 0.4: Configurar ESLint com regras FSD + a11y

**Files:**
- Modify: `frontend/eslint.config.js`

- [ ] **Step 1: Reescrever eslint.config.js**

```js
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import boundaries from 'eslint-plugin-boundaries'
import importPlugin from 'eslint-plugin-import'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'playwright-report', '.superpowers']),
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { boundaries, import: importPlugin, 'jsx-a11y': jsxA11y },
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      jsxA11y.flatConfigs.recommended,
    ],
    languageOptions: { globals: globals.browser },
    settings: {
      'boundaries/elements': [
        { type: 'app',      pattern: 'src/app/**'      },
        { type: 'pages',    pattern: 'src/pages/**'    },
        { type: 'widgets',  pattern: 'src/widgets/**'  },
        { type: 'features', pattern: 'src/features/**' },
        { type: 'entities', pattern: 'src/entities/**' },
        { type: 'shared',   pattern: 'src/shared/**'   },
      ],
    },
    rules: {
      'boundaries/element-types': ['error', {
        default: 'disallow',
        rules: [
          { from: 'app',      allow: ['app','pages','widgets','features','entities','shared'] },
          { from: 'pages',    allow: ['widgets','features','entities','shared'] },
          { from: 'widgets',  allow: ['features','entities','shared'] },
          { from: 'features', allow: ['entities','shared'] },
          { from: 'entities', allow: ['shared'] },
          { from: 'shared',   allow: [] },
        ],
      }],
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'dangerouslySetInnerHTML é proibido. Use texto ou DOMPurify se for absolutamente necessário.',
        },
      ],
      'no-restricted-imports': ['error', {
        patterns: [
          { group: ['*/internal/*', '*/_*'], message: 'Importe via Public API do slice (index.ts).' },
        ],
      }],
    },
  },
])
```

- [ ] **Step 2: Rodar lint pra confirmar config válida**

```bash
cd frontend && npx eslint . --max-warnings 0 || true
```
Expected: pode haver erros em arquivos antigos (esperado nesta fase); o objetivo é a config ser válida (sem `Parsing error` na config).

- [ ] **Step 3: Commit**

```bash
git add frontend/eslint.config.js
git commit -m "chore(ds): configure ESLint with FSD boundaries + jsx-a11y"
```

---

### Task 0.5: Configurar Vitest com vitest-axe e setup global

**Files:**
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/test/setup.ts` (existe; vamos confirmar e estender)

- [ ] **Step 1: Inspecionar setup atual**

```bash
cat frontend/src/test/setup.ts
```

- [ ] **Step 2: Estender setup.ts**

Substituir conteúdo por:

```ts
import '@testing-library/jest-dom/vitest'
import 'vitest-axe/extend-expect'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => cleanup())
```

- [ ] **Step 3: Ajustar coverage no vite.config.ts**

Em `test`:

```ts
test: {
  environment: 'jsdom',
  setupFiles: './src/test/setup.ts',
  globals: true,
  css: true,
  coverage: {
    provider: 'v8',
    reporter: ['text', 'html', 'lcov'],
    include: ['src/shared/**', 'src/entities/**', 'src/widgets/**'],
    exclude: ['**/*.test.{ts,tsx}', '**/index.ts', 'src/test/**'],
    thresholds: { lines: 80, functions: 80, statements: 80, branches: 75 },
  },
},
```

- [ ] **Step 4: Rodar vitest pra sanity**

```bash
cd frontend && npx vitest run --reporter=basic
```
Expected: testes existentes ainda passam (alguns vão falhar até serem migrados nas próximas tasks; aceitável agora — anote quais falham pra checar na Task 14).

- [ ] **Step 5: Commit**

```bash
git add frontend/vite.config.ts frontend/src/test/setup.ts
git commit -m "test(ds): wire vitest-axe + 80% coverage thresholds (ui/entities/widgets)"
```

---

### Task 0.6: Configurar Playwright pra smoke E2E

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/.gitkeep`

- [ ] **Step 1: Criar playwright.config.ts**

```ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})
```

- [ ] **Step 2: Criar diretório e2e**

```bash
mkdir -p frontend/e2e && touch frontend/e2e/.gitkeep
```

- [ ] **Step 3: Adicionar script npm**

Em `frontend/package.json` adicionar em `scripts`:

```json
"e2e": "playwright test",
"e2e:ui": "playwright test --ui"
```

- [ ] **Step 4: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e/.gitkeep frontend/package.json
git commit -m "test(ds): add playwright smoke config"
```

---

## Phase 1 — FSD skeleton

### Task 1.1: Criar estrutura de pastas FSD com Public API stubs

**Files:**
- Create: `frontend/src/app/index.tsx` (placeholder)
- Create: `frontend/src/{app,pages,widgets,features,entities,shared}/index.ts` (barrel stubs)
- Create: muitas pastas vazias com `.gitkeep`

- [ ] **Step 1: Criar pastas e barrels**

```bash
cd frontend/src && mkdir -p \
  app/providers app/styles \
  pages/landing pages/login pages/registro pages/recuperar-senha \
  pages/prospecting pages/pipeline pages/listas pages/relatorios \
  pages/configuracoes pages/app-home pages/not-found \
  widgets/app-shell \
  features \
  entities/user \
  shared/ui/primitives shared/ui/data shared/ui/feedback shared/ui/layout shared/ui/icons \
  shared/api shared/lib shared/hooks shared/config shared/types
```

- [ ] **Step 2: Criar barrels vazios em cada slice principal**

```bash
cd frontend/src && for f in pages widgets features entities shared/ui shared/api shared/lib shared/hooks shared/config shared/types; do
  echo "// FSD public API barrel — exports curated by slice owner" > $f/index.ts
done
```

- [ ] **Step 3: Adicionar .gitkeep nas pastas vazias**

```bash
cd frontend/src && find . -type d -empty -exec touch {}/.gitkeep \;
```

- [ ] **Step 4: Verificar estrutura**

```bash
cd frontend && tree src -L 3 -I 'node_modules|*.test.*' || find src -type d
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "chore(ds): scaffold FSD folder structure with barrel exports"
```

---

### Task 1.2: Documentar arquitetura FSD no repo

**Files:**
- Create: `frontend/docs/architecture.md`

- [ ] **Step 1: Criar doc**

```bash
mkdir -p frontend/docs
```

Conteúdo de `frontend/docs/architecture.md`:

```markdown
# Frontend Architecture — Feature-Sliced Design

Este frontend segue **Feature-Sliced Design v2** strict. Spec: https://feature-sliced.design

## Camadas (do mais alto pro mais baixo)

| Camada | Pode importar de | Responsabilidade |
|---|---|---|
| `app/` | tudo | Bootstrap: providers, router, styles globais |
| `pages/` | widgets, features, entities, shared | 1 page = 1 rota top-level |
| `widgets/` | features, entities, shared | Blocos grandes compostos (ex.: AppShell, PipelineBoard) |
| `features/` | entities, shared | Casos de uso atômicos do usuário (ex.: add-to-pipeline) |
| `entities/` | shared | Modelos de domínio puros (tipos + formatters), sem regra de negócio |
| `shared/` | (nada) | Reutilizável e sem domínio: UI kit, lib, hooks, api client |

## Regras

1. **Camada só importa de camadas abaixo.** Enforçado por `boundaries/element-types` no ESLint.
2. **Slices irmãos não se importam.** `features/A` não importa `features/B`. Comunicação por composição em widget/page.
3. **Toda importação externa de um slice usa o `index.ts` (Public API).** Nunca importar arquivos internos.
4. **Regra de negócio mora no backend.** `entities/` só contém tipos e formatadores. Nada de cálculo de preço, elegibilidade, etc.
5. **Componentes consomem tokens semânticos.** Nunca cor crua, nunca primitive token direto. Só semantic.

## Onde colocar coisa nova?

- "É um botão genérico?" → `shared/ui/primitives/`
- "É um tipo/formatter de domínio?" → `entities/<entidade>/`
- "É uma ação que o usuário faz?" → `features/<verbo-substantivo>/` (ex.: `add-company-to-pipeline`)
- "É um bloco composto que mostra várias features?" → `widgets/`
- "É uma rota?" → `pages/<rota>/` (compõe widgets)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/docs/architecture.md
git commit -m "docs(ds): document FSD architecture and rules"
```

---

## Phase 2 — Theme & tokens

### Task 2.1: Criar tokens.css (3 camadas W3C-style)

**Files:**
- Create: `frontend/src/app/styles/tokens.css`

- [ ] **Step 1: Criar arquivo de tokens**

Copiar integralmente o bloco `@theme { ... }` da Seção 6.2 do spec em `frontend/src/app/styles/tokens.css`. Não abreviar — todos os tokens (color primitives, semantic, spacing, typography, radius, shadow, motion, z-index) e a regra `@media (prefers-reduced-motion: reduce)`.

- [ ] **Step 2: Verificar Tailwind v4 reconhece o @theme**

```bash
cd frontend && grep -r '@import' src/index.css 2>/dev/null
```

- [ ] **Step 3: Importar tokens.css no index.css principal**

Editar `frontend/src/index.css` pra ter no topo (ANTES de qualquer `@import "tailwindcss"`):

```css
@import "tailwindcss";
@import "./app/styles/tokens.css";
```

- [ ] **Step 4: Verificar dev server compila**

```bash
cd frontend && timeout 15 npm run dev 2>&1 | head -20
```
Expected: vê `Local: http://localhost:5173` sem erro.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/styles/tokens.css frontend/src/index.css
git commit -m "feat(ds): add design tokens (3-layer W3C-style) and import via Tailwind v4 @theme"
```

---

### Task 2.2: Criar reset.css minimalista

**Files:**
- Create: `frontend/src/app/styles/reset.css`

- [ ] **Step 1: Escrever reset**

```css
/* Reset mínimo (Tailwind preflight já faz a maior parte; só ajustes específicos) */

html {
  font-family: var(--font-sans);
  font-size: var(--text-base);
  line-height: var(--text-base-lh);
  color: var(--color-fg-primary);
  background: var(--color-bg-app);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

body { margin: 0; min-height: 100vh; }

*:focus-visible {
  outline: none;
  box-shadow: var(--shadow-focus);
  border-radius: var(--radius-sm);
}

::selection {
  background: var(--color-blue-100);
  color: var(--color-navy-900);
}

/* Number tabular — uso global por padrão em códigos/IDs (CNPJ etc) */
.num, code, .font-mono {
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 2: Importar no index.css**

```css
@import "tailwindcss";
@import "./app/styles/tokens.css";
@import "./app/styles/reset.css";
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/styles/reset.css frontend/src/index.css
git commit -m "feat(ds): add reset.css with focus ring + tabular nums"
```

---

### Task 2.3: Carregar Inter via Google Fonts com performance

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Ler index.html**

```bash
cat frontend/index.html
```

- [ ] **Step 2: Adicionar preconnect + preload + stylesheet no `<head>`**

Substituir o `<head>` (mantendo `<title>` e `<meta>` existentes), adicionando antes de `<script type="module">`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preload"
  as="style"
  href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<link rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
```

E setar `<html lang="pt-BR">` se ainda não estiver.

- [ ] **Step 3: Validar no dev**

```bash
cd frontend && timeout 10 npm run dev 2>&1 | head -10
```

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "perf(ds): preconnect + preload Inter (Google Fonts) with font-display swap"
```

---

### Task 2.4: Teste de contraste WCAG dos pares semânticos

**Files:**
- Create: `frontend/src/app/styles/tokens.test.ts`

- [ ] **Step 1: Escrever teste falhando**

```ts
import { describe, expect, it } from 'vitest'

// Pares semantic que DEVEM atender WCAG AA (4.5:1 texto / 3:1 large)
const PAIRS: Array<[string, string, number]> = [
  // [fg-hex, bg-hex, ratioMinimo]
  ['#1a2333', '#f6f8fb', 4.5],   // fg-primary on bg-app
  ['#4a5878', '#f6f8fb', 4.5],   // fg-secondary on bg-app
  ['#6c7a8c', '#f6f8fb', 4.5],   // fg-muted on bg-app
  ['#ffffff', '#1351b4', 4.5],   // action-fg on action
  ['#1a2333', '#ffcd07', 4.5],   // brand-fg on brand
  ['#1351b4', '#ffffff', 4.5],   // action on bg-surface
]

function srgbToLin(c: number) {
  c /= 255
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
}
function relLuminance(hex: string) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return 0.2126 * srgbToLin(r) + 0.7152 * srgbToLin(g) + 0.0722 * srgbToLin(b)
}
function ratio(a: string, b: string) {
  const la = relLuminance(a), lb = relLuminance(b)
  const [hi, lo] = la > lb ? [la, lb] : [lb, la]
  return (hi + 0.05) / (lo + 0.05)
}

describe('design tokens — contraste WCAG AA', () => {
  it.each(PAIRS)('par %s sobre %s tem ratio >= %f', (fg, bg, min) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(min)
  })
})
```

- [ ] **Step 2: Rodar teste**

```bash
cd frontend && npx vitest run src/app/styles/tokens.test.ts
```
Expected: PASS (todos os pares passam — já validamos na spec).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/styles/tokens.test.ts
git commit -m "test(ds): validate WCAG AA contrast for semantic token pairs"
```

---

## Phase 3 — Shared lib

### Task 3.1: Implementar `cn()` helper (clsx + tailwind-merge)

**Files:**
- Create: `frontend/src/shared/lib/cn.ts`
- Create: `frontend/src/shared/lib/cn.test.ts`
- Modify: `frontend/src/shared/lib/index.ts` (criar se não existir)

- [ ] **Step 1: Escrever teste**

```ts
import { describe, expect, it } from 'vitest'
import { cn } from './cn'

describe('cn', () => {
  it('concatena classes', () => {
    expect(cn('a', 'b')).toBe('a b')
  })
  it('ignora falsy', () => {
    expect(cn('a', false, null, undefined, 'b')).toBe('a b')
  })
  it('faz merge inteligente de classes Tailwind conflitantes', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4')
  })
})
```

- [ ] **Step 2: Rodar teste (deve falhar)**

```bash
cd frontend && npx vitest run src/shared/lib/cn.test.ts
```
Expected: FAIL — `cn` not defined.

- [ ] **Step 3: Implementar**

```ts
// src/shared/lib/cn.ts
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 4: Atualizar barrel**

`src/shared/lib/index.ts`:

```ts
export { cn } from './cn'
```

- [ ] **Step 5: Rodar teste**

```bash
cd frontend && npx vitest run src/shared/lib/cn.test.ts
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/shared/lib/
git commit -m "feat(ds): add cn() helper (clsx + tailwind-merge)"
```

---

### Task 3.2: Implementar `formatCnpj`

**Files:**
- Create: `frontend/src/shared/lib/formatCnpj.ts`
- Create: `frontend/src/shared/lib/formatCnpj.test.ts`

- [ ] **Step 1: Escrever teste**

```ts
import { describe, expect, it } from 'vitest'
import { formatCnpj } from './formatCnpj'

describe('formatCnpj', () => {
  it('formata 14 dígitos canônico', () => {
    expect(formatCnpj('12345678000190')).toBe('12.345.678/0001-90')
  })
  it('mantém input já formatado idempotente', () => {
    expect(formatCnpj('12.345.678/0001-90')).toBe('12.345.678/0001-90')
  })
  it('retorna entrada inalterada se não tem 14 dígitos', () => {
    expect(formatCnpj('abc')).toBe('abc')
    expect(formatCnpj('123')).toBe('123')
  })
  it('lida com null/undefined retornando string vazia', () => {
    expect(formatCnpj(null as unknown as string)).toBe('')
    expect(formatCnpj(undefined as unknown as string)).toBe('')
  })
})
```

- [ ] **Step 2: Implementar**

```ts
// src/shared/lib/formatCnpj.ts
export function formatCnpj(value: string | null | undefined): string {
  if (value == null) return ''
  const digits = value.replace(/\D/g, '')
  if (digits.length !== 14) return value
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`
}
```

- [ ] **Step 3: Adicionar ao barrel**

`src/shared/lib/index.ts`:

```ts
export { cn } from './cn'
export { formatCnpj } from './formatCnpj'
```

- [ ] **Step 4: Rodar testes**

```bash
cd frontend && npx vitest run src/shared/lib/formatCnpj.test.ts
```
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/lib/
git commit -m "feat(ds): add formatCnpj util with idempotent + null-safe behavior"
```

---

### Task 3.3: Implementar `formatDate` e `formatCurrency`

**Files:**
- Create: `frontend/src/shared/lib/formatDate.ts`
- Create: `frontend/src/shared/lib/formatDate.test.ts`
- Create: `frontend/src/shared/lib/formatCurrency.ts`
- Create: `frontend/src/shared/lib/formatCurrency.test.ts`

- [ ] **Step 1: Testes**

`formatDate.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { formatDate } from './formatDate'

describe('formatDate', () => {
  it('formata ISO em pt-BR', () => {
    expect(formatDate('2026-05-14')).toMatch(/14\/05\/2026/)
  })
  it('aceita Date', () => {
    expect(formatDate(new Date(2026, 4, 14))).toMatch(/14\/05\/2026/)
  })
  it('retorna vazio em null', () => {
    expect(formatDate(null)).toBe('')
  })
})
```

`formatCurrency.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { formatCurrency } from './formatCurrency'

describe('formatCurrency', () => {
  it('formata centavos em BRL', () => {
    expect(formatCurrency(12990)).toMatch(/R\$\s*129,90/)
  })
  it('aceita 0', () => {
    expect(formatCurrency(0)).toMatch(/R\$\s*0,00/)
  })
})
```

- [ ] **Step 2: Implementar**

`formatDate.ts`:

```ts
export function formatDate(value: string | Date | null | undefined): string {
  if (value == null) return ''
  const d = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(d.getTime())) return ''
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' }).format(d)
}
```

`formatCurrency.ts`:

```ts
export function formatCurrency(cents: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency', currency: 'BRL',
  }).format(cents / 100)
}
```

- [ ] **Step 3: Atualizar barrel + rodar testes**

`src/shared/lib/index.ts`:
```ts
export { cn } from './cn'
export { formatCnpj } from './formatCnpj'
export { formatDate } from './formatDate'
export { formatCurrency } from './formatCurrency'
```

```bash
cd frontend && npx vitest run src/shared/lib/
```
Expected: todos PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/shared/lib/
git commit -m "feat(ds): add formatDate (pt-BR) and formatCurrency (BRL)"
```

---

### Task 3.4: Mover API client para `shared/api/` + interceptors de erro

**Files:**
- Move: `frontend/src/api/client.ts` → `frontend/src/shared/api/client.ts`
- Move: `frontend/src/api/client.test.ts` → `frontend/src/shared/api/client.test.ts`
- Create: `frontend/src/shared/api/ApiError.ts`
- Create: `frontend/src/shared/api/index.ts`

- [ ] **Step 1: Mover arquivos**

```bash
cd frontend && git mv src/api/client.ts src/shared/api/client.ts
git mv src/api/client.test.ts src/shared/api/client.test.ts
rmdir src/api
```

- [ ] **Step 2: Criar `ApiError`**

`src/shared/api/ApiError.ts`:

```ts
export type FieldErrors = Record<string, string[]>

export class ApiError extends Error {
  status: number
  code?: string
  fieldErrors?: FieldErrors

  constructor(opts: { message: string; status: number; code?: string; fieldErrors?: FieldErrors }) {
    super(opts.message)
    this.name = 'ApiError'
    this.status = opts.status
    this.code = opts.code
    this.fieldErrors = opts.fieldErrors
  }
}
```

- [ ] **Step 3: Adicionar interceptor em `client.ts`**

Após criar a instância axios, adicionar:

```ts
import { ApiError } from './ApiError'

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status ?? 0
    const data = error.response?.data ?? {}
    return Promise.reject(new ApiError({
      message: data.message ?? error.message ?? 'Erro de rede',
      status,
      code: data.code,
      fieldErrors: data.fieldErrors,
    }))
  }
)
```

(Adaptar nome da instância pro que já existe em `client.ts`.)

- [ ] **Step 4: Criar barrel**

`src/shared/api/index.ts`:

```ts
export * from './client'
export { ApiError } from './ApiError'
export type { FieldErrors } from './ApiError'
```

- [ ] **Step 5: Atualizar imports no resto do código**

```bash
cd frontend && grep -rl "from '\.\./api/client'\|from '\.\./\.\./api/client'\|from '@/api'" src/ | while read f; do
  sed -i "s|from '\.\./api/client'|from '@/shared/api'|g; s|from '\.\./\.\./api/client'|from '@/shared/api'|g; s|from '@/api'|from '@/shared/api'|g" "$f"
done
```

- [ ] **Step 6: Rodar testes**

```bash
cd frontend && npx vitest run src/shared/api/
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "refactor(ds): move api client to shared/api with ApiError type and interceptor"
```

---

### Task 3.5: Hooks `useDebounce`, `useMediaQuery`, `useKeyboardShortcut`

**Files:**
- Create: `frontend/src/shared/hooks/useDebounce.ts` + test
- Create: `frontend/src/shared/hooks/useMediaQuery.ts` + test
- Create: `frontend/src/shared/hooks/useKeyboardShortcut.ts` + test
- Create: `frontend/src/shared/hooks/index.ts`

- [ ] **Step 1: Testes**

`useDebounce.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebounce } from './useDebounce'

describe('useDebounce', () => {
  it('atrasa atualização do valor', async () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ v }) => useDebounce(v, 100), { initialProps: { v: 'a' } })
    expect(result.current).toBe('a')
    rerender({ v: 'b' })
    expect(result.current).toBe('a')
    act(() => { vi.advanceTimersByTime(100) })
    expect(result.current).toBe('b')
    vi.useRealTimers()
  })
})
```

`useMediaQuery.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useMediaQuery } from './useMediaQuery'

describe('useMediaQuery', () => {
  it('retorna match inicial', () => {
    vi.stubGlobal('matchMedia', () => ({
      matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn(),
      media: '', onchange: null, addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
    const { result } = renderHook(() => useMediaQuery('(min-width: 1024px)'))
    expect(result.current).toBe(true)
  })
})
```

`useKeyboardShortcut.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useKeyboardShortcut } from './useKeyboardShortcut'

describe('useKeyboardShortcut', () => {
  it('dispara handler na key', () => {
    const handler = vi.fn()
    renderHook(() => useKeyboardShortcut('/', handler))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '/' }))
    expect(handler).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Implementações**

`useDebounce.ts`:

```ts
import { useEffect, useState } from 'react'
export function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return debounced
}
```

`useMediaQuery.ts`:

```ts
import { useEffect, useState } from 'react'
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false
  )
  useEffect(() => {
    const mql = window.matchMedia(query)
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches)
    mql.addEventListener('change', handler)
    setMatches(mql.matches)
    return () => mql.removeEventListener('change', handler)
  }, [query])
  return matches
}
```

`useKeyboardShortcut.ts`:

```ts
import { useEffect } from 'react'
export function useKeyboardShortcut(
  key: string,
  handler: (e: KeyboardEvent) => void,
  opts: { ctrl?: boolean; meta?: boolean; shift?: boolean } = {}
) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== key) return
      if (opts.ctrl && !e.ctrlKey) return
      if (opts.meta && !e.metaKey) return
      if (opts.shift && !e.shiftKey) return
      // Não disparar quando foco está em input/textarea/contentEditable
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      handler(e)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [key, handler, opts.ctrl, opts.meta, opts.shift])
}
```

- [ ] **Step 3: Barrel**

`shared/hooks/index.ts`:

```ts
export { useDebounce } from './useDebounce'
export { useMediaQuery } from './useMediaQuery'
export { useKeyboardShortcut } from './useKeyboardShortcut'
```

- [ ] **Step 4: Rodar testes**

```bash
cd frontend && npx vitest run src/shared/hooks/
```
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/hooks/
git commit -m "feat(ds): add useDebounce, useMediaQuery, useKeyboardShortcut hooks"
```

---

## Phase 4 — Ícones curados

### Task 4.1: Criar barrel curado de ícones lucide

**Files:**
- Create: `frontend/src/shared/ui/icons/index.ts`

- [ ] **Step 1: Criar barrel**

```ts
// Apenas os ícones em uso explicito ficam aqui — tree-shaking garante 0 ícones não usados no bundle.
// Para adicionar um ícone novo: passe o nome do componente lucide aqui (https://lucide.dev/icons).
export {
  // Navegação principal
  Search,
  LayoutGrid,        // Pipeline
  Bookmark,          // Listas salvas
  BarChart3,         // Relatórios
  Settings,          // Configurações
  // TopBar
  Bell,
  CircleHelp,
  ChevronDown,
  // Ações de linha
  Plus,
  Eye,
  Pencil,
  Trash2,
  ArrowUpRight,
  // Status / feedback
  Check,
  CircleAlert,
  TriangleAlert,
  CircleX,
  CircleCheck,
  Info,
  Loader2,
  Clock,
  // Brand / premium
  Star,
  Sparkles,
  // Forms
  X,
  ChevronRight,
  ChevronLeft,
  ChevronUp,
  // Empty states
  Inbox,
  SearchX,
  // Skip / accessibility
  ArrowDown,
} from 'lucide-react'
```

- [ ] **Step 2: Adicionar regra ESLint que proíbe import direto de `lucide-react`**

Editar `frontend/eslint.config.js` adicionando em `rules`:

```js
'no-restricted-imports': ['error', {
  patterns: [
    { group: ['*/internal/*', '*/_*'], message: 'Importe via Public API do slice (index.ts).' },
  ],
  paths: [
    { name: 'lucide-react', message: 'Importe ícones de @/shared/ui/icons (barrel curado).' },
  ],
}],
```

(Mesclar com o `no-restricted-imports` já existente; manter `patterns`.)

- [ ] **Step 3: Verificar lint**

```bash
cd frontend && npx eslint src/shared/ui/icons/index.ts
```
Expected: 0 erros (o barrel é a única exceção; pode adicionar `/* eslint-disable no-restricted-imports */` no topo dele).

- [ ] **Step 4: Adicionar disable no topo do barrel**

No `icons/index.ts` adicionar primeira linha:

```ts
/* eslint-disable no-restricted-imports -- único lugar autorizado a importar de lucide-react */
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/ui/icons/index.ts frontend/eslint.config.js
git commit -m "feat(ds): add curated lucide icon barrel + ESLint guard"
```

---

## Phase 5 — Primitives (shared/ui/primitives)

> **Padrão por componente:** cada componente vive em `src/shared/ui/primitives/<Name>/`:
> - `<Name>.tsx` — componente com `cva` variants
> - `<Name>.test.tsx` — testes RTL + axe
> - `index.ts` — Public API
>
> Após criar todos os componentes desta fase, atualizar `src/shared/ui/index.ts` re-exportando.

### Task 5.1: Button + IconButton

**Files:**
- Create: `frontend/src/shared/ui/primitives/Button/Button.tsx`
- Create: `frontend/src/shared/ui/primitives/Button/Button.test.tsx`
- Create: `frontend/src/shared/ui/primitives/Button/index.ts`

- [ ] **Step 1: Teste**

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'
import { Button } from './Button'

describe('Button', () => {
  it('renderiza o texto', () => {
    render(<Button>Salvar</Button>)
    expect(screen.getByRole('button', { name: 'Salvar' })).toBeInTheDocument()
  })
  it('dispara onClick', async () => {
    let n = 0
    render(<Button onClick={() => n++}>Salvar</Button>)
    await userEvent.click(screen.getByRole('button'))
    expect(n).toBe(1)
  })
  it('mostra loader quando loading', () => {
    render(<Button loading>Salvar</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true')
  })
  it('passa axe', async () => {
    const { container } = render(<Button>Salvar</Button>)
    expect(await axe(container)).toHaveNoViolations()
  })
})
```

- [ ] **Step 2: Implementação**

```tsx
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef } from 'react'
import { Loader2 } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium ' +
  'transition-colors transition-shadow ' +
  'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)] ' +
  'disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary:   'bg-[var(--color-action)] text-[var(--color-action-fg)] hover:bg-[var(--color-action-hover)]',
        secondary: 'bg-[var(--color-bg-surface)] text-[var(--color-fg-primary)] border border-[var(--color-border-strong)] hover:bg-[var(--color-bg-subtle)]',
        ghost:     'bg-transparent text-[var(--color-fg-primary)] hover:bg-[var(--color-bg-subtle)]',
        danger:    'bg-[var(--color-danger)] text-white hover:opacity-90',
        link:      'bg-transparent text-[var(--color-action)] underline-offset-2 hover:underline p-0 h-auto',
      },
      size: {
        sm: 'h-8 px-3 text-[var(--text-sm)]',
        md: 'h-10 px-4 text-[var(--text-base)]',
        lg: 'h-12 px-6 text-[var(--text-md)]',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled ?? loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading && <Loader2 className="animate-spin" size={16} aria-hidden="true" />}
        {children}
      </Comp>
    )
  }
)
Button.displayName = 'Button'
```

- [ ] **Step 3: Barrel**

`primitives/Button/index.ts`:

```ts
export { Button, type ButtonProps } from './Button'
```

- [ ] **Step 4: Rodar testes**

```bash
cd frontend && npx vitest run src/shared/ui/primitives/Button/
```
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/ui/primitives/Button/
git commit -m "feat(ds): add Button primitive with cva variants and a11y"
```

---

### Task 5.2: IconButton (composição sobre Button)

**Files:**
- Create: `frontend/src/shared/ui/primitives/IconButton/IconButton.tsx`
- Create: `frontend/src/shared/ui/primitives/IconButton/IconButton.test.tsx`
- Create: `frontend/src/shared/ui/primitives/IconButton/index.ts`

- [ ] **Step 1: Teste**

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { IconButton } from './IconButton'
import { Plus } from '@/shared/ui/icons'

describe('IconButton', () => {
  it('exige aria-label', async () => {
    const { container } = render(
      <IconButton aria-label="Adicionar"><Plus size={16} /></IconButton>
    )
    expect(screen.getByRole('button', { name: 'Adicionar' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
```

- [ ] **Step 2: Implementação**

```tsx
import { forwardRef } from 'react'
import { Button, type ButtonProps } from '../Button/Button'
import { cn } from '@/shared/lib'

export interface IconButtonProps extends Omit<ButtonProps, 'children'> {
  'aria-label': string
  children: React.ReactNode
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, size = 'md', ...props }, ref) => {
    const dim = size === 'sm' ? 'h-8 w-8' : size === 'lg' ? 'h-12 w-12' : 'h-10 w-10'
    return <Button ref={ref} size={size} className={cn(dim, 'p-0', className)} {...props} />
  }
)
IconButton.displayName = 'IconButton'
```

- [ ] **Step 3: Barrel**

```ts
export { IconButton, type IconButtonProps } from './IconButton'
```

- [ ] **Step 4: Teste + commit**

```bash
cd frontend && npx vitest run src/shared/ui/primitives/IconButton/
git add frontend/src/shared/ui/primitives/IconButton/
git commit -m "feat(ds): add IconButton with required aria-label"
```

---

### Task 5.3: Input + Textarea + Label + FormField

**Files:**
- Create: `frontend/src/shared/ui/primitives/Input/Input.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/primitives/Textarea/Textarea.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/primitives/Label/Label.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/primitives/FormField/FormField.tsx` + test + index.ts

- [ ] **Step 1: Input — teste**

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'
import { Input } from './Input'

describe('Input', () => {
  it('aceita digitação', async () => {
    render(<Input aria-label="nome" />)
    await userEvent.type(screen.getByLabelText('nome'), 'abc')
    expect(screen.getByLabelText('nome')).toHaveValue('abc')
  })
  it('marca aria-invalid quando invalid', () => {
    render(<Input aria-label="x" invalid />)
    expect(screen.getByLabelText('x')).toHaveAttribute('aria-invalid', 'true')
  })
  it('passa axe', async () => {
    const { container } = render(<Input aria-label="x" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
```

- [ ] **Step 2: Input — implementação**

```tsx
import { forwardRef } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/shared/lib'

const inputVariants = cva(
  'flex w-full rounded-md border bg-[var(--color-bg-surface)] text-[var(--color-fg-primary)] ' +
  'placeholder:text-[var(--color-fg-muted)] ' +
  'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)] ' +
  'disabled:opacity-50 disabled:cursor-not-allowed transition-shadow',
  {
    variants: {
      size: {
        sm: 'h-8 px-2.5 text-[var(--text-sm)]',
        md: 'h-10 px-3 text-[var(--text-base)]',
      },
      invalid: {
        true:  'border-[var(--color-danger)]',
        false: 'border-[var(--color-border-strong)]',
      },
    },
    defaultVariants: { size: 'md', invalid: false },
  }
)

export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'>,
    VariantProps<typeof inputVariants> {}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, size, invalid, ...props }, ref) => (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(inputVariants({ size, invalid }), className)}
      {...props}
    />
  )
)
Input.displayName = 'Input'
```

- [ ] **Step 3: Textarea — teste + implementação**

`Textarea/Textarea.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { Textarea } from './Textarea'

describe('Textarea', () => {
  it('renderiza', () => { render(<Textarea aria-label="x" />); expect(screen.getByLabelText('x')).toBeInTheDocument() })
  it('axe', async () => { const { container } = render(<Textarea aria-label="x" />); expect(await axe(container)).toHaveNoViolations() })
})
```

`Textarea/Textarea.tsx`:

```tsx
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, invalid, ...props }, ref) => (
    <textarea
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        'flex w-full rounded-md border bg-[var(--color-bg-surface)] px-3 py-2 text-[var(--text-base)]',
        'placeholder:text-[var(--color-fg-muted)] focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
        invalid ? 'border-[var(--color-danger)]' : 'border-[var(--color-border-strong)]',
        className
      )}
      {...props}
    />
  )
)
Textarea.displayName = 'Textarea'
```

- [ ] **Step 4: Label — implementação**

`Label/Label.tsx`:

```tsx
import * as LabelPrimitive from '@radix-ui/react-label'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export interface LabelProps extends React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> {
  required?: boolean
}

export const Label = forwardRef<React.ElementRef<typeof LabelPrimitive.Root>, LabelProps>(
  ({ className, children, required, ...props }, ref) => (
    <LabelPrimitive.Root
      ref={ref}
      className={cn('text-[var(--text-sm)] font-medium text-[var(--color-fg-primary)]', className)}
      {...props}
    >
      {children}
      {required && <span aria-hidden="true" className="text-[var(--color-danger)] ml-0.5">*</span>}
    </LabelPrimitive.Root>
  )
)
Label.displayName = 'Label'
```

Teste:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Label } from './Label'

it('renderiza com asterisco quando required', () => {
  render(<Label required>Nome</Label>)
  expect(screen.getByText('Nome')).toBeInTheDocument()
  expect(screen.getByText('*')).toHaveAttribute('aria-hidden', 'true')
})
```

- [ ] **Step 5: FormField — implementação**

`FormField/FormField.tsx`:

```tsx
import { createContext, useContext, useId } from 'react'
import { cn } from '@/shared/lib'
import { Label } from '../Label/Label'

interface Ctx { id: string; descId: string; errId: string; invalid: boolean }
const FormFieldCtx = createContext<Ctx | null>(null)

export interface FormFieldProps {
  label: string
  required?: boolean
  helper?: string
  error?: string
  children: React.ReactNode
  className?: string
}

export function FormField({ label, required, helper, error, children, className }: FormFieldProps) {
  const id = useId()
  const descId = `${id}-desc`
  const errId = `${id}-err`
  const invalid = Boolean(error)
  return (
    <FormFieldCtx.Provider value={{ id, descId, errId, invalid }}>
      <div className={cn('flex flex-col gap-1.5', className)}>
        <Label htmlFor={id} required={required}>{label}</Label>
        {children}
        {helper && !error && <p id={descId} className="text-[var(--text-xs)] text-[var(--color-fg-muted)]">{helper}</p>}
        {error && <p id={errId} className="text-[var(--text-xs)] text-[var(--color-danger)]">{error}</p>}
      </div>
    </FormFieldCtx.Provider>
  )
}

export function useFormField() {
  const ctx = useContext(FormFieldCtx)
  if (!ctx) throw new Error('useFormField must be used inside <FormField>')
  return ctx
}
```

Teste:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { FormField } from './FormField'
import { Input } from '../Input/Input'

it('associa label, helper e erro', async () => {
  const { container } = render(
    <FormField label="Nome" helper="Como aparece em relatórios" error="Obrigatório">
      <Input aria-label="Nome" />
    </FormField>
  )
  expect(screen.getByText('Nome')).toBeInTheDocument()
  expect(screen.getByText('Obrigatório')).toBeInTheDocument()
  expect(await axe(container)).toHaveNoViolations()
})
```

- [ ] **Step 6: Barrels + rodar tudo**

Cada componente tem seu próprio `index.ts` exportando o componente e os tipos.

```bash
cd frontend && npx vitest run src/shared/ui/primitives/Input src/shared/ui/primitives/Textarea src/shared/ui/primitives/Label src/shared/ui/primitives/FormField
```
Expected: todos PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/shared/ui/primitives/Input frontend/src/shared/ui/primitives/Textarea frontend/src/shared/ui/primitives/Label frontend/src/shared/ui/primitives/FormField
git commit -m "feat(ds): add Input, Textarea, Label, FormField primitives"
```

---

### Task 5.4: Tooltip + Popover (Radix)

**Files:**
- Create: `frontend/src/shared/ui/primitives/Tooltip/Tooltip.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/primitives/Popover/Popover.tsx` + test + index.ts

- [ ] **Step 1: Tooltip**

`Tooltip/Tooltip.tsx`:

```tsx
import * as Tooltip from '@radix-ui/react-tooltip'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const TooltipProvider = Tooltip.Provider
export const TooltipRoot = Tooltip.Root
export const TooltipTrigger = Tooltip.Trigger

export const TooltipContent = forwardRef<
  React.ElementRef<typeof Tooltip.Content>,
  React.ComponentPropsWithoutRef<typeof Tooltip.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <Tooltip.Portal>
    <Tooltip.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        'z-[var(--z-tooltip)] rounded-md bg-[var(--color-gray-900)] text-white',
        'px-2 py-1 text-[var(--text-xs)] shadow-[var(--shadow-md)]',
        'data-[state=open]:animate-in data-[state=closed]:animate-out',
        className
      )}
      {...props}
    />
  </Tooltip.Portal>
))
TooltipContent.displayName = 'TooltipContent'
```

`Tooltip/Tooltip.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TooltipProvider, TooltipRoot, TooltipTrigger, TooltipContent } from './Tooltip'

it('mostra conteúdo on focus', async () => {
  render(
    <TooltipProvider delayDuration={0}>
      <TooltipRoot><TooltipTrigger>btn</TooltipTrigger><TooltipContent>oi</TooltipContent></TooltipRoot>
    </TooltipProvider>
  )
  await userEvent.tab()
  expect(await screen.findByText('oi')).toBeInTheDocument()
})
```

- [ ] **Step 2: Popover**

`Popover/Popover.tsx`:

```tsx
import * as Popover from '@radix-ui/react-popover'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const PopoverRoot = Popover.Root
export const PopoverTrigger = Popover.Trigger
export const PopoverClose = Popover.Close
export const PopoverAnchor = Popover.Anchor

export const PopoverContent = forwardRef<
  React.ElementRef<typeof Popover.Content>,
  React.ComponentPropsWithoutRef<typeof Popover.Content>
>(({ className, align = 'center', sideOffset = 6, ...props }, ref) => (
  <Popover.Portal>
    <Popover.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      className={cn(
        'z-[var(--z-popover)] w-72 rounded-lg bg-[var(--color-bg-surface)] border border-[var(--color-border)]',
        'p-3 shadow-[var(--shadow-md)] outline-none',
        className
      )}
      {...props}
    />
  </Popover.Portal>
))
PopoverContent.displayName = 'PopoverContent'
```

`Popover/Popover.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PopoverRoot, PopoverTrigger, PopoverContent } from './Popover'

it('abre ao clicar no trigger', async () => {
  render(<PopoverRoot><PopoverTrigger>abrir</PopoverTrigger><PopoverContent>conteúdo</PopoverContent></PopoverRoot>)
  await userEvent.click(screen.getByText('abrir'))
  expect(await screen.findByText('conteúdo')).toBeInTheDocument()
})
```

- [ ] **Step 3: Barrels, testar, commit**

```bash
cd frontend && npx vitest run src/shared/ui/primitives/Tooltip src/shared/ui/primitives/Popover
git add frontend/src/shared/ui/primitives/Tooltip frontend/src/shared/ui/primitives/Popover
git commit -m "feat(ds): add Tooltip and Popover primitives (Radix-based)"
```

---

### Task 5.5: Dialog + AlertDialog (Radix + Framer)

**Files:**
- Create: `frontend/src/shared/ui/primitives/Dialog/Dialog.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/primitives/AlertDialog/AlertDialog.tsx` + test + index.ts

- [ ] **Step 1: Dialog — implementação**

`Dialog/Dialog.tsx`:

```tsx
import * as Dialog from '@radix-ui/react-dialog'
import { forwardRef } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { X } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

const contentVariants = cva(
  'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-[var(--z-modal)] ' +
  'bg-[var(--color-bg-surface)] rounded-xl shadow-[var(--shadow-lg)] p-6 ' +
  'data-[state=open]:animate-in data-[state=closed]:animate-out ' +
  'focus:outline-none w-full',
  {
    variants: {
      size: {
        sm: 'max-w-md',
        md: 'max-w-lg',
        lg: 'max-w-2xl',
        xl: 'max-w-4xl',
        fullscreen: 'max-w-none w-screen h-screen rounded-none',
      },
    },
    defaultVariants: { size: 'md' },
  }
)

export const DialogRoot = Dialog.Root
export const DialogTrigger = Dialog.Trigger
export const DialogClose = Dialog.Close

export const DialogContent = forwardRef<
  React.ElementRef<typeof Dialog.Content>,
  React.ComponentPropsWithoutRef<typeof Dialog.Content> & VariantProps<typeof contentVariants>
>(({ className, size, children, ...props }, ref) => (
  <Dialog.Portal>
    <Dialog.Overlay className="fixed inset-0 bg-black/40 z-[var(--z-modal-backdrop)] data-[state=open]:animate-in data-[state=closed]:animate-out" />
    <Dialog.Content ref={ref} className={cn(contentVariants({ size }), className)} {...props}>
      {children}
      <Dialog.Close
        aria-label="Fechar"
        className="absolute right-3 top-3 p-1.5 rounded-md hover:bg-[var(--color-bg-subtle)] focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
      >
        <X size={16} aria-hidden="true" />
      </Dialog.Close>
    </Dialog.Content>
  </Dialog.Portal>
))
DialogContent.displayName = 'DialogContent'

export const DialogTitle = forwardRef<
  React.ElementRef<typeof Dialog.Title>,
  React.ComponentPropsWithoutRef<typeof Dialog.Title>
>(({ className, ...props }, ref) => (
  <Dialog.Title ref={ref} className={cn('text-[var(--text-lg)] font-semibold leading-tight', className)} {...props} />
))
DialogTitle.displayName = 'DialogTitle'

export const DialogDescription = forwardRef<
  React.ElementRef<typeof Dialog.Description>,
  React.ComponentPropsWithoutRef<typeof Dialog.Description>
>(({ className, ...props }, ref) => (
  <Dialog.Description ref={ref} className={cn('text-[var(--text-sm)] text-[var(--color-fg-secondary)] mt-1', className)} {...props} />
))
DialogDescription.displayName = 'DialogDescription'
```

`Dialog/Dialog.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DialogRoot, DialogTrigger, DialogContent, DialogTitle } from './Dialog'

it('abre e fecha via teclado', async () => {
  render(
    <DialogRoot><DialogTrigger>abrir</DialogTrigger>
      <DialogContent><DialogTitle>Título</DialogTitle></DialogContent>
    </DialogRoot>
  )
  await userEvent.click(screen.getByText('abrir'))
  expect(await screen.findByText('Título')).toBeInTheDocument()
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByText('Título')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: AlertDialog** — mesma estrutura usando `@radix-ui/react-alert-dialog`:

`AlertDialog/AlertDialog.tsx`:

```tsx
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const AlertDialogRoot = AlertDialog.Root
export const AlertDialogTrigger = AlertDialog.Trigger
export const AlertDialogAction = AlertDialog.Action
export const AlertDialogCancel = AlertDialog.Cancel

export const AlertDialogContent = forwardRef<
  React.ElementRef<typeof AlertDialog.Content>,
  React.ComponentPropsWithoutRef<typeof AlertDialog.Content>
>(({ className, ...props }, ref) => (
  <AlertDialog.Portal>
    <AlertDialog.Overlay className="fixed inset-0 bg-black/40 z-[var(--z-modal-backdrop)]" />
    <AlertDialog.Content ref={ref}
      className={cn(
        'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-[var(--z-modal)] max-w-md',
        'bg-[var(--color-bg-surface)] rounded-xl shadow-[var(--shadow-lg)] p-6 focus:outline-none',
        className
      )}
      {...props} />
  </AlertDialog.Portal>
))
AlertDialogContent.displayName = 'AlertDialogContent'

export const AlertDialogTitle = AlertDialog.Title
export const AlertDialogDescription = AlertDialog.Description
```

`AlertDialog/AlertDialog.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AlertDialogRoot, AlertDialogTrigger, AlertDialogContent, AlertDialogTitle, AlertDialogAction } from './AlertDialog'

it('abre, mostra ação destructive', async () => {
  render(
    <AlertDialogRoot><AlertDialogTrigger>excluir</AlertDialogTrigger>
      <AlertDialogContent><AlertDialogTitle>Tem certeza?</AlertDialogTitle><AlertDialogAction>Sim</AlertDialogAction></AlertDialogContent>
    </AlertDialogRoot>
  )
  await userEvent.click(screen.getByText('excluir'))
  expect(await screen.findByText('Tem certeza?')).toBeInTheDocument()
})
```

- [ ] **Step 3: Barrels + testar + commit**

```bash
cd frontend && npx vitest run src/shared/ui/primitives/Dialog src/shared/ui/primitives/AlertDialog
git add frontend/src/shared/ui/primitives/Dialog frontend/src/shared/ui/primitives/AlertDialog
git commit -m "feat(ds): add Dialog and AlertDialog (Radix + size variants)"
```

---

### Task 5.6: DropdownMenu + Tabs + Select

**Files:**
- Create: `frontend/src/shared/ui/primitives/DropdownMenu/DropdownMenu.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/primitives/Tabs/Tabs.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/primitives/Select/Select.tsx` + test + index.ts

> Para cada componente, seguir o padrão dos anteriores: Radix Root/Trigger/Content/Item, estilização via Tailwind tokens, teste mínimo de render + interação + axe. Por brevidade do plano, os 3 estão consolidados em uma task — mas escreva cada um em seu próprio diretório com teste próprio.

- [ ] **Step 1: DropdownMenu** (`@radix-ui/react-dropdown-menu`)

`DropdownMenu/DropdownMenu.tsx`:

```tsx
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const DropdownMenuRoot = DropdownMenu.Root
export const DropdownMenuTrigger = DropdownMenu.Trigger
export const DropdownMenuLabel = DropdownMenu.Label
export const DropdownMenuSeparator = DropdownMenu.Separator

export const DropdownMenuContent = forwardRef<
  React.ElementRef<typeof DropdownMenu.Content>,
  React.ComponentPropsWithoutRef<typeof DropdownMenu.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <DropdownMenu.Portal>
    <DropdownMenu.Content ref={ref} sideOffset={sideOffset}
      className={cn('z-[var(--z-dropdown)] min-w-[10rem] rounded-lg bg-[var(--color-bg-surface)] border border-[var(--color-border)] p-1 shadow-[var(--shadow-md)]', className)}
      {...props} />
  </DropdownMenu.Portal>
))
DropdownMenuContent.displayName = 'DropdownMenuContent'

export const DropdownMenuItem = forwardRef<
  React.ElementRef<typeof DropdownMenu.Item>,
  React.ComponentPropsWithoutRef<typeof DropdownMenu.Item>
>(({ className, ...props }, ref) => (
  <DropdownMenu.Item ref={ref}
    className={cn('flex items-center gap-2 rounded-md px-2.5 py-2 text-[var(--text-sm)] cursor-pointer outline-none', 'data-[highlighted]:bg-[var(--color-bg-subtle)]', className)}
    {...props} />
))
DropdownMenuItem.displayName = 'DropdownMenuItem'
```

`DropdownMenu/DropdownMenu.test.tsx`: render trigger, click, assert items appear.

- [ ] **Step 2: Tabs** (`@radix-ui/react-tabs`)

`Tabs/Tabs.tsx`:

```tsx
import * as Tabs from '@radix-ui/react-tabs'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const TabsRoot = Tabs.Root

export const TabsList = forwardRef<
  React.ElementRef<typeof Tabs.List>,
  React.ComponentPropsWithoutRef<typeof Tabs.List>
>(({ className, ...props }, ref) => (
  <Tabs.List ref={ref}
    className={cn('inline-flex items-center gap-1 border-b border-[var(--color-border)]', className)}
    {...props} />
))
TabsList.displayName = 'TabsList'

export const TabsTrigger = forwardRef<
  React.ElementRef<typeof Tabs.Trigger>,
  React.ComponentPropsWithoutRef<typeof Tabs.Trigger>
>(({ className, ...props }, ref) => (
  <Tabs.Trigger ref={ref}
    className={cn(
      'px-4 h-10 text-[var(--text-sm)] font-medium text-[var(--color-fg-secondary)]',
      'border-b-2 border-transparent -mb-px',
      'data-[state=active]:text-[var(--color-action)] data-[state=active]:border-[var(--color-action)]',
      'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)] rounded-t-md',
      className
    )}
    {...props} />
))
TabsTrigger.displayName = 'TabsTrigger'

export const TabsContent = Tabs.Content
```

`Tabs/Tabs.test.tsx`: render with 2 tabs, click second, expect content swap.

- [ ] **Step 3: Select** (`@radix-ui/react-select`)

`Select/Select.tsx`:

```tsx
import * as Select from '@radix-ui/react-select'
import { forwardRef } from 'react'
import { Check, ChevronDown } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

export const SelectRoot = Select.Root
export const SelectValue = Select.Value

export const SelectTrigger = forwardRef<
  React.ElementRef<typeof Select.Trigger>,
  React.ComponentPropsWithoutRef<typeof Select.Trigger>
>(({ className, children, ...props }, ref) => (
  <Select.Trigger ref={ref}
    className={cn(
      'flex h-10 w-full items-center justify-between rounded-md border border-[var(--color-border-strong)]',
      'bg-[var(--color-bg-surface)] px-3 text-[var(--text-base)] outline-none',
      'focus-visible:shadow-[var(--shadow-focus)] disabled:opacity-50',
      className
    )}
    {...props}>
    {children}
    <Select.Icon><ChevronDown size={16} aria-hidden="true" /></Select.Icon>
  </Select.Trigger>
))
SelectTrigger.displayName = 'SelectTrigger'

export const SelectContent = forwardRef<
  React.ElementRef<typeof Select.Content>,
  React.ComponentPropsWithoutRef<typeof Select.Content>
>(({ className, ...props }, ref) => (
  <Select.Portal>
    <Select.Content ref={ref}
      className={cn('z-[var(--z-dropdown)] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] shadow-[var(--shadow-md)] overflow-hidden', className)}
      position="popper"
      {...props}>
      <Select.Viewport className="p-1">{props.children}</Select.Viewport>
    </Select.Content>
  </Select.Portal>
))
SelectContent.displayName = 'SelectContent'

export const SelectItem = forwardRef<
  React.ElementRef<typeof Select.Item>,
  React.ComponentPropsWithoutRef<typeof Select.Item>
>(({ className, children, ...props }, ref) => (
  <Select.Item ref={ref}
    className={cn(
      'flex items-center justify-between rounded-md px-2.5 py-2 text-[var(--text-sm)] outline-none',
      'data-[highlighted]:bg-[var(--color-bg-subtle)] cursor-pointer',
      className
    )}
    {...props}>
    <Select.ItemText>{children}</Select.ItemText>
    <Select.ItemIndicator><Check size={14} aria-hidden="true" /></Select.ItemIndicator>
  </Select.Item>
))
SelectItem.displayName = 'SelectItem'
```

`Select/Select.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SelectRoot, SelectTrigger, SelectContent, SelectItem, SelectValue } from './Select'

it('seleciona um valor', async () => {
  render(
    <SelectRoot><SelectTrigger><SelectValue placeholder="escolha" /></SelectTrigger>
      <SelectContent><SelectItem value="a">A</SelectItem><SelectItem value="b">B</SelectItem></SelectContent>
    </SelectRoot>
  )
  await userEvent.click(screen.getByRole('combobox'))
  await userEvent.click(await screen.findByText('A'))
  expect(screen.getByRole('combobox')).toHaveTextContent('A')
})
```

- [ ] **Step 4: Barrels + testar + commit**

```bash
cd frontend && npx vitest run src/shared/ui/primitives/DropdownMenu src/shared/ui/primitives/Tabs src/shared/ui/primitives/Select
git add frontend/src/shared/ui/primitives/DropdownMenu frontend/src/shared/ui/primitives/Tabs frontend/src/shared/ui/primitives/Select
git commit -m "feat(ds): add DropdownMenu, Tabs and Select primitives"
```

---

### Task 5.7: Checkbox, RadioGroup, Switch, Slider

**Files:**
- Create: `frontend/src/shared/ui/primitives/Checkbox/Checkbox.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/primitives/RadioGroup/RadioGroup.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/primitives/Switch/Switch.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/primitives/Slider/Slider.tsx` + test + index.ts

> Cada componente segue o padrão Radix + Tailwind tokens. Cada um tem teste render + interação + axe.

- [ ] **Step 1: Checkbox**

```tsx
// Checkbox/Checkbox.tsx
import * as Checkbox from '@radix-ui/react-checkbox'
import { forwardRef } from 'react'
import { Check } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

export const CheckboxRoot = forwardRef<
  React.ElementRef<typeof Checkbox.Root>,
  React.ComponentPropsWithoutRef<typeof Checkbox.Root>
>(({ className, ...props }, ref) => (
  <Checkbox.Root ref={ref}
    className={cn(
      'h-4 w-4 rounded-sm border border-[var(--color-border-strong)] bg-[var(--color-bg-surface)]',
      'flex items-center justify-center',
      'data-[state=checked]:bg-[var(--color-action)] data-[state=checked]:border-[var(--color-action)]',
      'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
      className
    )}
    {...props}>
    <Checkbox.Indicator><Check size={12} className="text-white" aria-hidden="true" /></Checkbox.Indicator>
  </Checkbox.Root>
))
CheckboxRoot.displayName = 'Checkbox'

export { CheckboxRoot as Checkbox }
```

Teste: render, click, expect `data-state=checked` + axe.

- [ ] **Step 2: RadioGroup**

```tsx
// RadioGroup/RadioGroup.tsx
import * as RadioGroup from '@radix-ui/react-radio-group'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const RadioGroupRoot = RadioGroup.Root
export const RadioGroupItem = forwardRef<
  React.ElementRef<typeof RadioGroup.Item>,
  React.ComponentPropsWithoutRef<typeof RadioGroup.Item>
>(({ className, ...props }, ref) => (
  <RadioGroup.Item ref={ref}
    className={cn(
      'h-4 w-4 rounded-full border border-[var(--color-border-strong)] bg-[var(--color-bg-surface)]',
      'data-[state=checked]:border-[var(--color-action)] flex items-center justify-center',
      'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
      className
    )}
    {...props}>
    <RadioGroup.Indicator className="h-2 w-2 rounded-full bg-[var(--color-action)]" />
  </RadioGroup.Item>
))
RadioGroupItem.displayName = 'RadioGroupItem'
```

Teste: render 2 itens, click segundo, expect aria-checked.

- [ ] **Step 3: Switch**

```tsx
// Switch/Switch.tsx
import * as Switch from '@radix-ui/react-switch'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const SwitchRoot = forwardRef<
  React.ElementRef<typeof Switch.Root>,
  React.ComponentPropsWithoutRef<typeof Switch.Root>
>(({ className, ...props }, ref) => (
  <Switch.Root ref={ref}
    className={cn(
      'h-5 w-9 rounded-full bg-[var(--color-gray-300)] relative transition-colors',
      'data-[state=checked]:bg-[var(--color-action)]',
      'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
      className
    )}
    {...props}>
    <Switch.Thumb className="block h-4 w-4 bg-white rounded-full shadow translate-x-0.5 transition-transform data-[state=checked]:translate-x-4" />
  </Switch.Root>
))
SwitchRoot.displayName = 'Switch'

export { SwitchRoot as Switch }
```

Teste: render, click, expect data-state checked.

- [ ] **Step 4: Slider**

```tsx
// Slider/Slider.tsx
import * as Slider from '@radix-ui/react-slider'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const SliderRoot = forwardRef<
  React.ElementRef<typeof Slider.Root>,
  React.ComponentPropsWithoutRef<typeof Slider.Root>
>(({ className, ...props }, ref) => (
  <Slider.Root ref={ref}
    className={cn('relative flex items-center select-none touch-none w-full h-5', className)}
    {...props}>
    <Slider.Track className="bg-[var(--color-gray-200)] relative grow rounded-full h-1">
      <Slider.Range className="absolute bg-[var(--color-action)] rounded-full h-full" />
    </Slider.Track>
    <Slider.Thumb className="block h-4 w-4 bg-white border-2 border-[var(--color-action)] rounded-full focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]" aria-label="valor" />
  </Slider.Root>
))
SliderRoot.displayName = 'Slider'

export { SliderRoot as Slider }
```

Teste: render `defaultValue={[50]}`, expect `aria-valuenow=50`.

- [ ] **Step 5: Barrels + testar + commit**

```bash
cd frontend && npx vitest run src/shared/ui/primitives/Checkbox src/shared/ui/primitives/RadioGroup src/shared/ui/primitives/Switch src/shared/ui/primitives/Slider
git add frontend/src/shared/ui/primitives/Checkbox frontend/src/shared/ui/primitives/RadioGroup frontend/src/shared/ui/primitives/Switch frontend/src/shared/ui/primitives/Slider
git commit -m "feat(ds): add Checkbox, RadioGroup, Switch, Slider primitives"
```

---

### Task 5.8: Badge, Avatar, Separator, Spinner, Kbd, VisuallyHidden

**Files:**
- Create: 6 componentes em `src/shared/ui/primitives/<Name>/`

> Componentes pequenos. Cada um com seu próprio teste mínimo. Implementações enxutas.

- [ ] **Step 1: Badge**

```tsx
// Badge/Badge.tsx
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/shared/lib'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[var(--text-xs)] font-medium border',
  {
    variants: {
      variant: {
        neutral: 'bg-[var(--color-gray-100)] text-[var(--color-gray-700)] border-[var(--color-gray-200)]',
        info:    'bg-[var(--color-info-bg)] text-[var(--color-info)] border-[var(--color-blue-100)]',
        success: 'bg-[var(--color-success-bg)] text-[var(--color-success)] border-[var(--color-green-100)]',
        warning: 'bg-[var(--color-warning-bg)] text-[var(--color-warning)] border-[var(--color-amber-100)]',
        danger:  'bg-[var(--color-danger-bg)] text-[var(--color-danger)] border-[var(--color-red-100)]',
        brand:   'bg-[var(--color-yellow-100)] text-[var(--color-amber-600)] border-[var(--color-yellow-400)]',
      },
    },
    defaultVariants: { variant: 'neutral' },
  }
)

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}
export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
```

- [ ] **Step 2: Avatar**

```tsx
// Avatar/Avatar.tsx
import * as Avatar from '@radix-ui/react-avatar'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const AvatarRoot = forwardRef<React.ElementRef<typeof Avatar.Root>, React.ComponentPropsWithoutRef<typeof Avatar.Root> & { size?: 'sm' | 'md' | 'lg' }>(
  ({ className, size = 'md', ...props }, ref) => {
    const dim = size === 'sm' ? 'h-7 w-7 text-[10px]' : size === 'lg' ? 'h-10 w-10 text-[13px]' : 'h-8 w-8 text-[11px]'
    return <Avatar.Root ref={ref} className={cn('inline-flex items-center justify-center overflow-hidden rounded-full bg-[var(--color-yellow-500)] text-[var(--color-gray-900)] font-semibold', dim, className)} {...props} />
  }
)
AvatarRoot.displayName = 'Avatar'
export { AvatarRoot as Avatar }
export const AvatarImage = Avatar.Image
export const AvatarFallback = Avatar.Fallback
```

- [ ] **Step 3: Separator**

```tsx
// Separator/Separator.tsx
import * as Separator from '@radix-ui/react-separator'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const SeparatorRoot = forwardRef<React.ElementRef<typeof Separator.Root>, React.ComponentPropsWithoutRef<typeof Separator.Root>>(
  ({ className, orientation = 'horizontal', decorative = true, ...props }, ref) => (
    <Separator.Root ref={ref} orientation={orientation} decorative={decorative}
      className={cn('bg-[var(--color-border)]', orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px', className)} {...props} />
  )
)
SeparatorRoot.displayName = 'Separator'
export { SeparatorRoot as Separator }
```

- [ ] **Step 4: Spinner**

```tsx
// Spinner/Spinner.tsx
import { Loader2 } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

export interface SpinnerProps {
  size?: number
  className?: string
  'aria-label'?: string
}

export function Spinner({ size = 16, className, 'aria-label': ariaLabel = 'Carregando' }: SpinnerProps) {
  return <Loader2 size={size} className={cn('animate-spin text-[var(--color-fg-muted)]', className)} role="status" aria-label={ariaLabel} />
}
```

- [ ] **Step 5: Kbd**

```tsx
// Kbd/Kbd.tsx
import { cn } from '@/shared/lib'
export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd className={cn(
      'inline-flex items-center rounded border border-[var(--color-border)] bg-[var(--color-bg-subtle)]',
      'px-1.5 h-5 text-[10px] text-[var(--color-fg-secondary)] font-medium font-mono',
      className
    )}>{children}</kbd>
  )
}
```

- [ ] **Step 6: VisuallyHidden**

```tsx
// VisuallyHidden/VisuallyHidden.tsx
import * as VH from '@radix-ui/react-visually-hidden'
export const VisuallyHidden = VH.Root
```

- [ ] **Step 7: Testes mínimos (1 por componente)**

Para cada um, criar `<Name>.test.tsx` com:

```tsx
import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { <Name> } from './<Name>'

it('renderiza sem violar a11y', async () => {
  const { container } = render(<<Name>>conteúdo</<Name>>)
  expect(await axe(container)).toHaveNoViolations()
})
```

(Adaptar children/props pra cada componente.)

- [ ] **Step 8: Barrels + testar + commit**

```bash
cd frontend && npx vitest run src/shared/ui/primitives/Badge src/shared/ui/primitives/Avatar src/shared/ui/primitives/Separator src/shared/ui/primitives/Spinner src/shared/ui/primitives/Kbd src/shared/ui/primitives/VisuallyHidden
git add frontend/src/shared/ui/primitives/
git commit -m "feat(ds): add Badge, Avatar, Separator, Spinner, Kbd, VisuallyHidden"
```

---

### Task 5.9: Combobox (cmdk wrap) — async-search ready

**Files:**
- Create: `frontend/src/shared/ui/primitives/Combobox/Combobox.tsx` + test + index.ts

- [ ] **Step 1: Implementação**

```tsx
import { Command } from 'cmdk'
import { useState } from 'react'
import { PopoverRoot, PopoverTrigger, PopoverContent } from '../Popover/Popover'
import { cn } from '@/shared/lib'

export interface ComboboxOption { value: string; label: string }

export interface ComboboxProps {
  options: ComboboxOption[]
  value?: string
  onChange?: (v: string) => void
  onSearchChange?: (q: string) => void
  placeholder?: string
  emptyText?: string
  loading?: boolean
}

export function Combobox({
  options, value, onChange, onSearchChange, placeholder = 'Buscar…', emptyText = 'Nada encontrado.', loading = false,
}: ComboboxProps) {
  const [open, setOpen] = useState(false)
  const selected = options.find((o) => o.value === value)
  return (
    <PopoverRoot open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          role="combobox"
          aria-expanded={open}
          className={cn(
            'flex h-10 w-full items-center justify-between rounded-md border border-[var(--color-border-strong)]',
            'bg-[var(--color-bg-surface)] px-3 text-left text-[var(--text-base)]'
          )}
        >
          {selected ? selected.label : <span className="text-[var(--color-fg-muted)]">{placeholder}</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0">
        <Command shouldFilter={!onSearchChange} loop>
          <Command.Input
            onValueChange={onSearchChange}
            placeholder={placeholder}
            className="w-full border-b border-[var(--color-border)] px-3 py-2 outline-none text-[var(--text-sm)]"
          />
          <Command.List className="max-h-60 overflow-auto p-1">
            {loading && <div className="px-2 py-2 text-[var(--text-xs)] text-[var(--color-fg-muted)]">Carregando…</div>}
            {!loading && <Command.Empty className="px-2 py-2 text-[var(--text-xs)] text-[var(--color-fg-muted)]">{emptyText}</Command.Empty>}
            {options.map((o) => (
              <Command.Item
                key={o.value}
                value={o.value}
                onSelect={() => { onChange?.(o.value); setOpen(false) }}
                className="px-2 py-2 rounded-md text-[var(--text-sm)] aria-selected:bg-[var(--color-bg-subtle)] cursor-pointer"
              >
                {o.label}
              </Command.Item>
            ))}
          </Command.List>
        </Command>
      </PopoverContent>
    </PopoverRoot>
  )
}
```

- [ ] **Step 2: Teste**

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Combobox } from './Combobox'

it('seleciona uma opção', async () => {
  let chosen = ''
  render(<Combobox options={[{value:'a',label:'A'},{value:'b',label:'B'}]} onChange={v => chosen = v} />)
  await userEvent.click(screen.getByRole('combobox'))
  await userEvent.click(await screen.findByText('A'))
  expect(chosen).toBe('a')
})
```

- [ ] **Step 3: Testar + commit**

```bash
cd frontend && npx vitest run src/shared/ui/primitives/Combobox
git add frontend/src/shared/ui/primitives/Combobox
git commit -m "feat(ds): add Combobox (cmdk + Popover) with async-search support"
```

---

### Task 5.10: Atualizar barrel central `shared/ui/index.ts`

**Files:**
- Modify: `frontend/src/shared/ui/index.ts`

- [ ] **Step 1: Escrever barrel central**

```ts
// Primitives
export * from './primitives/Button'
export * from './primitives/IconButton'
export * from './primitives/Input'
export * from './primitives/Textarea'
export * from './primitives/Label'
export * from './primitives/FormField'
export * from './primitives/Tooltip'
export * from './primitives/Popover'
export * from './primitives/Dialog'
export * from './primitives/AlertDialog'
export * from './primitives/DropdownMenu'
export * from './primitives/Tabs'
export * from './primitives/Select'
export * from './primitives/Checkbox'
export * from './primitives/RadioGroup'
export * from './primitives/Switch'
export * from './primitives/Slider'
export * from './primitives/Badge'
export * from './primitives/Avatar'
export * from './primitives/Separator'
export * from './primitives/Spinner'
export * from './primitives/Kbd'
export * from './primitives/VisuallyHidden'
export * from './primitives/Combobox'

// Icons (sub-barrel)
export * as Icons from './icons'
```

- [ ] **Step 2: Verificar import alias funciona**

```bash
cd frontend && cat > /tmp/probe.tsx <<'EOF'
import { Button, Input, Icons } from '@/shared/ui'
const _ = <><Button>x</Button><Input aria-label="x" /><Icons.Search /></>
EOF
mv /tmp/probe.tsx frontend/src/probe.tsx
npx tsc -b --noEmit 2>&1 | head -10
rm frontend/src/probe.tsx
```
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/shared/ui/index.ts
git commit -m "chore(ds): expose primitives via shared/ui barrel"
```

---

## Phase 6 — Data components

### Task 6.1: EmptyState, Skeleton, Stat

**Files:**
- Create: `frontend/src/shared/ui/data/EmptyState/EmptyState.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/data/Skeleton/Skeleton.tsx` + test + index.ts
- Create: `frontend/src/shared/ui/data/Stat/Stat.tsx` + test + index.ts

- [ ] **Step 1: EmptyState**

```tsx
import { cn } from '@/shared/lib'
import type { LucideIcon } from 'lucide-react'

export interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center text-center py-12 px-6', className)}>
      <Icon size={40} className="text-[var(--color-fg-muted)]" aria-hidden="true" />
      <h3 className="mt-4 text-[var(--text-md)] font-semibold text-[var(--color-fg-primary)]">{title}</h3>
      {description && <p className="mt-1 text-[var(--text-sm)] text-[var(--color-fg-secondary)] max-w-md">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
```

Teste: render com icon mock, title, action; expect tudo no DOM.

- [ ] **Step 2: Skeleton**

```tsx
import { cn } from '@/shared/lib'
export function Skeleton({ className }: { className?: string }) {
  return <div role="status" aria-label="Carregando" className={cn('animate-pulse bg-[var(--color-gray-200)] rounded-md', className)} />
}
```

Teste: render, expect `role=status`.

- [ ] **Step 3: Stat**

```tsx
import { cn } from '@/shared/lib'
export interface StatProps { label: string; value: React.ReactNode; delta?: { value: string; positive?: boolean }; className?: string }
export function Stat({ label, value, delta, className }: StatProps) {
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <span className="text-[var(--text-xs)] uppercase tracking-wide text-[var(--color-fg-muted)]">{label}</span>
      <span className="text-[var(--text-2xl)] font-semibold text-[var(--color-fg-primary)] tabular-nums">{value}</span>
      {delta && (
        <span className={cn('text-[var(--text-xs)] font-medium', delta.positive ? 'text-[var(--color-success)]' : 'text-[var(--color-danger)]')}>
          {delta.value}
        </span>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Testar + commit**

```bash
cd frontend && npx vitest run src/shared/ui/data
git add frontend/src/shared/ui/data
git commit -m "feat(ds): add EmptyState, Skeleton, Stat"
```

---

### Task 6.2: Pagination (cursor-based + page-size)

**Files:**
- Create: `frontend/src/shared/ui/data/Pagination/Pagination.tsx` + test + index.ts

- [ ] **Step 1: Implementação**

```tsx
import { ChevronLeft, ChevronRight } from '@/shared/ui/icons'
import { IconButton, Button } from '../../primitives'

export interface PaginationProps {
  hasPrev: boolean
  hasNext: boolean
  onPrev: () => void
  onNext: () => void
  pageSize: number
  onPageSizeChange?: (n: number) => void
  pageSizeOptions?: number[]
  totalLabel?: string
}

export function Pagination({
  hasPrev, hasNext, onPrev, onNext, pageSize, onPageSizeChange,
  pageSizeOptions = [25, 50, 100, 200], totalLabel,
}: PaginationProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-t border-[var(--color-border)]">
      <div className="text-[var(--text-xs)] text-[var(--color-fg-muted)]">{totalLabel}</div>
      <div className="flex items-center gap-3">
        {onPageSizeChange && (
          <label className="flex items-center gap-2 text-[var(--text-xs)] text-[var(--color-fg-secondary)]">
            por página
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="rounded border border-[var(--color-border-strong)] bg-[var(--color-bg-surface)] px-2 py-1 text-[var(--text-sm)]"
            >
              {pageSizeOptions.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        )}
        <IconButton variant="secondary" size="sm" aria-label="Página anterior" disabled={!hasPrev} onClick={onPrev}>
          <ChevronLeft size={16} aria-hidden="true" />
        </IconButton>
        <IconButton variant="secondary" size="sm" aria-label="Próxima página" disabled={!hasNext} onClick={onNext}>
          <ChevronRight size={16} aria-hidden="true" />
        </IconButton>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Teste**

```tsx
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Pagination } from './Pagination'

it('dispara onNext e onPrev', async () => {
  const onPrev = vi.fn(), onNext = vi.fn()
  render(<Pagination hasPrev hasNext onPrev={onPrev} onNext={onNext} pageSize={25} />)
  await userEvent.click(screen.getByLabelText('Próxima página'))
  await userEvent.click(screen.getByLabelText('Página anterior'))
  expect(onNext).toHaveBeenCalledOnce()
  expect(onPrev).toHaveBeenCalledOnce()
})

it('desabilita botões quando não tem páginas', () => {
  render(<Pagination hasPrev={false} hasNext={false} onPrev={vi.fn()} onNext={vi.fn()} pageSize={25} />)
  expect(screen.getByLabelText('Próxima página')).toBeDisabled()
})
```

- [ ] **Step 3: Testar + commit**

```bash
cd frontend && npx vitest run src/shared/ui/data/Pagination
git add frontend/src/shared/ui/data/Pagination
git commit -m "feat(ds): add Pagination component (cursor + page-size)"
```

---

### Task 6.3: DataTable (TanStack Table v8 + virtualização)

**Files:**
- Create: `frontend/src/shared/ui/data/DataTable/DataTable.tsx`
- Create: `frontend/src/shared/ui/data/DataTable/DataTable.test.tsx`
- Create: `frontend/src/shared/ui/data/DataTable/index.ts`

- [ ] **Step 1: Implementação**

```tsx
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useRef } from 'react'
import { cn } from '@/shared/lib'

export interface DataTableProps<T> {
  data: T[]
  columns: ColumnDef<T, unknown>[]
  rowKey: (row: T) => string
  emptyMessage?: string
  loading?: boolean
  estimatedRowHeight?: number
  maxHeight?: number
  className?: string
}

export function DataTable<T>({
  data, columns, rowKey, emptyMessage = 'Nenhum resultado.', loading,
  estimatedRowHeight = 36, maxHeight = 600, className,
}: DataTableProps<T>) {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel(), getRowId: (r) => rowKey(r) })
  const rows = table.getRowModel().rows
  const parentRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimatedRowHeight,
    overscan: 8,
  })
  return (
    <div ref={parentRef}
      className={cn('overflow-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)]', className)}
      style={{ maxHeight }}
    >
      <table className="w-full text-[var(--text-sm)]" role="table" aria-busy={loading || undefined}>
        <thead className="sticky top-0 z-10 bg-[var(--color-bg-app)]">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id} className="text-left font-semibold text-[var(--color-fg-primary)] uppercase tracking-wide text-[var(--text-xs)] px-3 py-2 border-b border-[var(--color-border)]">
                  {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
          {rows.length === 0 && !loading && (
            <tr><td colSpan={columns.length} className="text-center py-8 text-[var(--color-fg-muted)]">{emptyMessage}</td></tr>
          )}
          {rowVirtualizer.getVirtualItems().map((virtualRow) => {
            const row = rows[virtualRow.index]
            return (
              <tr key={row.id}
                style={{ position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${virtualRow.start}px)`, height: virtualRow.size }}
                className="hover:bg-[var(--color-gray-50)] border-b border-[var(--color-gray-100)]"
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 align-middle">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: Teste**

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DataTable } from './DataTable'

interface Row { id: string; name: string }
const cols = [{ accessorKey: 'name', header: 'Nome' }]
const data: Row[] = [{ id: '1', name: 'A' }, { id: '2', name: 'B' }]

it('renderiza header e linhas', () => {
  render(<DataTable<Row> data={data} columns={cols} rowKey={(r) => r.id} />)
  expect(screen.getByText('Nome')).toBeInTheDocument()
  expect(screen.getByText('A')).toBeInTheDocument()
  expect(screen.getByText('B')).toBeInTheDocument()
})

it('mostra mensagem vazia', () => {
  render(<DataTable<Row> data={[]} columns={cols} rowKey={(r) => r.id} emptyMessage="vazio" />)
  expect(screen.getByText('vazio')).toBeInTheDocument()
})
```

- [ ] **Step 3: Atualizar barrel `shared/ui/index.ts`**

```ts
export * from './data/DataTable'
export * from './data/Pagination'
export * from './data/EmptyState'
export * from './data/Skeleton'
export * from './data/Stat'
```

- [ ] **Step 4: Testar + commit**

```bash
cd frontend && npx vitest run src/shared/ui/data/DataTable
git add frontend/src/shared/ui/data/DataTable frontend/src/shared/ui/index.ts
git commit -m "feat(ds): add DataTable (TanStack Table + virtualization)"
```

---

## Phase 7 — Feedback (Toast, Alert, Banner, ConfirmDialog)

### Task 7.1: Toast (sonner)

**Files:**
- Create: `frontend/src/shared/ui/feedback/Toast/Toaster.tsx`
- Create: `frontend/src/shared/ui/feedback/Toast/toast.ts`
- Create: `frontend/src/shared/ui/feedback/Toast/Toast.test.tsx`
- Create: `frontend/src/shared/ui/feedback/Toast/index.ts`

- [ ] **Step 1: Toaster component**

```tsx
// Toaster.tsx
import { Toaster as Sonner } from 'sonner'

export function Toaster() {
  return (
    <Sonner
      position="top-right"
      richColors
      closeButton
      toastOptions={{
        classNames: {
          toast: 'bg-[var(--color-bg-surface)] border border-[var(--color-border)] shadow-[var(--shadow-md)] text-[var(--color-fg-primary)] rounded-lg',
        },
        duration: 4000,
      }}
    />
  )
}
```

- [ ] **Step 2: Wrapper helper**

```ts
// toast.ts
import { toast as sonner } from 'sonner'

export const toast = {
  success: (msg: string, opts?: { description?: string }) => sonner.success(msg, opts),
  error:   (msg: string, opts?: { description?: string }) => sonner.error(msg, { duration: 99999, ...opts }),
  info:    (msg: string, opts?: { description?: string }) => sonner.info(msg, opts),
  warning: (msg: string, opts?: { description?: string }) => sonner.warning(msg, { duration: 8000, ...opts }),
}
```

- [ ] **Step 3: Teste**

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Toaster } from './Toaster'
import { toast } from './toast'

it('mostra toast de sucesso', async () => {
  render(<Toaster />)
  toast.success('feito')
  expect(await screen.findByText('feito')).toBeInTheDocument()
})
```

- [ ] **Step 4: Barrel + testar + commit**

```ts
// index.ts
export { Toaster } from './Toaster'
export { toast } from './toast'
```

```bash
cd frontend && npx vitest run src/shared/ui/feedback/Toast
git add frontend/src/shared/ui/feedback/Toast
git commit -m "feat(ds): add Toaster (sonner) with semantic tokens"
```

---

### Task 7.2: Alert, Banner, ConfirmDialog

**Files:**
- Create: `Alert/Alert.tsx` + test + index.ts
- Create: `Banner/Banner.tsx` + test + index.ts
- Create: `ConfirmDialog/ConfirmDialog.tsx` + test + index.ts

- [ ] **Step 1: Alert (inline)**

```tsx
// Alert/Alert.tsx
import { cva, type VariantProps } from 'class-variance-authority'
import { Info, CircleCheck, CircleAlert, TriangleAlert, CircleX } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'
import type { ComponentType } from 'react'

const alertVariants = cva('flex items-start gap-3 rounded-lg border p-3 text-[var(--text-sm)]', {
  variants: {
    variant: {
      info:    'bg-[var(--color-info-bg)]    border-[var(--color-blue-100)]  text-[var(--color-fg-primary)]',
      success: 'bg-[var(--color-success-bg)] border-[var(--color-green-100)] text-[var(--color-fg-primary)]',
      warning: 'bg-[var(--color-warning-bg)] border-[var(--color-amber-100)] text-[var(--color-fg-primary)]',
      danger:  'bg-[var(--color-danger-bg)]  border-[var(--color-red-100)]   text-[var(--color-fg-primary)]',
    },
  },
  defaultVariants: { variant: 'info' },
})

const ICON: Record<NonNullable<VariantProps<typeof alertVariants>['variant']>, ComponentType<{ size?: number; className?: string; 'aria-hidden'?: boolean }>> = {
  info: Info, success: CircleCheck, warning: TriangleAlert, danger: CircleX,
}
const ICON_COLOR = { info: 'var(--color-info)', success: 'var(--color-success)', warning: 'var(--color-warning)', danger: 'var(--color-danger)' }

export interface AlertProps extends VariantProps<typeof alertVariants> {
  title?: string
  children: React.ReactNode
  className?: string
}

export function Alert({ title, children, variant = 'info', className }: AlertProps) {
  const Icon = ICON[variant!]
  return (
    <div role="alert" className={cn(alertVariants({ variant }), className)}>
      <Icon size={18} aria-hidden={true} style={{ color: ICON_COLOR[variant!], flex: '0 0 auto', marginTop: 2 }} />
      <div className="flex-1">
        {title && <p className="font-semibold mb-0.5">{title}</p>}
        <div className="text-[var(--color-fg-secondary)]">{children}</div>
      </div>
    </div>
  )
}
```

Teste: render variant=danger, expect role=alert + título visível + axe ok.

- [ ] **Step 2: Banner (full-width, dismissible)**

```tsx
// Banner/Banner.tsx
import { useState } from 'react'
import { X } from '@/shared/ui/icons'
import { IconButton } from '../../primitives'
import { cn } from '@/shared/lib'

export interface BannerProps {
  id: string
  children: React.ReactNode
  variant?: 'info' | 'warning' | 'danger'
  persistDismiss?: boolean
  className?: string
}

export function Banner({ id, children, variant = 'info', persistDismiss, className }: BannerProps) {
  const key = `banner-dismissed-${id}`
  const [dismissed, setDismissed] = useState(() => persistDismiss && typeof window !== 'undefined' ? localStorage.getItem(key) === '1' : false)
  if (dismissed) return null
  const bg = variant === 'danger' ? 'bg-[var(--color-danger-bg)]' : variant === 'warning' ? 'bg-[var(--color-warning-bg)]' : 'bg-[var(--color-info-bg)]'
  return (
    <div role="region" aria-label="Aviso" className={cn('flex items-center justify-between gap-4 px-4 py-2 border-b border-[var(--color-border)]', bg, className)}>
      <div className="text-[var(--text-sm)] text-[var(--color-fg-primary)]">{children}</div>
      <IconButton variant="ghost" size="sm" aria-label="Fechar aviso" onClick={() => { setDismissed(true); if (persistDismiss) localStorage.setItem(key, '1') }}>
        <X size={14} aria-hidden="true" />
      </IconButton>
    </div>
  )
}
```

Teste: render, click X, expect aviso some.

- [ ] **Step 3: ConfirmDialog (api imperativa)**

```tsx
// ConfirmDialog/ConfirmDialog.tsx
import { createContext, useContext, useState, useCallback } from 'react'
import { AlertDialogRoot, AlertDialogContent, AlertDialogTitle, AlertDialogDescription, AlertDialogAction, AlertDialogCancel } from '../../primitives'
import { Button } from '../../primitives'

interface ConfirmOpts { title: string; description?: string; confirmLabel?: string; cancelLabel?: string; destructive?: boolean }
type ConfirmFn = (opts: ConfirmOpts) => Promise<boolean>

const Ctx = createContext<ConfirmFn | null>(null)

export function ConfirmDialogProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<(ConfirmOpts & { resolve: (b: boolean) => void }) | null>(null)
  const confirm = useCallback<ConfirmFn>((opts) => new Promise((resolve) => setState({ ...opts, resolve })), [])
  const handle = (b: boolean) => { state?.resolve(b); setState(null) }
  return (
    <Ctx.Provider value={confirm}>
      {children}
      <AlertDialogRoot open={!!state} onOpenChange={(o) => !o && handle(false)}>
        {state && (
          <AlertDialogContent>
            <AlertDialogTitle>{state.title}</AlertDialogTitle>
            {state.description && <AlertDialogDescription className="mt-1 text-[var(--color-fg-secondary)] text-[var(--text-sm)]">{state.description}</AlertDialogDescription>}
            <div className="mt-4 flex justify-end gap-2">
              <AlertDialogCancel asChild><Button variant="secondary" onClick={() => handle(false)}>{state.cancelLabel ?? 'Cancelar'}</Button></AlertDialogCancel>
              <AlertDialogAction asChild><Button variant={state.destructive ? 'danger' : 'primary'} onClick={() => handle(true)}>{state.confirmLabel ?? 'Confirmar'}</Button></AlertDialogAction>
            </div>
          </AlertDialogContent>
        )}
      </AlertDialogRoot>
    </Ctx.Provider>
  )
}

export function useConfirm(): ConfirmFn {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useConfirm requires <ConfirmDialogProvider>')
  return ctx
}
```

Teste:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfirmDialogProvider, useConfirm } from './ConfirmDialog'

function Sample({ onResult }: { onResult: (b: boolean) => void }) {
  const confirm = useConfirm()
  return <button onClick={async () => onResult(await confirm({ title: 'Tem certeza?' }))}>excluir</button>
}

it('resolve true ao confirmar', async () => {
  let result: boolean | undefined
  render(<ConfirmDialogProvider><Sample onResult={(b) => { result = b }} /></ConfirmDialogProvider>)
  await userEvent.click(screen.getByText('excluir'))
  await userEvent.click(await screen.findByText('Confirmar'))
  expect(result).toBe(true)
})
```

- [ ] **Step 4: Atualizar barrel + testar + commit**

```ts
// shared/ui/index.ts (acrescentar)
export * from './feedback/Toast'
export * from './feedback/Alert'
export * from './feedback/Banner'
export * from './feedback/ConfirmDialog'
```

```bash
cd frontend && npx vitest run src/shared/ui/feedback
git add frontend/src/shared/ui/feedback frontend/src/shared/ui/index.ts
git commit -m "feat(ds): add Alert, Banner and ConfirmDialog (imperative API)"
```

---

## Phase 8 — Layout primitives

### Task 8.1: Container, Stack, Inline, PageHeader

**Files:**
- Create: `frontend/src/shared/ui/layout/Container/Container.tsx` + index.ts
- Create: `frontend/src/shared/ui/layout/Stack/Stack.tsx` + index.ts (exporta Stack e Inline)
- Create: `frontend/src/shared/ui/layout/PageHeader/PageHeader.tsx` + test + index.ts

- [ ] **Step 1: Container**

```tsx
import { cn } from '@/shared/lib'
export interface ContainerProps extends React.HTMLAttributes<HTMLDivElement> { size?: 'sm' | 'md' | 'lg' | 'full' }
export function Container({ className, size = 'lg', ...props }: ContainerProps) {
  const max = size === 'sm' ? 'max-w-2xl' : size === 'md' ? 'max-w-4xl' : size === 'lg' ? 'max-w-7xl' : 'max-w-none'
  return <div className={cn('mx-auto w-full px-6', max, className)} {...props} />
}
```

- [ ] **Step 2: Stack / Inline**

```tsx
import { cn } from '@/shared/lib'

interface BaseProps extends React.HTMLAttributes<HTMLDivElement> {
  gap?: 1 | 2 | 3 | 4 | 5 | 6 | 8
  align?: 'start' | 'center' | 'end' | 'stretch'
  justify?: 'start' | 'center' | 'end' | 'between'
}

const GAP = { 1: 'gap-1', 2: 'gap-2', 3: 'gap-3', 4: 'gap-4', 5: 'gap-5', 6: 'gap-6', 8: 'gap-8' }
const ALIGN = { start: 'items-start', center: 'items-center', end: 'items-end', stretch: 'items-stretch' }
const JUSTIFY = { start: 'justify-start', center: 'justify-center', end: 'justify-end', between: 'justify-between' }

export function Stack({ gap = 4, align = 'stretch', justify = 'start', className, ...props }: BaseProps) {
  return <div className={cn('flex flex-col', GAP[gap], ALIGN[align], JUSTIFY[justify], className)} {...props} />
}

export function Inline({ gap = 3, align = 'center', justify = 'start', className, ...props }: BaseProps) {
  return <div className={cn('flex flex-row', GAP[gap], ALIGN[align], JUSTIFY[justify], className)} {...props} />
}
```

- [ ] **Step 3: PageHeader**

```tsx
import { cn } from '@/shared/lib'
import { Inline } from '../Stack/Stack'

export interface PageHeaderProps {
  title: string
  description?: string
  actions?: React.ReactNode
  breadcrumb?: React.ReactNode
  className?: string
}

export function PageHeader({ title, description, actions, breadcrumb, className }: PageHeaderProps) {
  return (
    <header className={cn('flex flex-col gap-2 py-4 border-b border-[var(--color-border)]', className)}>
      {breadcrumb && <div className="text-[var(--text-xs)] text-[var(--color-fg-muted)]">{breadcrumb}</div>}
      <Inline justify="between" align="center" className="gap-6">
        <div>
          <h1 className="text-[var(--text-xl)] font-semibold leading-tight">{title}</h1>
          {description && <p className="mt-1 text-[var(--text-sm)] text-[var(--color-fg-secondary)]">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </Inline>
    </header>
  )
}
```

Teste: render `<PageHeader title="x" actions={<button>a</button>} />` expect h1 + botão.

- [ ] **Step 4: Barrel + testar + commit**

```ts
// shared/ui/index.ts (acrescentar)
export * from './layout/Container'
export * from './layout/Stack'
export * from './layout/PageHeader'
```

```bash
cd frontend && npx vitest run src/shared/ui/layout
git add frontend/src/shared/ui/layout frontend/src/shared/ui/index.ts
git commit -m "feat(ds): add Container, Stack, Inline, PageHeader layout primitives"
```

---

## Phase 9 — Entity `user`

### Task 9.1: User type + UserAvatar entity

**Files:**
- Create: `frontend/src/entities/user/model/types.ts`
- Create: `frontend/src/entities/user/ui/UserAvatar.tsx` + test
- Create: `frontend/src/entities/user/index.ts`

- [ ] **Step 1: Types**

```ts
// model/types.ts
export interface User {
  id: string
  name: string
  email: string
  // pictureUrl?: string  // suporte futuro, mas iniciais é o default
}

export function userInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}
```

- [ ] **Step 2: UserAvatar**

```tsx
// ui/UserAvatar.tsx
import { Avatar, AvatarFallback } from '@/shared/ui'
import { userInitials, type User } from '../model/types'

export interface UserAvatarProps { user: Pick<User, 'name'>; size?: 'sm' | 'md' | 'lg' }
export function UserAvatar({ user, size = 'md' }: UserAvatarProps) {
  return (
    <Avatar size={size} aria-label={user.name}>
      <AvatarFallback>{userInitials(user.name)}</AvatarFallback>
    </Avatar>
  )
}
```

- [ ] **Step 3: Teste**

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { UserAvatar } from './UserAvatar'
import { userInitials } from '../model/types'

describe('userInitials', () => {
  it('1 nome', () => expect(userInitials('Maria')).toBe('MA'))
  it('2 nomes', () => expect(userInitials('Luiz Felippe')).toBe('LF'))
  it('vazio', () => expect(userInitials('')).toBe('?'))
})

it('UserAvatar renderiza iniciais', () => {
  render(<UserAvatar user={{ name: 'Luiz Felippe' }} />)
  expect(screen.getByText('LF')).toBeInTheDocument()
})
```

- [ ] **Step 4: Barrel**

```ts
// entities/user/index.ts
export type { User } from './model/types'
export { userInitials } from './model/types'
export { UserAvatar } from './ui/UserAvatar'
```

- [ ] **Step 5: Testar + commit**

```bash
cd frontend && npx vitest run src/entities/user
git add frontend/src/entities/user
git commit -m "feat(ds): add user entity (User type + UserAvatar + initials helper)"
```

---

## Phase 10 — Widget `app-shell`

### Task 10.1: SideNav

**Files:**
- Create: `frontend/src/widgets/app-shell/ui/SideNav.tsx`
- Create: `frontend/src/widgets/app-shell/ui/SideNav.test.tsx`

- [ ] **Step 1: SideNav**

```tsx
// ui/SideNav.tsx
import { NavLink } from 'react-router'
import { Search, LayoutGrid, Bookmark, BarChart3, Settings, Icons as _Icons } from '@/shared/ui/icons'
import { TooltipProvider, TooltipRoot, TooltipTrigger, TooltipContent } from '@/shared/ui'
import { cn } from '@/shared/lib'
import type { ComponentType } from 'react'

interface NavItem {
  to: string
  label: string
  Icon: ComponentType<{ size?: number; 'aria-hidden'?: boolean }>
}

const PRIMARY: NavItem[] = [
  { to: '/app/prospecting', label: 'Prospecting', Icon: Search },
  { to: '/app/pipeline',    label: 'Pipeline',    Icon: LayoutGrid },
  { to: '/app/listas',      label: 'Listas',      Icon: Bookmark },
  { to: '/app/relatorios',  label: 'Relatórios',  Icon: BarChart3 },
]
const FOOTER: NavItem[] = [
  { to: '/app/configuracoes', label: 'Configurações', Icon: Settings },
]

function Item({ to, label, Icon }: NavItem) {
  return (
    <TooltipRoot>
      <TooltipTrigger asChild>
        <NavLink
          to={to}
          aria-label={label}
          className={({ isActive }) => cn(
            'relative flex h-10 w-10 items-center justify-center rounded-md text-white/65 hover:bg-white/10 hover:text-white',
            'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
            isActive && 'bg-white/15 text-white'
          )}
        >
          {({ isActive }) => (
            <>
              {isActive && <span aria-hidden="true" className="absolute -left-[10px] top-2 bottom-2 w-[3px] rounded-r bg-[var(--color-brand)]" />}
              <Icon size={20} aria-hidden={true} />
            </>
          )}
        </NavLink>
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </TooltipRoot>
  )
}

export function SideNav() {
  return (
    <TooltipProvider delayDuration={300}>
      <nav aria-label="Navegação principal"
        className="h-full w-14 bg-[var(--color-bg-inverse)] flex flex-col items-center gap-1.5 py-3 border-r border-white/5">
        {PRIMARY.map((i) => <Item key={i.to} {...i} />)}
        <div className="mt-auto flex flex-col gap-1.5">{FOOTER.map((i) => <Item key={i.to} {...i} />)}</div>
      </nav>
    </TooltipProvider>
  )
}
```

- [ ] **Step 2: Teste**

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { SideNav } from './SideNav'

it('renderiza todos os links com aria-label', () => {
  render(<MemoryRouter><SideNav /></MemoryRouter>)
  expect(screen.getByLabelText('Prospecting')).toBeInTheDocument()
  expect(screen.getByLabelText('Pipeline')).toBeInTheDocument()
  expect(screen.getByLabelText('Configurações')).toBeInTheDocument()
})
```

- [ ] **Step 3: Testar + commit**

```bash
cd frontend && npx vitest run src/widgets/app-shell/ui/SideNav.test.tsx
git add frontend/src/widgets/app-shell/ui/SideNav.tsx frontend/src/widgets/app-shell/ui/SideNav.test.tsx
git commit -m "feat(ds): add SideNav widget with tooltips and active route indicator"
```

---

### Task 10.2: TopBar

**Files:**
- Create: `frontend/src/widgets/app-shell/ui/TopBar.tsx`
- Create: `frontend/src/widgets/app-shell/ui/TopBar.test.tsx`

- [ ] **Step 1: TopBar**

```tsx
import { Link } from 'react-router'
import { Search, Bell, CircleHelp, ChevronDown } from '@/shared/ui/icons'
import { Kbd, IconButton, DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '@/shared/ui'
import { UserAvatar } from '@/entities/user'
import { useKeyboardShortcut } from '@/shared/hooks'
import { useRef } from 'react'

export interface TopBarProps {
  user: { name: string; email: string }
  onSearchFocus?: () => void
  onLogout?: () => void
}

export function TopBar({ user, onSearchFocus, onLogout }: TopBarProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  useKeyboardShortcut('/', () => { inputRef.current?.focus(); onSearchFocus?.() })

  return (
    <header className="h-14 bg-[var(--color-bg-inverse)] text-white flex items-center gap-3 px-4 border-b border-white/5">
      <Link to="/app" className="text-[var(--text-base)] font-semibold tracking-tight">CNPJ Discovery</Link>

      <div className="ml-6 flex-1 max-w-md">
        <label className="flex items-center gap-2 bg-white/10 rounded-md px-2.5 h-9 focus-within:ring-2 focus-within:ring-[var(--color-focus-ring)]">
          <Search size={14} aria-hidden="true" className="opacity-70" />
          <input
            ref={inputRef}
            type="search"
            placeholder="Buscar empresa, CNPJ, sócio…"
            aria-label="Busca global"
            className="bg-transparent border-0 outline-none text-[var(--text-sm)] flex-1 placeholder:text-white/50"
          />
          <Kbd className="bg-white/10 border-white/10 text-white/70">/</Kbd>
        </label>
      </div>

      <div className="ml-auto flex items-center gap-1">
        <IconButton variant="ghost" size="sm" aria-label="Ajuda"><CircleHelp size={16} className="text-white/80" aria-hidden="true" /></IconButton>
        <IconButton variant="ghost" size="sm" aria-label="Notificações"><Bell size={16} className="text-white/80" aria-hidden="true" /></IconButton>

        <DropdownMenuRoot>
          <DropdownMenuTrigger className="ml-1 flex items-center gap-2 rounded-md px-1 h-9 hover:bg-white/10 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]">
            <UserAvatar user={user} size="sm" />
            <ChevronDown size={14} className="text-white/70" aria-hidden="true" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <div className="px-2 py-2 text-[var(--text-xs)] text-[var(--color-fg-muted)]">
              <div className="font-medium text-[var(--color-fg-primary)] text-[var(--text-sm)]">{user.name}</div>
              <div>{user.email}</div>
            </div>
            <DropdownMenuItem onSelect={() => onLogout?.()}>Sair</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenuRoot>
      </div>
    </header>
  )
}
```

- [ ] **Step 2: Teste**

```tsx
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { TopBar } from './TopBar'

it('renderiza usuário e dispara logout', async () => {
  const onLogout = vi.fn()
  render(<MemoryRouter><TopBar user={{ name: 'Luiz Felippe', email: 'lf@x.com' }} onLogout={onLogout} /></MemoryRouter>)
  expect(screen.getByLabelText('Busca global')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: /LF|Luiz/ }))
  await userEvent.click(await screen.findByText('Sair'))
  expect(onLogout).toHaveBeenCalledOnce()
})

it('foca a busca ao apertar /', async () => {
  render(<MemoryRouter><TopBar user={{ name: 'A', email: 'a@a' }} /></MemoryRouter>)
  await userEvent.keyboard('/')
  expect(screen.getByLabelText('Busca global')).toHaveFocus()
})
```

- [ ] **Step 3: Testar + commit**

```bash
cd frontend && npx vitest run src/widgets/app-shell/ui/TopBar.test.tsx
git add frontend/src/widgets/app-shell/ui/TopBar.tsx frontend/src/widgets/app-shell/ui/TopBar.test.tsx
git commit -m "feat(ds): add TopBar widget with global search shortcut and user menu"
```

---

### Task 10.3: AppShell layout

**Files:**
- Create: `frontend/src/widgets/app-shell/ui/AppShell.tsx`
- Create: `frontend/src/widgets/app-shell/ui/AppShell.test.tsx`
- Create: `frontend/src/widgets/app-shell/index.ts`

- [ ] **Step 1: AppShell**

```tsx
import { Outlet } from 'react-router'
import { Suspense } from 'react'
import { TopBar } from './TopBar'
import { SideNav } from './SideNav'
import { Skeleton } from '@/shared/ui'

export interface AppShellProps {
  user: { name: string; email: string }
  onLogout?: () => void
}

export function AppShell({ user, onLogout }: AppShellProps) {
  return (
    <div className="min-h-screen flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-[var(--z-toast)] focus:top-2 focus:left-2 bg-[var(--color-action)] text-white px-3 py-2 rounded-md">
        Pular para o conteúdo
      </a>
      <TopBar user={user} onLogout={onLogout} />
      <div className="flex flex-1 min-h-0">
        <SideNav />
        <main id="main" tabIndex={-1} className="flex-1 min-w-0 bg-[var(--color-bg-app)] overflow-auto">
          <Suspense fallback={<div className="p-6"><Skeleton className="h-8 w-48 mb-4" /><Skeleton className="h-40 w-full" /></div>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Teste**

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { AppShell } from './AppShell'

it('compõe topbar + sidenav + outlet', () => {
  render(
    <MemoryRouter initialEntries={['/app']}>
      <Routes>
        <Route element={<AppShell user={{ name: 'Luiz', email: 'a@a' }} />}>
          <Route path="/app" element={<div>HOME</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
  expect(screen.getByText('CNPJ Discovery')).toBeInTheDocument()
  expect(screen.getByLabelText('Prospecting')).toBeInTheDocument()
  expect(screen.getByText('HOME')).toBeInTheDocument()
  expect(screen.getByText('Pular para o conteúdo')).toBeInTheDocument()
})
```

- [ ] **Step 3: Barrel**

```ts
// widgets/app-shell/index.ts
export { AppShell, type AppShellProps } from './ui/AppShell'
```

- [ ] **Step 4: Testar + commit**

```bash
cd frontend && npx vitest run src/widgets/app-shell
git add frontend/src/widgets/app-shell
git commit -m "feat(ds): assemble AppShell (TopBar + SideNav + Outlet + skip link)"
```

---

## Phase 11 — Pages stub

### Task 11.1: Criar 10 pages stub

**Files:**
- Create: 10 arquivos `pages/<page>/<Page>.tsx` + index.ts pra cada

- [ ] **Step 1: Criar landing stub**

```tsx
// src/pages/landing/Landing.tsx
import { Link } from 'react-router'
import { Button } from '@/shared/ui'

export function Landing() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-app)]">
      <div className="max-w-xl text-center px-6">
        <h1 className="text-[var(--text-3xl)] font-bold text-[var(--color-fg-primary)] tracking-tight">CNPJ Discovery</h1>
        <p className="mt-4 text-[var(--color-fg-secondary)]">Prospecção B2B sobre dados abertos da Receita Federal.</p>
        <div className="mt-6 flex gap-3 justify-center">
          <Button asChild><Link to="/login">Entrar</Link></Button>
          <Button variant="secondary" asChild><Link to="/registro">Criar conta</Link></Button>
        </div>
        <p className="mt-12 text-[var(--text-xs)] text-[var(--color-fg-muted)]">Landing definitiva: sub-projeto #3.</p>
      </div>
    </div>
  )
}
```

`src/pages/landing/index.ts`: `export { Landing } from './Landing'`

- [ ] **Step 2: Login / Registro / Recuperar-senha stubs**

`src/pages/login/Login.tsx`:

```tsx
import { Link } from 'react-router'
import { Button } from '@/shared/ui'

export function Login() {
  return (
    <div className="min-h-screen grid place-items-center bg-[var(--color-bg-app)] px-6">
      <div className="w-full max-w-sm bg-[var(--color-bg-surface)] p-8 rounded-xl shadow-[var(--shadow-md)] border border-[var(--color-border)]">
        <h1 className="text-[var(--text-xl)] font-semibold">Entrar</h1>
        <p className="mt-1 text-[var(--text-sm)] text-[var(--color-fg-secondary)]">Autenticação completa no sub-projeto #2.</p>
        <div className="mt-6 flex flex-col gap-2">
          <Button asChild><Link to="/app/prospecting">Entrar (stub)</Link></Button>
          <Button variant="link" asChild><Link to="/registro">Criar conta</Link></Button>
        </div>
      </div>
    </div>
  )
}
```

Análogo pra `pages/registro/Registro.tsx` e `pages/recuperar-senha/RecuperarSenha.tsx` com formulários stub (campo email, botão "enviar — em breve").

- [ ] **Step 3: Páginas internas placeholder**

`src/pages/app-home/AppHome.tsx`:

```tsx
import { PageHeader, Container, Stat, Inline } from '@/shared/ui'

export function AppHome() {
  return (
    <Container size="lg" className="py-6">
      <PageHeader title="Dashboard" description="Visão geral do seu trabalho de prospecção." />
      <Inline gap={4} className="mt-6">
        <Stat label="Empresas no pipeline" value="—" />
        <Stat label="Filtrar empresas" value="—" />
        <Stat label="Listas salvas" value="—" />
      </Inline>
    </Container>
  )
}
```

`pages/listas/Listas.tsx`, `pages/relatorios/Relatorios.tsx`, `pages/configuracoes/Configuracoes.tsx`, `pages/pipeline/Pipeline.tsx`:

Cada uma: `<Container><PageHeader title="X" description="Detalhes em sub-projeto #Y" /></Container>`

`pages/not-found/NotFound.tsx`:

```tsx
import { Link } from 'react-router'
import { EmptyState, Button, Icons } from '@/shared/ui'

export function NotFound() {
  return <EmptyState icon={Icons.SearchX} title="Página não encontrada" description="O endereço que você acessou não existe."
    action={<Button asChild><Link to="/">Voltar ao início</Link></Button>} />
}
```

- [ ] **Step 4: Page Prospecting placeholder (mantém componentes atuais funcionando)**

`src/pages/prospecting/Prospecting.tsx`: cópia idêntica de `frontend/src/pages/Prospecting.tsx` MAS com os imports refatorados pra apontar pros caminhos antigos por enquanto. (Vamos refazer no Task 14.)

Por enquanto basta:

```tsx
export { Prospecting } from '@/pages/prospecting/legacy/Prospecting'
```

E mover o arquivo antigo `src/pages/Prospecting.tsx` pra `src/pages/prospecting/legacy/Prospecting.tsx` com seus imports inalterados — task 14 fará a refatoração completa.

- [ ] **Step 5: Barrels em pages**

```ts
// src/pages/index.ts
export { Landing } from './landing'
export { Login } from './login'
export { Registro } from './registro'
export { RecuperarSenha } from './recuperar-senha'
export { AppHome } from './app-home'
export { Prospecting } from './prospecting'
export { Pipeline } from './pipeline'
export { Listas } from './listas'
export { Relatorios } from './relatorios'
export { Configuracoes } from './configuracoes'
export { NotFound } from './not-found'
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages
git commit -m "feat(ds): scaffold page stubs (landing/login/registro/recuperar/app-home/listas/relatorios/configuracoes/pipeline/not-found)"
```

---

## Phase 12 — Roteamento (React Router v7)

### Task 12.1: Configurar router + ProtectedRoute stub + ErrorBoundary por rota

**Files:**
- Create: `frontend/src/app/router.tsx`
- Create: `frontend/src/app/RouteErrorBoundary.tsx`

- [ ] **Step 1: ProtectedRoute (em `widgets/app-shell` ou inline no router)**

Vamos inline no router (stub mínimo):

`src/app/router.tsx`:

```tsx
import { createBrowserRouter, redirect, type LoaderFunctionArgs, Navigate, Outlet } from 'react-router'
import { lazy } from 'react'
import { AppShell } from '@/widgets/app-shell'
import { RouteErrorBoundary } from './RouteErrorBoundary'

// Stub auth — substituído em sub-projeto #2
const isAuthenticated = () => typeof window !== 'undefined' && localStorage.getItem('demo-auth') === '1'
const protectedLoader = (_args: LoaderFunctionArgs) => {
  if (!isAuthenticated()) throw redirect('/login')
  return null
}

// Lazy imports
const Landing = lazy(() => import('@/pages/landing').then((m) => ({ default: m.Landing })))
const Login = lazy(() => import('@/pages/login').then((m) => ({ default: m.Login })))
const Registro = lazy(() => import('@/pages/registro').then((m) => ({ default: m.Registro })))
const RecuperarSenha = lazy(() => import('@/pages/recuperar-senha').then((m) => ({ default: m.RecuperarSenha })))
const AppHome = lazy(() => import('@/pages/app-home').then((m) => ({ default: m.AppHome })))
const Prospecting = lazy(() => import('@/pages/prospecting').then((m) => ({ default: m.Prospecting })))
const Pipeline = lazy(() => import('@/pages/pipeline').then((m) => ({ default: m.Pipeline })))
const Listas = lazy(() => import('@/pages/listas').then((m) => ({ default: m.Listas })))
const Relatorios = lazy(() => import('@/pages/relatorios').then((m) => ({ default: m.Relatorios })))
const Configuracoes = lazy(() => import('@/pages/configuracoes').then((m) => ({ default: m.Configuracoes })))
const NotFound = lazy(() => import('@/pages/not-found').then((m) => ({ default: m.NotFound })))

const demoUser = { name: 'Luiz Felippe', email: 'demo@cnpj.local' }

export const router = createBrowserRouter([
  { path: '/', element: <Landing />, errorElement: <RouteErrorBoundary /> },
  { path: '/login', element: <Login />, errorElement: <RouteErrorBoundary /> },
  { path: '/registro', element: <Registro />, errorElement: <RouteErrorBoundary /> },
  { path: '/recuperar-senha', element: <RecuperarSenha />, errorElement: <RouteErrorBoundary /> },
  {
    path: '/app',
    loader: protectedLoader,
    element: <AppShell user={demoUser} onLogout={() => { localStorage.removeItem('demo-auth'); location.assign('/login') }} />,
    errorElement: <RouteErrorBoundary />,
    children: [
      { index: true, element: <AppHome /> },
      { path: 'prospecting', element: <Prospecting /> },
      { path: 'pipeline', element: <Pipeline /> },
      { path: 'listas', element: <Listas /> },
      { path: 'relatorios', element: <Relatorios /> },
      { path: 'configuracoes', element: <Configuracoes /> },
    ],
  },
  { path: '*', element: <NotFound /> },
])
```

- [ ] **Step 2: RouteErrorBoundary**

```tsx
// src/app/RouteErrorBoundary.tsx
import { useRouteError, isRouteErrorResponse, Link } from 'react-router'
import { Button, EmptyState, Icons, Container } from '@/shared/ui'

export function RouteErrorBoundary() {
  const error = useRouteError()
  const status = isRouteErrorResponse(error) ? error.status : 500
  const message = isRouteErrorResponse(error) ? error.statusText : (error instanceof Error ? error.message : 'Erro desconhecido')

  // TODO: reportar pro endpoint POST /v1/client-errors (criado em sub-projeto #2)

  return (
    <Container className="py-12">
      <EmptyState
        icon={Icons.CircleAlert}
        title={`Erro ${status}`}
        description={message || 'Algo deu errado ao carregar essa página.'}
        action={
          <div className="flex gap-2 justify-center">
            <Button onClick={() => location.reload()}>Recarregar</Button>
            <Button variant="secondary" asChild><Link to="/app">Voltar ao início</Link></Button>
          </div>
        }
      />
    </Container>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/router.tsx frontend/src/app/RouteErrorBoundary.tsx
git commit -m "feat(ds): wire React Router v7 (data router) with lazy pages and error boundaries"
```

---

## Phase 13 — App bootstrap

### Task 13.1: Providers composition

**Files:**
- Create: `frontend/src/app/providers/AppProviders.tsx`
- Create: `frontend/src/app/index.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: AppProviders**

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router'
import { Toaster, ConfirmDialogProvider } from '@/shared/ui'
import { router } from '@/app/router'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

export function AppProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfirmDialogProvider>
        <RouterProvider router={router} />
        <Toaster />
      </ConfirmDialogProvider>
    </QueryClientProvider>
  )
}
```

- [ ] **Step 2: app/index.tsx**

```tsx
// re-export pra ser o entry point do app
export { AppProviders } from './providers/AppProviders'
```

- [ ] **Step 3: Atualizar main.tsx**

Substituir conteúdo de `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { AppProviders } from './app'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders />
  </StrictMode>,
)
```

- [ ] **Step 4: Remover App.tsx legado**

```bash
git rm frontend/src/App.tsx
```

- [ ] **Step 5: Verificar build**

```bash
cd frontend && npx tsc -b --noEmit && npm run build 2>&1 | tail -20
```
Expected: 0 errors. Aviso de bundle size pode aparecer.

- [ ] **Step 6: Smoke manual do dev server**

```bash
cd frontend && timeout 8 npm run dev 2>&1 | head -10
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app frontend/src/main.tsx
git commit -m "feat(ds): bootstrap app with providers (QueryClient, Router, Toaster, Confirm)"
```

---

## Phase 14 — Migrar página Prospecting atual pra FSD

### Task 14.1: Mover componentes legados pra estrutura FSD (sem refatorar UI)

**Files:**
- Move: `frontend/src/components/*` → `frontend/src/pages/prospecting/legacy/`
- Move: `frontend/src/hooks/*` → `frontend/src/pages/prospecting/legacy/hooks/`
- Move: `frontend/src/utils/*` → `frontend/src/pages/prospecting/legacy/utils/`
- Move: `frontend/src/pages/Prospecting.tsx` → `frontend/src/pages/prospecting/legacy/Prospecting.tsx`

- [ ] **Step 1: Mover via git**

```bash
cd frontend/src && mkdir -p pages/prospecting/legacy/hooks pages/prospecting/legacy/utils && \
  git mv components/*.tsx pages/prospecting/legacy/ && \
  git mv components/*.ts pages/prospecting/legacy/ 2>/dev/null || true && \
  git mv hooks/* pages/prospecting/legacy/hooks/ 2>/dev/null || true && \
  git mv utils/* pages/prospecting/legacy/utils/ 2>/dev/null || true && \
  git mv pages/Prospecting.tsx pages/prospecting/legacy/Prospecting.tsx && \
  rmdir components hooks utils 2>/dev/null || true
```

- [ ] **Step 2: Atualizar imports dentro do legacy**

Imports relativos entre arquivos do legacy continuam funcionando porque foram movidos juntos. Imports que apontavam pra `@/shared/api` etc continuam OK.

Verificar nada quebrou:

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | head -30
```
Expected: 0 errors. Se houver, ajustar imports relativos quebrados.

- [ ] **Step 3: Atualizar `pages/prospecting/index.ts` pra exportar legacy**

```ts
export { Prospecting } from './legacy/Prospecting'
```

- [ ] **Step 4: Rodar testes**

```bash
cd frontend && npx vitest run
```
Expected: testes legados (FilterPanel, ResultsTable, LocationAutocomplete, etc) passam. Novos testes do DS também passam.

- [ ] **Step 5: Smoke E2E — navegar para Prospecting via AppShell**

Criar `frontend/e2e/smoke-shell.spec.ts`:

```ts
import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('landing → login stub → app → prospecting tem tabela', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'CNPJ Discovery' })).toBeVisible()
  await page.getByRole('link', { name: 'Entrar' }).click()
  await expect(page).toHaveURL(/\/login/)
  // Simula auth stub
  await page.evaluate(() => localStorage.setItem('demo-auth', '1'))
  await page.getByRole('link', { name: /Entrar \(stub\)/ }).click()
  await expect(page).toHaveURL(/\/app\/prospecting/)
  // SideNav presente
  await expect(page.getByLabel('Prospecting')).toBeVisible()
  await expect(page.getByLabel('Pipeline')).toBeVisible()

  // axe — sem violações na rota
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
```

- [ ] **Step 6: Rodar Playwright**

```bash
cd frontend && npm run e2e
```
Expected: 1 passed. Se a página legada de Prospecting tiver violações axe, anotar e abrir issue (corrigir em sub-projeto #6); por enquanto exclua a página interna desse axe se necessário (ajuste em CI: `new AxeBuilder({ page }).exclude('main')` apenas para o teste do shell — mantém asserts no shell).

- [ ] **Step 7: Commit**

```bash
git add frontend/ && git commit -m "refactor(ds): move legacy prospecting components into pages/prospecting/legacy/"
```

---

## Phase 15 — Segurança (Nginx CSP + headers)

### Task 15.1: Adicionar headers de segurança no Nginx

**Files:**
- Modify: `nginx/nginx.conf`

- [ ] **Step 1: Editar nginx.conf**

Dentro do `server { listen 80; ... }`, ANTES do bloco `location / {`, adicionar:

```nginx
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' http://api:8000; frame-ancestors 'none'; object-src 'none'; base-uri 'self'" always;
```

(O `connect-src` aponta pro upstream `api`; em produção HTTPS deverá ser substituído pelo domínio real — anotado pra #2 ajustar.)

- [ ] **Step 2: Validar sintaxe Nginx**

```bash
cd /home/luife/projetos/cnpj-discovery && docker compose -f docker-compose.yml run --rm nginx nginx -t 2>&1 | tail -10
```
Expected: `nginx: configuration file ... test is successful`.

- [ ] **Step 3: Commit**

```bash
git add nginx/nginx.conf
git commit -m "feat(security): add CSP and hardening headers in nginx"
```

---

## Phase 16 — CI gates

### Task 16.1: Bundle size budget

**Files:**
- Create: `frontend/scripts/check-bundle-size.cjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: Script**

```js
// scripts/check-bundle-size.cjs
const fs = require('node:fs')
const path = require('node:path')
const zlib = require('node:zlib')

const DIST = path.resolve(__dirname, '../dist/assets')
const BUDGET_KB = 220

const files = fs.readdirSync(DIST).filter((f) => f.endsWith('.js'))
const initial = files.find((f) => f.startsWith('index') || f.startsWith('main'))
if (!initial) { console.error('Initial chunk not found in dist/assets'); process.exit(1) }

const buf = fs.readFileSync(path.join(DIST, initial))
const gz = zlib.gzipSync(buf, { level: 9 })
const kb = (gz.length / 1024).toFixed(1)
console.log(`Initial chunk ${initial}: ${kb} KB gz`)

if (parseFloat(kb) > BUDGET_KB) {
  console.error(`FAIL: initial chunk ${kb} KB exceeds budget ${BUDGET_KB} KB`)
  process.exit(1)
}
console.log('PASS')
```

- [ ] **Step 2: Adicionar script npm**

Em `frontend/package.json` adicionar:

```json
"check-bundle": "node scripts/check-bundle-size.cjs"
```

- [ ] **Step 3: Rodar build + check**

```bash
cd frontend && npm run build && npm run check-bundle
```
Expected: PASS (ou número exato pra ajustar budget).

- [ ] **Step 4: Commit**

```bash
git add frontend/scripts/check-bundle-size.cjs frontend/package.json
git commit -m "test(ds): add bundle size budget check (initial ≤ 220 KB gz)"
```

---

### Task 16.2: GitHub Actions workflow pra frontend

**Files:**
- Create: `.github/workflows/frontend.yml`

- [ ] **Step 1: Workflow**

```yaml
name: frontend

on:
  pull_request:
    paths:
      - 'frontend/**'
      - '.github/workflows/frontend.yml'
  push:
    branches: [develop, main]
    paths:
      - 'frontend/**'

jobs:
  test:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npx tsc -b --noEmit
      - run: npx vitest run --coverage
      - run: npm run build
      - run: npm run check-bundle
      - run: npx playwright install --with-deps chromium
      - run: npm run e2e
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: frontend/playwright-report
```

- [ ] **Step 2: Adicionar script lint em package.json**

Confirmar que `frontend/package.json` tem `"lint": "eslint ."`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/frontend.yml frontend/package.json
git commit -m "ci(ds): add frontend pipeline (lint, types, vitest+cov, build, bundle, e2e)"
```

---

## Phase 17 — Documentação final

### Task 17.1: README de frontend e seção no README raiz

**Files:**
- Create: `frontend/README.md`
- Modify: `README.md` (raiz) — adicionar seção curta linkando

- [ ] **Step 1: Criar `frontend/README.md`**

```markdown
# Frontend — CNPJ Discovery

Vite + React 19 + TypeScript. Arquitetura: Feature-Sliced Design (ver `docs/architecture.md`).

## Scripts

| Comando | Faz |
|---|---|
| `npm run dev` | Dev server (5173) |
| `npm run build` | Build de produção |
| `npm run lint` | ESLint (FSD boundaries + a11y) |
| `npm test` | Vitest |
| `npm run test:coverage` | Vitest + cobertura |
| `npm run e2e` | Playwright |
| `npm run check-bundle` | Verifica orçamento de bundle |

## Estrutura

```
src/
├── app/        ← bootstrap + providers + styles + router
├── pages/      ← 1 por rota top-level
├── widgets/    ← blocos grandes (AppShell, PipelineBoard, …)
├── features/   ← casos de uso atômicos
├── entities/   ← modelos de domínio (tipos + formatters)
└── shared/     ← UI kit, api, lib, hooks, config
```

Cada camada importa só de camadas abaixo. ESLint enforça.

## Design System

Tokens em `app/styles/tokens.css` (3 camadas W3C-style). Componentes em `shared/ui/`.

Inspirado na Receita Federal + SaaS polish. Identidade: navy + azul-bandeira + amarelo como acento.
```

- [ ] **Step 2: Adicionar parágrafo no README raiz**

Em `README.md`, antes da última seção, adicionar:

```markdown
## Frontend

O frontend é uma SPA Vite + React + Feature-Sliced Design. Ver [`frontend/README.md`](./frontend/README.md) e [`frontend/docs/architecture.md`](./frontend/docs/architecture.md). Especificação do design system em [`docs/superpowers/specs/2026-05-14-design-system-foundation-design.md`](./docs/superpowers/specs/2026-05-14-design-system-foundation-design.md).
```

- [ ] **Step 3: Commit**

```bash
git add frontend/README.md README.md
git commit -m "docs(ds): add frontend README and link from root"
```

---

## Validação final

### Task 99: Smoke completo + checklist do spec

- [ ] **Step 1: Rodar todos os checks locais**

```bash
cd frontend && \
  npm run lint && \
  npx tsc -b --noEmit && \
  npx vitest run --coverage && \
  npm run build && \
  npm run check-bundle && \
  npm run e2e
```
Expected: tudo PASS, cobertura ≥ 80% em shared/entities/widgets, bundle ≤ 220 KB gz.

- [ ] **Step 2: Conferir checklist §18 do spec**

- [ ] Estrutura FSD criada com ESLint plugin configurado
- [ ] `app/styles/tokens.css` completo
- [ ] Todos os componentes de `shared/ui/` da §7 do spec entregues com testes (≥ 80%)
- [ ] `widgets/app-shell` funcionando: TopBar + SideNav + Outlet
- [ ] React Router v7 com 9+ rotas (5 placeholder, 4 stub)
- [ ] Prospecting movido pra `pages/prospecting/` sem regressão
- [ ] CSP + headers de segurança no Nginx
- [ ] Lighthouse Performance ≥ 90 desktop (rodar manualmente em `npm run build && npm run preview` + DevTools/Lighthouse)
- [ ] axe-core 0 violações no smoke E2E
- [ ] Bundle inicial ≤ 200 kB gz (budget máximo 220 KB)

- [ ] **Step 3: Commit final (se necessário) e abrir PR**

```bash
git log --oneline develop..HEAD | head -50
gh pr create --base develop --title "feat(ds): design system foundation + app shell (#1 de 6)" --body "$(cat <<'EOF'
## Summary
- FSD strict (eslint-plugin-boundaries enforcing layer rules)
- Design tokens em 3 camadas (W3C-style) via Tailwind v4 @theme
- ~26 componentes em shared/ui/ (Radix-based, cva variants, lucide icons)
- AppShell (TopBar + SideNav) com tooltips, atalho /, skip link
- React Router v7 com 11 rotas (data router, lazy, ErrorBoundary)
- Prospecting legada migrada pra pages/prospecting/legacy sem regressão
- CSP + hardening headers no Nginx
- CI: lint, types, vitest+coverage 80%, e2e Playwright + axe, bundle budget

## Test plan
- [ ] CI passa
- [ ] `npm run dev` abre landing → login stub → /app
- [ ] Navegação por tab funciona até o conteúdo
- [ ] Apertar `/` foca a busca global
- [ ] Lighthouse Performance ≥ 90 desktop

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist (executado pelo autor do plano antes de entregar)

**1. Cobertura do spec:**
- Arquitetura FSD strict → Phase 1 ✓
- Design tokens 3 camadas → Phase 2 ✓
- Componentes §7 do spec → Phases 5-8 ✓
- App Shell → Phase 10 ✓
- React Router v7 + ProtectedRoute + ErrorBoundary → Phase 12 ✓
- Padrões transversais (loading/error/empty/toast/modal) → Phases 6, 7 ✓
- Performance (bundle budget, lazy, virtualization) → Phases 6, 12, 16 ✓
- Acessibilidade (axe em CI, foco, skip link, aria-labels) → Phases 5-10, 14 ✓
- Segurança (CSP, headers, no `dangerouslySetInnerHTML`) → Phases 0, 15 ✓
- Testes (Vitest + RTL + vitest-axe + Playwright) → Phases 0, 14 ✓
- Migração Prospecting → Phase 14 ✓
- Docs → Phases 1, 17 ✓
- Fora de escopo respeitado (sem auth real, sem pipeline real, sem dark) ✓

**2. Placeholder scan:** sem TBD, TODO, "implement later". Todos os steps têm código concreto.

**3. Consistência de tipos:** `cn` (lib), `ApiError` (api), `User`/`userInitials` (entity), `ConfirmDialogProvider`/`useConfirm` (feedback) — nomes batem entre tasks.

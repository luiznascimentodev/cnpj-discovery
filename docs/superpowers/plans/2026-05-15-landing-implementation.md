# Landing pública — plano de implementação

**Data:** 2026-05-15
**Spec:** `docs/superpowers/specs/2026-05-15-landing-design.md`
**Branch:** `feature/landing-public` (a criar a partir de `main`)

---

## Estratégia

Single-PR, pequeno. Landing é estática e isolada — não toca nenhum outro slice. Sem risco de regressão fora de `pages/landing/`, `frontend/index.html` e `frontend/public/`.

Ordem das fases tenta deixar a página utilizável o quanto antes (com testes verde após cada fase) para qualquer interrupção deixar artefato funcional.

---

## L1 — Estrutura de sections (Marketing header/footer + composer da página)

**Output**
- `pages/landing/ui/sections/MarketingHeader.tsx`
- `pages/landing/ui/sections/MarketingFooter.tsx`
- `pages/landing/ui/LandingPage.tsx` re-organizado como composer das sections
- Atualizar `pages/landing/index.ts` (sem mudar API pública)

**Critério**
- Página visualmente equivalente ao stub atual mas com header/footer extraídos
- Testes existentes (se houver) ainda passam
- `npm run lint && npm run test -- pages/landing` verde

## L2 — Hero refinado + Mockup CSS

**Output**
- `pages/landing/ui/sections/Hero.tsx` (extrai a seção do composer)
- `pages/landing/ui/mockups/ProductMockup.tsx` — janela com header "dots", barra de filtros mock e tabela de 5 linhas
- Hero passa a ter 2 colunas em ≥1024px: texto à esquerda, mockup à direita
- Mockup com `aria-hidden="true"` e dados fictícios

**Critério**
- Visual verificado no dev server (`npm run dev`)
- `aria-hidden` no mockup confirmado em DOM
- vitest-axe sem violação na LandingPage

## L3 — Features section (3 colunas)

**Output**
- `pages/landing/ui/sections/Features.tsx`
- 3 cards em grid responsivo (grid-cols-3 desktop, grid-cols-1 quando viewport < tablet — mesmo o mobile não sendo escopo, o fallback evita layout quebrado)
- Ícones do barrel `@/shared/ui/icons`: `Filter`, `KanbanSquare`, `RefreshCw` (verificar quais já estão exportados; se faltar, adicionar)

**Critério**
- Renderiza 3 `<article>` com h3 + descrição
- Snapshot RTL pass

## L4 — Closing CTA banner

**Output**
- `pages/landing/ui/sections/ClosingCTA.tsx`
- Banner full-width com bg `--color-bg-inverse` (navy), texto branco, CTA primário "Criar conta grátis" → `/registro`

**Critério**
- CTA link verificado no teste (`getByRole('link', { name: /criar conta/i })` com `href="/registro"`)

## L5 — SEO: meta tags + Open Graph + sitemap/robots

**Output**
- `frontend/index.html` com `<title>`, `<meta description>`, OG completo, canonical, twitter card
- `frontend/public/robots.txt`
- `frontend/public/sitemap.xml`
- Placeholder `frontend/public/og-card.png` (imagem transparente 1200×630, TODO comentado para o user trocar depois)

**Critério**
- `curl http://localhost:5173/robots.txt` retorna 200 no dev server
- View-source mostra todas meta tags
- Build (`npm run build`) copia os arquivos para `dist/`

## L6 — Testes + axe + bundle gate

**Output**
- `pages/landing/ui/LandingPage.test.tsx`:
  - asserções de presença das sections, links dos CTAs, axe zero
- Garantir que o bundle gate existente (Phase 16 do DS) não falhe
- Rodar `npm run test:coverage` e checar cobertura do slice `pages/landing`

**Critério**
- `npm run lint && npm run test:coverage && npm run build` tudo verde
- Cobertura do slice ≥ 80%

## L7 — Smoke E2E (opcional, se Playwright estiver setup)

**Output**
- Verificar se há Playwright config no projeto; se sim, adicionar `e2e/landing.spec.ts` cobrindo: load `/`, click "Começar gratuitamente", verificar redirect para `/registro`
- Se não houver Playwright config ainda, **pular esta fase** (fica para uma fase futura de E2E setup global)

**Critério**
- Test passa em CI ou fase explicitamente skippada com nota

## L8 — Commit + PR

**Output**
- Branch: `feature/landing-public` a partir de `main`
- Commit único ou poucos commits semânticos
- PR título: `feat(landing): public landing page (sub-project #3)`
- PR body: link pro spec, screenshot do hero, checklist do spec §10

**Critério**
- CI verde
- Lighthouse Performance ≥ 95 no preview (manual se não houver Lighthouse CI)
- Roadmap memory atualizada para #3 ✅

---

## Estimativa

~3-4h de trabalho ininterrupto. Sem dependência externa, sem coordenação com backend, sem mudanças em DS.

## Riscos

| Risco | Mitigação |
|---|---|
| Mockup CSS ficar feio sem screenshot real | Iterar com user antes de finalizar L2; se ficar ruim, fallback para gradient sem mockup |
| Domínio placeholder em sitemap/canonical | Documentar TODO + variável de ambiente futura `VITE_PUBLIC_URL` |
| Bundle estourar com novos imports de ícones | Curated barrel já garante tree-shake; gate de bundle vai falhar se passar do budget |

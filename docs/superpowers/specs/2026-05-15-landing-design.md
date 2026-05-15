# Landing pública — design

**Data:** 2026-05-15
**Sub-projeto #3 de 6**
**Depende de:** #1 (DS foundation) ✅, #2 (Auth) ✅
**Status:** spec aprovado pelo usuário (decisões fechadas via AskUserQuestion)

---

## 1. Objetivo

Transformar `pages/landing/` (atual stub hero-only) em uma landing pública enxuta orientada a conversão para signup. Sem pricing, sem screenshots reais — só copy + mockup CSS + CTA.

**Sucesso:**
- Visitante anônimo cai em `/`, entende em <10s o que o produto faz e clica em "Começar grátis" → `/registro`.
- Indexável no Google (sitemap, robots, meta tags).
- Compartilhável no LinkedIn/WhatsApp com OG card decente.
- Lighthouse Performance ≥ 95 desktop (página é estática, sem JS pesado).

## 2. Decisões fechadas

| Tema | Decisão |
|---|---|
| Escopo | Enxuta single-scroll: Hero + 3 features inline + CTA final + Footer |
| Pricing | Sem pricing nesta fase |
| Visual hero | Mockup estilizado em CSS (não screenshot) |
| SEO | Meta tags + Open Graph + sitemap.xml + robots.txt |
| Analytics | Não nesta fase |
| Auth wiring | "Entrar" → `/login`, "Começar grátis" / "Criar conta" → `/registro` (ambos já funcionam pós-#2) |
| Idioma | pt-BR apenas |
| Devices | Desktop-first + tablet (≥1024px). Mobile fica para uma fase posterior. |

## 3. Estrutura (sections)

```
┌──────────────────────────────────────────────┐
│ Header (sticky, sutil): logo · Entrar · Criar│
├──────────────────────────────────────────────┤
│ Hero                                          │
│   ─ Pill: "Dados oficiais da Receita Federal"│
│   ─ H1 (2 linhas)                            │
│   ─ Subhead (1 parágrafo)                    │
│   ─ CTAs primário + secundário               │
│   ─ Mockup CSS à direita (tabela+filtros)    │
├──────────────────────────────────────────────┤
│ Features (3 colunas inline)                  │
│   icon · title · description                 │
├──────────────────────────────────────────────┤
│ CTA final (banner de fechamento)             │
│   título + 1 CTA primário                    │
├──────────────────────────────────────────────┤
│ Footer (compacto)                            │
│   logo · links institucionais · ano · social │
└──────────────────────────────────────────────┘
```

### 3.1 Copy proposto (provisório, refinar na implementação)

**Hero**
- Pill: "Dados oficiais da Receita Federal"
- H1: "Prospecção B2B com a base completa do CNPJ brasileiro."
- Sub: "Filtre, segmente e organize empresas em pipeline com a precisão dos dados oficiais — sem planilhas, sem retrabalho."
- CTAs: `[Começar gratuitamente]` (primary) · `[Já tenho conta]` (secondary)

**Features (3)**
1. **Filtros precisos** — CNAE, porte, UF, bairro, capital social, situação cadastral. Combine como quiser.
2. **Pipeline de prospecção** — organize empresas em estágios, anote contatos e nunca perca um lead.
3. **Dados sempre atualizados** — base sincronizada com a Receita Federal a cada release oficial.

**CTA final**
- Título: "Pronto para parar de prospectar no escuro?"
- CTA: `[Criar conta grátis]`

**Footer**
- Esquerda: "CNPJ Discovery · © 2026"
- Direita: links "Termos" · "Privacidade" · "Contato" (placeholders nesta fase — sem páginas reais ainda; ESLint allow para anchors com `href="#"` ou linkar pra `mailto:`)

### 3.2 Mockup CSS do hero

Renderização HTML/CSS de uma "janela" do produto:
- Container com `border-radius`, `shadow-lg`, `border` e header tipo "macOS dots"
- Top: barra de filtros com 3 pills (`CNAE 62.04-0`, `SP`, `Capital > 100k`)
- Body: tabela com header e 5 linhas mock (CNPJ, Razão social, UF, Porte)
- Não é interativo. Apenas decorativo. `aria-hidden="true"` para AT skipar.
- Dados completamente fictícios (`Acme S.A.`, `0X.XXX.XXX/0001-XX`).

## 4. Arquitetura

### 4.1 Slices envolvidos (FSD)

| Camada | Path | Conteúdo |
|---|---|---|
| pages | `pages/landing/ui/LandingPage.tsx` | composição das sections |
| pages | `pages/landing/ui/sections/Hero.tsx` | hero + mockup |
| pages | `pages/landing/ui/sections/Features.tsx` | 3 colunas |
| pages | `pages/landing/ui/sections/ClosingCTA.tsx` | banner final |
| pages | `pages/landing/ui/sections/MarketingHeader.tsx` | header público (não usa AppShell) |
| pages | `pages/landing/ui/sections/MarketingFooter.tsx` | footer público |
| pages | `pages/landing/ui/mockups/ProductMockup.tsx` | mockup CSS reusável |

Tudo dentro do slice `pages/landing/` (não vai pra `widgets/` porque é específico de uma página).

### 4.2 Regra de negócio

Nenhuma. Landing é 100% estática — sem fetch, sem state, sem condicionais de domínio. Atende ao princípio "regra de negócio no backend, front só exibe".

### 4.3 Rotas

Já configurada em `app/router.tsx`: `/` → `LandingPage` (público, lazy). Nada a mudar.

## 5. SEO

### 5.1 Meta tags (em `index.html` ou via `react-helmet-async`)

```html
<title>CNPJ Discovery — Prospecção B2B com dados oficiais da Receita Federal</title>
<meta name="description" content="Plataforma de prospecção B2B com a base completa de CNPJs do Brasil. Filtros por CNAE, UF, porte e capital social. Organize leads em pipeline.">
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://cnpj-discovery.com.br/">

<meta property="og:type" content="website">
<meta property="og:title" content="CNPJ Discovery — Prospecção B2B brasileira">
<meta property="og:description" content="...">
<meta property="og:image" content="/og-card.png">
<meta property="og:url" content="https://cnpj-discovery.com.br/">

<meta name="twitter:card" content="summary_large_image">
```

Implementação: hardcoded direto em `frontend/index.html` (única página pública nesta fase, então não precisa de helmet). Quando #6 adicionar mais páginas públicas, refatorar pra react-helmet-async.

### 5.2 OG image

`frontend/public/og-card.png` — 1200×630 px. Gerar manualmente uma vez (Figma/Canva) ou via script Playwright que screenshote uma versão `/og-preview` da landing.

**Decisão:** fora de escopo gerar a imagem nesta fase. Placeholder 1200×630 transparente + TODO comentado. Usuário entrega o asset final depois.

### 5.3 sitemap.xml e robots.txt

`frontend/public/robots.txt`:
```
User-agent: *
Allow: /
Disallow: /app/
Sitemap: https://cnpj-discovery.com.br/sitemap.xml
```

`frontend/public/sitemap.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://cnpj-discovery.com.br/</loc>
    <changefreq>monthly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
```

Domínio é placeholder; quando o usuário tiver o domínio real, substitui em build-time via `VITE_PUBLIC_URL` ou commit manual.

## 6. Performance

- Sem JS extra além do bundle existente do React Router + DS.
- Hero mockup é HTML/CSS puro — zero custo de runtime.
- Fonts já carregadas pela landing existente.
- Imagem OG não é renderizada na página, só no `<meta>` (carregada pelas crawlers).
- Lighthouse desktop target: **≥ 95** (sem screenshot real significa pouco LCP cost).

## 7. Acessibilidade

- Header marketing tem `<header>` + `<nav aria-label="Acesso">`
- Hero usa `<section aria-labelledby="hero-title">` com `<h1 id="hero-title">`
- Mockup tem `aria-hidden="true"` para screen readers pularem
- Features section: cada feature card é `<article>` com `<h3>`
- Skip-link "Pular para conteúdo principal" no topo do `<body>` apontando para `<main>` (já existia no AppShell mas landing não usa AppShell — adicionar manualmente)
- Contraste: já garantido pelos tokens semantic do DS
- Foco visível: já herdado dos primitives

## 8. Testes

- `vitest-axe` em `LandingPage` (zero violações)
- RTL: assert que ambos CTAs estão visíveis e linkam para `/registro` e `/login`
- E2E (Playwright smoke): navegar `/` → clicar "Começar gratuitamente" → cair em `/registro` com form visível

Cobertura alvo do slice: 80%+ (linha com o resto do `shared/ui/`).

## 9. Fora de escopo

- ❌ Mobile (≤1023px) — fase posterior
- ❌ i18n (só pt-BR)
- ❌ Pricing real (planos comerciais ainda indefinidos)
- ❌ Screenshots/vídeos reais do produto
- ❌ Depoimentos/social proof real (não temos clientes ainda para citar)
- ❌ Analytics (não nesta fase)
- ❌ Páginas institucionais (Termos, Privacidade, Contato) — links são placeholders
- ❌ Geração da OG image (placeholder; user entrega depois)

## 10. Sucesso = checklist

- [ ] `LandingPage` renderiza Hero + Features + ClosingCTA + Footer sem regressão visual
- [ ] Mockup CSS renderiza com dados fictícios e `aria-hidden`
- [ ] Meta tags + OG + canonical no `index.html`
- [ ] `robots.txt` e `sitemap.xml` em `public/`
- [ ] Testes RTL + axe passando
- [ ] Lighthouse Performance ≥ 95 desktop
- [ ] Bundle inicial não cresce mais que 10kB gz (verificado pelo gate existente)

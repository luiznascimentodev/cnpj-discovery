# Frontend Architecture — Feature-Sliced Design

Este frontend segue **Feature-Sliced Design v2** strict. Spec oficial: https://feature-sliced.design

## Camadas (do mais alto pro mais baixo)

| Camada | Pode importar de | Responsabilidade |
|---|---|---|
| `app/` | tudo | Bootstrap: providers, router, styles globais |
| `pages/` | widgets, features, entities, shared | 1 page = 1 rota top-level |
| `widgets/` | features, entities, shared | Blocos grandes compostos (ex.: AppShell, PipelineBoard) |
| `features/` | entities, shared | Casos de uso atômicos do usuário (ex.: add-to-pipeline) |
| `entities/` | shared | Modelos de domínio puros (tipos + formatters), sem regra de negócio |
| `shared/` | (nada) | Reutilizável e sem domínio: UI kit, lib, hooks, api client |

## Regras (enforçadas via ESLint)

1. **Camada só importa de camadas abaixo.** `eslint-plugin-boundaries/element-types` quebra build se violar.
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

## Aliases de import

| Alias | Aponta para |
|---|---|
| `@/app/*` | `src/app/*` |
| `@/pages/*` | `src/pages/*` |
| `@/widgets/*` | `src/widgets/*` |
| `@/features/*` | `src/features/*` |
| `@/entities/*` | `src/entities/*` |
| `@/shared/*` | `src/shared/*` |

## Migração legada

A página atual de Prospecting (com seus componentes em `src/components/`, hooks em `src/hooks/` e utils em `src/utils/`) será movida para `src/pages/prospecting/legacy/` no Phase 14 do plano de implementação. Refatoração completa pro novo Design System fica para o sub-projeto #6.

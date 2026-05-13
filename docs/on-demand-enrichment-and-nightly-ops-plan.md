# Plano de Enriquecimento Sob Demanda e Operacao Noturna

Objetivo: transformar o enrichment em um fluxo sob demanda, barato e previsivel
para VPS, mantendo um worker lento de preenchimento continuo e criando jobs
noturnos para verificar atualizacoes da base publica da Receita Federal.

Este plano assume a base ativa-only ja adotada no ETL: somente CNPJs com
`estabelecimentos.situacao_cadastral = 2` entram no banco principal e somente
esses CNPJs podem virar alvo de enrichment.

## Decisao de arquitetura

O enrichment deixa de tentar cobrir a base inteira rapidamente. O produto passa
a operar em tres camadas:

1. Cache global de enrichment: todo contato descoberto com evidencia fica em
   `paid_enrichment`, reutilizavel por qualquer cliente autorizado.
2. Fila sob demanda: quando o usuario filtra ou seleciona CNPJs, o sistema cria
   um job priorizado para aquele lote.
3. Worker lento continuo: quando nao ha demanda de usuario, um unico worker
   trabalha em baixa velocidade para aumentar a cobertura sem pressionar CPU,
   memoria, disco, rede ou os sites consultados.

Regra principal: demanda do usuario tem prioridade absoluta sobre varredura
background. O background existe para aproveitar ocioso, nao para competir com
uso real.

## Fontes publicas do ETL

As fontes devem ser tratadas como manifestos de arquivos, nao como "baixar de
qualquer lugar". A rotina noturna compara nome, tamanho, `Last-Modified`, `ETag`
quando existir, mes de referencia e conjunto esperado de arquivos.

Fontes aceitas:

- `rf_webdav`: fonte atual do projeto, via `RF_WEBDAV_BASE` e
  `RF_SHARE_TOKEN`. Deve continuar sendo suportada porque ja funciona no ETL.
- `rf_http_index`: indice HTTP oficial:
  `https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/`.
  Em 2026-05-13, este indice expunha pastas mensais e arquivos grandes no
  mesmo dominio da Receita. O job nao deve assumir que a pasta mais nova sera o
  mes corrente; ele deve usar o snapshot efetivamente publicado.
- `dados_gov_catalog`: catalogo oficial:
  `https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj`.
  Deve ser usado como fonte de metadados/checagem e link de descoberta, nao como
  unico canal de download.
- `serpro_cnpj_api`: somente validacao pontual opcional, nao bulk ETL. O servico
  e API paga/contratada e retorna dados em tempo real; ele pode ajudar a auditar
  divergencias em amostras pequenas, mas nao substitui dados abertos.

Fonte nao oficial ou mirror privado so entra com flag manual de emergencia,
registrando URL, hash, origem e motivo. O caminho padrao de producao deve ficar
em fontes oficiais.

## Regras de negocio do enrichment

- O usuario pode enriquecer CNPJs selecionados manualmente ou o resultado de um
  filtro salvo no momento da criacao do job.
- O backend sempre materializa a lista de CNPJs no servidor. O frontend nao manda
  filtros soltos para o worker processar depois, porque os dados podem mudar.
- CNPJ inativo, baixado, inapto ou ausente da base ativa-only e marcado como
  `skipped_inactive` e nao consome credito.
- CNPJ com enrichment fresco e retornado imediatamente do cache e entra no job
  como `cache_hit`.
- CNPJ sem cache fresco vira item `pending`.
- Cache fresco: contato publicado nos ultimos 180 dias.
- Cache velho: entre 181 e 365 dias, mostrar com selo "desatualizado" e enfileirar
  refresh em baixa prioridade dentro do job.
- Cache expirado: acima de 365 dias, nao prometer qualidade; o item deve ser
  processado antes de aparecer como pronto.
- Resultado "sem contato publico encontrado" expira em 30 dias, porque ausencia
  de contato muda mais rapido que contato positivo.
- O mesmo CNPJ nao deve ter dois itens ativos para o mesmo usuario e mesma janela
  de cache. Duplicatas dentro do lote sao deduplicadas antes de gravar.
- Contato so e publicado quando tiver evidencia (`evidence_url`), tipo normalizado
  e score minimo. Dado RF puro pode aparecer como dado publico de cadastro, mas
  nao deve ser vendido como enrichment crawler.
- O usuario ve progresso parcial. Exportacao pode conter `ready`, `processing`,
  `no_public_contact`, `failed_retryable` e `skipped_inactive`.
- Cancelamento nao apaga contatos ja descobertos, apenas cancela itens ainda nao
  processados daquele job.

## Modelo de dados

Adicionar uma migration nova, por exemplo
`db/migrations/014_on_demand_enrichment.sql`.

Tabelas principais:

- `app_private.enrichment_jobs`
  - `id`, `account_id`, `created_by`, `source_type`
  - `filter_hash`, `filters_json`, `selection_count`
  - `status`: `draft`, `estimating`, `queued`, `running`, `completed`,
    `completed_with_errors`, `cancelled`, `failed`
  - `priority`, `plan_key`, `requested_count`, `accepted_count`
  - `cache_hit_count`, `skipped_count`, `failed_count`, `ready_count`
  - `cost_credits`, `created_at`, `started_at`, `completed_at`, `cancelled_at`
  - `last_error`, `idempotency_key`
- `app_private.enrichment_job_items`
  - `id`, `job_id`, `account_id`
  - `cnpj_basico`, `cnpj_ordem`, `cnpj_dv`
  - `status`: `pending`, `leased`, `cache_hit`, `enriched`,
    `no_public_contact`, `skipped_inactive`, `failed_retryable`,
    `failed_terminal`, `cancelled`
  - `priority`, `attempts`, `locked_by`, `locked_at`, `lease_expires_at`
  - `result_source`: `cache`, `fresh_crawl`, `rf_only`, `none`
  - `cache_fresh_until`, `last_error`, `created_at`, `updated_at`
- `app_private.enrichment_credit_ledger`
  - lancamento imutavel por job, com debito/estorno e motivo.
- `app_private.etl_dataset_snapshots`
  - `snapshot_key`, `source_name`, `source_url`, `status`, `discovered_at`,
    `selected_at`, `loaded_at`, `manifest_hash`, `file_count`,
    `total_size_bytes`, `last_modified_max`.
- `app_private.etl_dataset_files`
  - `snapshot_id`, `file_name`, `url`, `size_bytes`, `etag`,
    `last_modified`, `sha256` quando calculado.

Indices e constraints:

- Unique em `enrichment_jobs(account_id, idempotency_key)` quando informado.
- Unique em `enrichment_job_items(job_id, cnpj_basico, cnpj_ordem, cnpj_dv)`.
- Indice de claim:
  `(status, priority DESC, lease_expires_at, id)` para `pending`/`failed_retryable`.
- Indice de acompanhamento:
  `(account_id, created_at DESC)` em jobs.
- Constraints de status com `CHECK`, espelhadas por testes.

## API backend

Novos endpoints na API publica, com entitlement server-side:

- `POST /v1/paid/enrichment/estimate`
  - Entrada: `cnpjs` ou `filters`.
  - Saida: total elegivel, cache hits, novos, ignorados, custo estimado,
    tempo estimado por faixa.
- `POST /v1/paid/enrichment/jobs`
  - Cria o job materializado. Exige idempotency key para evitar duplo clique.
- `GET /v1/paid/enrichment/jobs`
  - Lista jobs do usuario/conta.
- `GET /v1/paid/enrichment/jobs/{job_id}`
  - Progresso agregado e proximos passos.
- `GET /v1/paid/enrichment/jobs/{job_id}/items`
  - Paginacao dos itens e status por CNPJ.
- `POST /v1/paid/enrichment/jobs/{job_id}/cancel`
  - Cancela pendentes e leases ainda nao iniciadas.
- `GET /v1/paid/enrichment/jobs/{job_id}/export.csv`
  - Exporta o estado atual com contatos ja publicados.

Regras de API:

- Todo endpoint deve validar `account_id`, plano, feature `bulk_enrichment` e
  limite por lote antes de tocar na fila.
- O endpoint de criacao deve bloquear filtros que expandem acima do limite do
  plano sem confirmacao explicita.
- O estimate deve ser barato: usar query de contagem e amostra, nao abrir job.
- O worker nao deve confiar no payload do frontend. Ele sempre le de
  `enrichment_job_items`.
- A API interna do servico de enrichment continua em `/v1/enrichment/...`; a API
  publica de produto fica em `/v1/paid/enrichment/...`.

## Workers

Implementar comandos novos no `enrichment/cli.py`.

`demand-worker`:

- Reivindica primeiro itens `pending` de jobs de usuario.
- Reusa cache fresco sem crawler.
- Para miss/stale, chama o pipeline existente de discovery/crawler/resolver.
- Atualiza item e contadores do job em transacao curta.
- Concurrency inicial na KVM 4: 2 itens simultaneos, batch 20, intervalo 5s.

`trickle-worker`:

- Roda somente quando nao ha fila de demanda vencida.
- Usa prioridade baixa e lote pequeno.
- Concurrency inicial: 1 item, batch 5, intervalo 120s.
- Pausa automaticamente quando o load medio, conexoes Postgres ou uso de disco
  passam do limite configurado.

`release-stale-demand-leases`:

- Reabre itens `leased` cujo `lease_expires_at` passou.
- Roda a cada 5 minutos ou dentro do proprio worker.

Politica de prioridade:

- Demanda usuario: prioridade base 1000.
- Refresh de cache velho disparado por usuario: prioridade base 700.
- Retentativa por erro temporario: prioridade base reduzida por backoff.
- Trickle: prioridade base 10.
- Dentro da mesma prioridade, alternar contas para evitar que um cliente grande
  monopolize a VPS.

## Jobs noturnos

Usar cron do host na VPS para agendamento. Cron e mais simples de auditar que
um scheduler dentro do container, e o ETL ja roda como comando isolado.

Comandos a implementar no ETL:

- `python main.py check-public-data`
  - Consulta `rf_webdav`, `rf_http_index` e `dados_gov_catalog`.
  - Gera manifesto normalizado por fonte.
  - Compara contra `etl_dataset_snapshots`.
  - Marca `pending_load` se houver snapshot novo e valido.
- `python main.py refresh-active-only-if-updated`
  - Pega o snapshot `pending_load` mais recente.
  - Usa advisory lock para impedir execucao dupla.
  - Valida espaco livre antes de baixar.
  - Pausa trickle worker.
  - Executa full-load ativa-only em staging ou em janela de manutencao.
  - Reindexa/analyze.
  - Valida que nao existe `situacao_cadastral IS DISTINCT FROM 2`.
  - Marca snapshot como `loaded` somente depois das validacoes.

Cron sugerido em America/Sao_Paulo:

```cron
10 03 * * * cd /opt/cnpj-discovery && docker compose --profile etl run --rm etl python main.py check-public-data
30 03 * * * cd /opt/cnpj-discovery && docker compose --profile etl run --rm etl python main.py refresh-active-only-if-updated
```

O release de leases vencidas deve rodar dentro do `demand-worker` a cada 300s.
Se o worker estiver desligado, um cron opcional pode executar o comando por
`docker compose exec -T enrichment python cli.py release-stale-demand-leases`.

Servicos permanentes sugeridos:

```yaml
enrichment-demand-worker:
  command: ["python", "cli.py", "demand-worker", "--batch-size", "20", "--concurrency", "2", "--interval", "5"]
  restart: unless-stopped

enrichment-trickle-worker:
  command: ["python", "cli.py", "trickle-worker", "--batch-size", "5", "--concurrency", "1", "--interval", "120"]
  restart: unless-stopped
```

Durante o full-load noturno, o `trickle-worker` deve ficar pausado. O
`demand-worker` pode continuar com concurrency 1 ou entrar em modo degradado,
dependendo do consumo real medido na VPS.

## Perfil inicial para KVM 4

Comecar conservador e aumentar depois de medir:

- `ENRICHMENT_DEMAND_CONCURRENCY=2`
- `ENRICHMENT_DEMAND_BATCH=20`
- `ENRICHMENT_TRICKLE_CONCURRENCY=1`
- `ENRICHMENT_TRICKLE_BATCH=5`
- `ENRICHMENT_TRICKLE_INTERVAL=120`
- `ETL_AUTO_LOAD_PUBLIC_DATA=false` no primeiro deploy, para o job apenas marcar
  snapshot novo como `pending_load`.
- Depois de um refresh manual bem-sucedido na VPS, liberar
  `ETL_AUTO_LOAD_PUBLIC_DATA=true`.
- `ETL_MIN_FREE_GB=70` antes de baixar/carregar snapshot novo.
- `ETL_KEEP_ZIPS_AFTER_LOAD=false`.

## Frontend e UX

O frontend vira uma bancada operacional de prospeccao, nao uma tela de busca
solta.

Mudancas em `Prospecting.tsx`:

- Estado de selecao de CNPJs por pagina e por filtro atual.
- Barra de acoes fixa sobre a tabela com:
  - quantidade selecionada;
  - `Estimar enrichment`;
  - `Enriquecer selecionados`;
  - `Exportar CSV`;
  - `Limpar selecao`.
- Quando o usuario escolhe "todos do filtro", o frontend mostra isso
  explicitamente e chama estimate no backend antes de criar job.

Mudancas em `ResultsTable.tsx`:

- Checkbox por linha e checkbox no cabecalho.
- Coluna de status de enrichment:
  - `Pronto`;
  - `Processando`;
  - `Sem contato`;
  - `Desatualizado`;
  - `Nao solicitado`.
- Badges pequenos, legiveis e consistentes.
- Row click continua abrindo detalhe, mas checkbox nao pode disparar detalhe.

Novo fluxo de job:

- Modal/drawer de estimate:
  - total elegivel;
  - cache hits;
  - novos que vao para crawler;
  - custo/creditos;
  - tempo estimado;
  - limite do plano;
  - confirmacao.
- Drawer "Jobs":
  - lista de jobs recentes;
  - progresso;
  - parcial pronto;
  - cancelar;
  - exportar enriquecidos.
- Detalhe da empresa:
  - contatos publicados;
  - evidencia;
  - data de coleta;
  - botao "Atualizar enrichment" quando stale.

Melhorias visuais:

- Interface compacta e utilitaria, adequada a ferramenta B2B.
- Menos cards decorativos; mais densidade organizada.
- Filtros agrupados em secoes recolhiveis.
- Toolbar com icones `lucide-react`.
- Estados vazios e erros objetivos.
- Tabela responsiva: no mobile, selecao e acoes ficam em uma barra inferior.

## Cobertura de testes

Meta: 100% de cobertura para codigo proprio em API, ETL, enrichment e frontend.
Qualquer excecao precisa ser explicita, pequena e justificada no arquivo de
configuracao de cobertura. Regra de negocio nao pode ficar fora de teste.

Backend API:

- Testes de schema e validacao de entrada.
- Estimate por lista, por filtro e por lote acima do limite.
- Criacao idempotente de job.
- Dedupe de CNPJ.
- Bloqueio de CNPJ inativo.
- Entitlement e quota por plano.
- Cancelamento.
- Export CSV parcial.
- Isolamento por `account_id`.

Enrichment:

- Claim com `FOR UPDATE SKIP LOCKED` e prioridade.
- Cache hit fresco.
- Cache velho enfileira refresh.
- Cache expirado exige novo processamento.
- Retry/backoff.
- Release de leases vencidas.
- Fairness entre contas.
- Trickle nao roda quando ha demanda.
- Falha de rede simulada sem acessar internet real nos testes.
- Publicacao exige evidencia e score minimo.

ETL:

- Parser de manifesto WebDAV.
- Parser de indice HTTP da Receita.
- Parser/cliente do catalogo dados.gov.br.
- Quorum entre fontes.
- Fonte divergente bloqueia load automatico.
- Snapshot igual nao baixa nada.
- Snapshot novo cria `pending_load`.
- Advisory lock impede duas cargas.
- Guard de espaco livre.
- Full-load ativa-only valida zero inativos.
- Erro no load nao marca snapshot como carregado.

Frontend:

- Adicionar Vitest, React Testing Library, user-event e coverage v8.
- Testar selecao de linhas, selecionar pagina e selecionar filtro.
- Testar estimate modal.
- Testar criacao de job.
- Testar drawer de jobs e estados de progresso.
- Testar cancelamento.
- Testar export.
- Testar erro de quota e erro de rede.
- Testar responsividade basica dos componentes criticos.

Gates antes de merge:

```bash
cd api && python -m pytest
cd enrichment && python -m pytest
cd etl && python -m pytest
cd frontend && npm run lint && npm run test:coverage && npm run build
```

## Mitigacao de riscos

Sobrecarga da VPS:

- Concurrency inicial baixa.
- Pausa do trickle durante ETL.
- Limite por lote e por conta.
- Worker com leases e backoff.
- Docker resource limits no compose de producao depois de medir consumo real.

Disco cheio:

- ETL ativa-only como padrao.
- Preflight de espaco antes de baixar.
- Remover ZIPs apos carga validada.
- Dump comprimido fora da VPS.
- Nao manter banco, ZIPs e dumps historicos juntos no mesmo disco.

Dados ruins ou snapshot incompleto:

- Manifesto por arquivo.
- Validacao de quantidade minima de arquivos esperados.
- Comparacao entre fontes.
- Load so vira "oficial" depois de contagem, constraints, analyze e checagem de
  ativos.
- Rollback para ultimo snapshot carregado.

Abuso ou custo inesperado:

- Estimate obrigatorio para lotes grandes.
- Idempotency key.
- Quota diaria/mensal.
- Creditos debitados apenas para itens aceitos.
- Cache hit mais barato ou gratuito conforme regra comercial.

Privacidade, compliance e reputacao:

- Apenas dados publicos e com evidencia.
- Respeitar robots.txt/crawl-delay.
- Nao burlar captcha, login, paywall ou bloqueio.
- Supressao de contato mantida e respeitada na publicacao.
- Auditoria de leitura/export de dados pagos.

Regressao futura:

- Cobertura 100% com testes de contrato.
- Fixtures pequenas e deterministicas.
- Testes de migracao aplicando SQL em Postgres efemero.
- Snapshots de payloads publicos da API.
- Feature flags para liberar por etapa.

UX ruim em job demorado:

- Estimate antes de iniciar.
- Progresso parcial.
- Export parcial.
- Estados claros por CNPJ.
- Cancelamento seguro.

## Ordem de implementacao

- [ ] Migration `014_on_demand_enrichment.sql`.
- [ ] Repositorios backend para jobs, itens, ledger e snapshots.
- [ ] Endpoints de estimate/job/cancel/export.
- [ ] Comandos `demand-worker`, `trickle-worker` e release de leases.
- [ ] Comandos ETL `check-public-data` e `refresh-active-only-if-updated`.
- [ ] Compose/cron de producao para workers e jobs noturnos.
- [ ] Frontend: selecao, estimate, jobs drawer, status na tabela e detalhe.
- [ ] Testes unitarios, integracao e frontend com gate 100%.
- [ ] Rodar carga de homologacao com lote pequeno.
- [ ] Deploy na VPS com flags desligadas, ligar primeiro estimate, depois jobs,
  depois trickle.

## Criterios de pronto

- Um usuario filtra empresas, estima enrichment, confirma job e ve progresso sem
  travar a busca.
- Cache existente e reaproveitado sem crawler.
- CNPJ inativo nunca entra no worker.
- Worker lento aumenta cobertura quando a VPS esta ociosa.
- Job noturno detecta se a Receita publicou snapshot novo.
- ETL so carrega snapshot validado por manifesto e mantem zero inativos.
- Todos os pacotes passam com cobertura 100%.
- A VPS KVM 4 continua com margem de CPU, memoria e disco durante uso normal.

# Active-Only ETL para VPS Econômica

Objetivo: manter no banco apenas CNPJs abertos/ativos, reduzindo disco, índices,
tempo de backup e custo da VPS sem degradar a qualidade do dado usado pela API.

## Regra de corte

O corte usa `estabelecimentos.situacao_cadastral = 2`, que na base da Receita
representa cadastro ativo.

O ETL mantém:

- todos os estabelecimentos ativos;
- a linha de `empresas` de cada `cnpj_basico` que tem pelo menos um estabelecimento ativo;
- `simples` e `socios` somente para esses `cnpj_basico` ativos;
- tabelas de domínio pequenas, como CNAE, municípios, países, naturezas,
  qualificações e motivos.

O ETL descarta:

- estabelecimentos baixados, inaptos, suspensos ou nulos para prospecção ativa;
- empresas sem nenhum estabelecimento ativo;
- `simples` e `socios` ligados somente a empresas sem estabelecimento ativo.

## Como o fluxo evita dados mortos

`ETL_ACTIVE_ONLY=true` é o padrão.

O `full-load` roda em duas fases:

1. Carrega referências e `estabelecimentos`, filtrando cada batch para manter
   somente `situacao_cadastral = 2`.
2. Cria uma tabela transitória `UNLOGGED etl_active_cnpjs` com os `cnpj_basico`
   ativos e usa `JOIN` contra essa tabela para carregar `empresas`, `simples`
   e `socios`.

A tabela `etl_active_cnpjs` é apagada no fim do `full-load`, então ela não fica
ocupando espaço na VPS.

## Economia esperada

Pelos dados medidos localmente:

- estabelecimentos totais: 70.863.993;
- estabelecimentos ativos: 28.739.635;
- CNPJs base totais: 67.642.315;
- CNPJs base com pelo menos um estabelecimento ativo: 27.398.796.

Isso remove aproximadamente 59% da base RF bruta. A economia esperada é:

- cerca de 28,5 GB só em `estabelecimentos` + `empresas`;
- cerca de 34,5 GB incluindo a redução proporcional em `simples` + `socios`;
- banco final esperado perto de 33-40 GB, antes do crescimento de enrichment.

## Comando recomendado na VPS

Use uma base limpa. Se o volume já foi populado com a carga completa, apagar
linhas com `DELETE` não devolve o espaço de forma eficiente; para economia real,
recrie o volume ou restaure a partir de um dump ativo-only.

Subir infra:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres redis
```

Rodar full-load ativo-only:

```bash
docker compose --profile etl run --rm etl python main.py full-load
```

Conferir contagens:

```bash
docker compose exec -T postgres psql -U cnpj_user -d cnpj -P pager=off -c "
SELECT count(*) AS estabelecimentos_ativos
FROM estabelecimentos
WHERE situacao_cadastral = 2;

SELECT count(*) AS estabelecimentos_nao_ativos
FROM estabelecimentos
WHERE situacao_cadastral IS DISTINCT FROM 2;
"
```

O segundo número deve ser zero.

## Backup e transporte compacto

Para mover banco entre máquinas, usar dump comprimido. Não copiar o diretório
`pgdata` a quente.

```bash
docker compose exec -T postgres pg_dump -U cnpj_user -d cnpj -Fc -Z9 > cnpj-active.dump
```

Restaurar:

```bash
docker compose exec -T postgres pg_restore -U cnpj_user -d cnpj --clean --if-exists < cnpj-active.dump
```

Regra operacional: não manter dump completo, ZIPs da Receita e banco ativo no
mesmo disco pequeno por muito tempo. Gerar o dump, transferir para storage
externo e remover da VPS.

## Atualizações mensais

Com `ETL_ACTIVE_ONLY=true`, o comando `update` incremental fica bloqueado de
propósito. Mudanças de status de ativa para baixada exigem remoção consistente
em várias tabelas, então o caminho seguro e barato é rodar um novo `full-load`
ativo-only mensal ou criar no futuro uma rotina de refresh transacional própria.

## Cuidados de custo

- Manter pelo menos 40 GB livres na VPS.
- Não guardar histórico de dumps dentro da VPS.
- Rodar workers de enrichment em escala reduzida.
- Limpar cache Docker após builds grandes:

```bash
docker system prune
```

Usar `docker system prune -a` só quando houver certeza de que imagens antigas
não são necessárias para rollback.

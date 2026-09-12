# Guia de testes e demonstração

O [passo a passo](PASSO_A_PASSO.md) prepara o ambiente. Execute os comandos PowerShell na raiz do projeto, com os bancos já iniciados. Consultas SQL devem usar a conexão indicada. Não execute o script de demonstração inteiro de uma vez.

## 1. Escopo e preparação

Confirme `.env`, origem restaurada, CT preparado e DW criado conforme o roteiro principal. Se código, SQL ou testes mudaram, execute `docker compose build etl`. A ETL roda um ciclo por chamada. Os testes automatizados usam bases próprias; a demonstração opcional da seção 8 modifica a cópia didática do AdventureWorks e exige restauração dos valores.

## 2. Serviços e carga

```powershell
docker compose up -d --wait --wait-timeout 300 postgres sqlserver
if ($LASTEXITCODE -ne 0) { throw 'Os bancos não ficaram prontos.' }
docker compose run --rm etl run
if ($LASTEXITCODE -ne 0) { throw 'A carga falhou.' }
```

Uma instalação vazia deve indicar `initial`; uma instalação já carregada deve indicar `incremental`. Não apague dados para obter uma mensagem de primeira carga.

## 3. Reconciliação

```powershell
docker compose run --rm etl verify
if ($LASTEXITCODE -ne 0) { throw 'Reconciliação reprovada.' }
```

Confira `evidence/reconciliation.json`: `PASS`, zero divergências, contagens e receita iguais entre origem e destino. Preserve a exportação antes de repetir, pois o arquivo é sobrescrito. As evidências que acompanham esta entrega estão descritas em [RESULTADOS.md](../evidence/RESULTADOS.md).

## 4. Incremental sem alterações

Sem editar a origem, repita `docker compose run --rm etl run`. Espere zero fatos extraídos, escritos e excluídos. No PostgreSQL, execute:

```sql
SELECT * FROM etl.controle WHERE pipeline='vendas';
SELECT inicio, fim, fim-inicio AS duracao, status, modo,
       versao_anterior, versao_nova, estatisticas, erro
FROM etl.execucao ORDER BY inicio DESC LIMIT 5;
```

O checkpoint pode permanecer igual. Execute `verify` novamente e espere PASS.

## 5. Qualidade e modelo estrela

Execute [004_qualidade.sql](../sql/postgres/004_qualidade.sql) no PostgreSQL. As três primeiras consultas devem retornar zero linhas. Confira também:

```sql
SELECT conname, convalidated FROM pg_constraint
WHERE conrelid='dw.fato_venda'::regclass AND contype='f'
ORDER BY conname;
```

Espere oito FKs validadas. Abra as sete tabelas do esquema `dw` no diagrama ER do DBeaver e compare com [o modelo estrela](modelo_estrela.png).

## 6. Dez indicadores

```powershell
docker compose run --rm etl report
if ($LASTEXITCODE -ne 0) { throw 'Exportação dos indicadores falhou.' }
```

Execute [003_comprovar_kpis.sql](../sql/postgres/003_comprovar_kpis.sql) no PostgreSQL e compare os resultados com `evidence/kpis.json`. A população é status 5; receitas são UM da fonte e expedição não significa entrega ao cliente.

## 7. Testes automatizados

### 7.1 Transformações

```powershell
docker compose run --rm --entrypoint python etl -m pytest tests/test_transform.py -q
if ($LASTEXITCODE -ne 0) { throw 'Testes de transformação falharam.' }
```

### 7.2 PostgreSQL e Change Tracking real

Crie uma vez a base descartável de testes. Se `test_aw_dw` já existir como base exclusiva desses testes, pule somente o `createdb`. Se alterou `PGUSER`, use esse usuário no lugar de `dw`.

```powershell
docker compose exec postgres createdb -U dw test_aw_dw
```

```powershell
docker compose run --rm -e PGDATABASE=test_aw_dw -e DW_TEST_DATABASE=test_aw_dw -e RUN_SQLSERVER_TESTS=1 --entrypoint python etl -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'A suíte completa falhou.' }
```

A versão atual tem 28 casos. Registre o resultado observado e não apresente CT como validado quando houver testes SQL Server pulados. As fixtures apagam os esquemas apenas da base PostgreSQL de teste e criam/removem suas próprias bases SQL Server. O workflow CI atual usa PostgreSQL; os três testes CT exigem a execução completa acima.

## 8. Demonstração opcional de alteração, SCD1 e recuperação

Use somente o AdventureWorks didático deste projeto. Guarde cópias de `reconciliation.json` e `kpis.json`, registre o checkpoint e os valores iniciais. Abra [003_demo_incremental.sql](../sql/sqlserver/003_demo_incremental.sql) na conexão SQL Server/AdventureWorks2016.

1. Execute **apenas a etapa A** do SQL para salvar o item e a categoria originais. Confirme a transação se o autocommit estiver desligado. Consulte `dbo.DWDemoBackup` e anote pedido/item.
2. No PostgreSQL, registre o item, a receita e a SK do produto antes da alteração. Consulte `dw.fato_venda` filtrando o pedido/item anotados e `dw.dim_produto` pela `produto_sk` correspondente.
3. Execute **apenas a etapa B** no SQL Server e faça COMMIT. Ela aumenta a quantidade sem atribuir `ModifiedDate`. No PowerShell, execute `docker compose run --rm etl run --fail-before-checkpoint`. **A falha é esperada**. Confira que o checkpoint e o item no DW continuam com os valores anteriores e que `etl.execucao` contém status `failed`.
4. Execute `docker compose run --rm etl run`. Agora a atualização deve ser aplicada e o checkpoint confirmado. Execute `verify` e espere PASS. Registre os valores antes/depois e as estatísticas da execução.
5. Execute **apenas a etapa C** do SQL e faça COMMIT. Rode a ETL e confira a mudança da categoria em `dw.dim_produto`, preservando as SKs. A mudança de categoria pode afetar vários produtos; confira as contagens retornadas.
6. Execute **apenas a etapa D** do SQL e faça COMMIT para restaurar os valores originais e remover as tabelas de apoio. Rode `run`, `verify` e `report` novamente. Espere PASS e os valores comerciais iniciais. A versão CT terá avançado e os eventos de auditoria podem permanecer, mesmo após restaurar os valores.

Se interromper a demonstração, preserve as tabelas de apoio e retome pela etapa correspondente; não repita A enquanto elas existirem. A consulta `verify` não deve ser esperada como PASS entre a alteração da origem e a aplicação bem-sucedida da ETL.

## 9. Registrar uma nova execução

Registre responsável, data/hora, versão Python/bancos, commit ou manifesto dos arquivos, saídas de testes e estatísticas da carga. Preserve o registro da revisão anterior ou identifique claramente sua substituição. Atualize as datas e tabelas do artigo quando trocar a evidência usada para sustentá-lo.

# AdventureWorks DW — do zero ao resultado final

Este roteiro permite montar o ambiente e avaliar o projeto em um computador Windows x86-64 com Docker Desktop. Execute uma etapa por vez. **Só avance quando o resultado esperado da etapa anterior for confirmado.** Os valores e as mensagens apresentados como esperados são critérios de teste, não resultados já medidos no seu computador.

Ao terminar, você terá o AdventureWorks2016 no SQL Server, um DW de vendas no PostgreSQL, a carga inicial reconciliada, a carga incremental validada, dez indicadores consultáveis e evidências dos testes. Não há site ou dashboard para abrir: a entrega funciona pelo terminal e pelo DBeaver.

## 1. Instalar e abrir as ferramentas

Instale:

- [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/), com os pré-requisitos de WSL 2 e virtualização indicados pelo instalador. Use containers Linux.
- [DBeaver Community](https://dbeaver.io/download/), para visualizar os dois bancos e executar consultas.
- [Git para Windows](https://git-scm.com/downloads/win), se for clonar o repositório. Quem recebe um ZIP pode extraí-lo pelo Explorador.

Abra o Docker Desktop e aguarde o motor iniciar. Planeje aproximadamente 8 GB disponíveis para o ambiente Docker, além da memória do Windows, e espaço em disco para imagens e bancos. SQL Server neste projeto exige x86-64; não presuma compatibilidade com computadores ARM.

**Não é preciso instalar Python, SQL Server ou PostgreSQL diretamente no Windows:** o Docker fornece esses componentes. O DBeaver é apenas o cliente de consulta.

Abra um PowerShell novo e execute separadamente:

```powershell
docker version
```

Esperado: informações de **Client e Server**. Se aparecer somente Client ou acesso negado, resolva o acesso ao Docker antes de continuar.

```powershell
docker compose version
```

Esperado: Compose v2 com suporte a `up --wait`. O Docker Desktop atualizado inclui o Compose.

## 2. Obter o projeto e abrir a pasta correta

Baixe e extraia o ZIP do projeto ou clone o endereço real fornecido pelo grupo. Não existe uma URL de repositório fictícia neste roteiro.

No Explorador, abra a pasta que contém `compose.yaml` e `README.md`. Clique na barra de endereço, copie o caminho e entre nele pelo PowerShell:

```powershell
Set-Location 'C:\caminho\onde\voce\extraiu\adventureworks-dw'
Get-ChildItem
```

Substitua o caminho de exemplo. Você deve enxergar `compose.yaml`, `Dockerfile`, `.env.example`, `etl`, `sql`, `tests`, `docs` e `scripts`. Não execute os comandos na pasta superior ou dentro de `docs`.

Todos os comandos seguintes são executados nesse mesmo PowerShell, na raiz do projeto. Os blocos identificados como SQL serão executados no DBeaver, na conexão indicada.

## 3. Configurar as credenciais e as portas

Crie `.env` somente se ainda não existir:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
notepad .env
```

No editor, altere `MSSQL_SA_PASSWORD` e `PGPASSWORD` para duas senhas de laboratório que você conheça. Na senha do SQL Server, use ao menos 12 caracteres com maiúsculas, minúsculas, números e símbolos. Para evitar problemas de interpretação do `.env` neste primeiro uso, prefira letras, números, `_` e `!`, sem espaços, `$` ou `#`. Salve o arquivo e feche o editor.

Deixe as demais configurações como no exemplo:

```dotenv
MSSQL_PORT=14330
PGPORT_EXTERNAL=54330
SOURCE_HOST=sqlserver
SOURCE_PORT=1433
SOURCE_DB=AdventureWorks2016
SOURCE_USER=sa
PGHOST=postgres
PGPORT=5432
PGDATABASE=adventureworks_dw
PGUSER=dw
```

`sqlserver:1433` e `postgres:5432` são endereços **internos dos containers**. No DBeaver, serão `localhost:14330` e `localhost:54330`. Não troque os hosts internos por `localhost` no `.env` quando executar a ETL pelo Docker.

O arquivo deve se chamar `.env`, e não `.env.txt`. As senhas não devem ser publicadas no GitHub. A senha usada no DBeaver será exatamente a definida aqui, sem o nome da variável e sem o sinal `=`.

Valide o Compose sem imprimir credenciais:

```powershell
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Corrija o .env ou o Compose antes de continuar.' }
```

Esperado: nenhum erro. Um comando que termina silenciosamente pode ter funcionado; `$LASTEXITCODE = 0` indica sucesso.

### Somente para apagar uma instalação anterior e reiniciar do zero

**Quem nunca executou o projeto pode pular esta subseção.** Quem teve os containers e volumes do Compose atual removidos também pode seguir diretamente para a etapa 4.

Esta limpeza apaga o SQL Server e o PostgreSQL do projeto, incluindo cargas, checkpoints e testes. O código, o `.env`, as imagens e o backup em `backups/` permanecem. Remover apenas os containers não zera os bancos, pois os volumes persistem.

Confira o escopo antes de apagar:

```powershell
docker compose -p adventureworks-olap -f compose.yaml ps -a
docker volume ls --filter label=com.docker.compose.project=adventureworks-olap
```

O Compose deste projeto usa `postgres`, `sqlserver` e dois volumes: `adventureworks-olap_pgdata` e `adventureworks-olap_mssqldata`. Se os recursos identificados não corresponderem ao ambiente que deseja zerar, pare e confira o projeto.

Para o reinício deliberado:

```powershell
docker compose -p adventureworks-olap -f compose.yaml --profile tools down --volumes --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'A limpeza falhou; confira o Docker antes de prosseguir.' }
```

Repita os dois comandos de inspeção. Esperado: nenhum container ou volume desse Compose. Não use `docker system prune` ou remoção global de volumes para reiniciar este projeto. Em uso normal, a etapa 15 mostra como encerrar preservando os dados.

## 4. Obter o backup correto

No PowerShell:

```powershell
.\scripts\download_backup.ps1
```

Se o PowerShell bloquear a execução do script, baixe pelo navegador o [AdventureWorks2016.bak oficial da Microsoft](https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks2016.bak) e salve na pasta `backups` do projeto.

Não use AdventureWorksDW, AdventureWorksLT, um arquivo ZIP renomeado ou uma página HTML salva como `.bak`.

Confira o arquivo:

```powershell
Get-Item -LiteralPath .\backups\AdventureWorks2016.bak | Select-Object Name,Length
Get-FileHash -LiteralPath .\backups\AdventureWorks2016.bak -Algorithm SHA256
```

Esperado: arquivo presente, com tamanho diferente de zero. Registre o SHA-256 utilizado para identificar o backup da execução; o hash calculado sozinho não autentica o download. O script preserva um backup existente. A restauração da etapa 7 confirmará se o SQL Server consegue ler seu conteúdo.

## 5. Subir os dois bancos e aguardar a prontidão

```powershell
docker compose up -d --wait --wait-timeout 300 postgres sqlserver
if ($LASTEXITCODE -ne 0) { throw 'Os bancos não ficaram prontos; consulte os logs.' }
docker compose ps
```

A primeira subida pode demorar para baixar as imagens. Esperado: `postgres` e `sqlserver` com estado **healthy** e as portas externas 54330 e 14330. O serviço `etl` ainda não precisa aparecer ativo.

Se houver falha:

```powershell
docker compose logs --tail 80 sqlserver
docker compose logs --tail 80 postgres
```

Corrija o erro antes de continuar. O timeout não significa que o backup foi restaurado: nesta etapa, apenas os servidores iniciaram. **AdventureWorks2016 ainda será criado na etapa 7.**

## 6. Construir a imagem da ETL

```powershell
docker compose build etl
if ($LASTEXITCODE -ne 0) { throw 'O build da ETL falhou.' }
```

Esperado: build concluído sem erro. O Docker instala Python e as dependências e copia o código para a imagem. Sempre repita o build se alterar código, SQL ou testes depois desta etapa.

`docker compose run --rm etl ...` cria um container temporário para cada comando e o remove ao terminar. Isso é normal; a ETL não fica rodando continuamente.

## 7. Restaurar e confirmar o AdventureWorks2016

```powershell
docker compose run --rm etl restore
if ($LASTEXITCODE -ne 0) { throw 'A restauração falhou; não avance para a ETL.' }
```

Esperado em um ambiente limpo: **`Banco AdventureWorks2016 restaurado.`** Se aparecer “Base já existe; restauração ignorada”, a origem já existia; o comando não a sobrescreve. Isso não comprova uma restauração nova nem garante que o banco existente esteja online.

Agora abra o DBeaver e crie uma conexão **SQL Server**:

| Campo | Valor |
|---|---|
| Host | `localhost` |
| Porta | `14330` |
| Banco, neste primeiro teste | `master` |
| Autenticação | SQL Server Authentication / usuário e senha |
| Usuário | `sa` |
| Senha | Valor de `MSSQL_SA_PASSWORD` no `.env` |
| Propriedades do driver | `encrypt=true`, `trustServerCertificate=true` para o certificado deste laboratório local |

Clique em **Testar conexão**, aceite o download do driver se solicitado e conclua a conexão. Abra um editor SQL ligado a essa conexão e execute:

```sql
SELECT name, state_desc
FROM sys.databases
WHERE name = 'AdventureWorks2016';
```

Esperado: uma linha `AdventureWorks2016 | ONLINE`. Isso confirma que o banco está disponível, mas **não muda o banco ativo do editor SQL**.

Edite a conexão, troque o banco de `master` para `AdventureWorks2016` e salve. Desconecte e conecte novamente; abra um **novo editor SQL nessa conexão**. Um editor que já estava aberto pode continuar usando a sessão anterior em `master`, mesmo que a configuração da conexão mostre o banco correto.

No editor SQL Server em que fará as consultas, selecione e execute **primeiro esta instrução isoladamente**:

```sql
USE [AdventureWorks2016];
```

Depois execute, no mesmo editor:

```sql
SELECT DB_NAME() AS banco_atual;
```

**Só avance se o resultado for `AdventureWorks2016`.** Se retornar `master`, a consulta ainda está na sessão errada: execute o `USE` nesse mesmo editor ou reconecte e abra um novo editor na conexão correta.

Agora execute a contagem, indicando explicitamente o banco para evitar ambiguidade:

```sql
SELECT COUNT_BIG(*) AS itens_origem
FROM [AdventureWorks2016].[Sales].[SalesOrderDetail];
```

Esperado: contagem positiva. Guarde a contagem real, sem inventar um total de referência. O nome completo permite consultar essa tabela mesmo a partir de `master`, mas não troca o contexto da sessão: para as verificações de Change Tracking da próxima etapa, `DB_NAME()` ainda deve retornar `AdventureWorks2016`.

**Se aparecer `Erro SQL [208]: Invalid object name 'Sales.SalesOrderDetail'`:** confira primeiro `SELECT DB_NAME();`. Quando ele retorna `master`, a consulta procurou a tabela no banco errado. Corrija o contexto conforme acima; não restaure o backup nem recrie os containers por esse motivo. Se o erro persistir com o banco correto ou com o nome completo, confira se a restauração é do AdventureWorks2016 completo.

Se `master` conectar, mas `AdventureWorks2016` não conectar, volte à consulta de `sys.databases`. Não continue tentando senhas diferentes quando o erro for de banco ausente. A etapa 16 detalha os estados 8 e 38 do erro 18456.

## 8. Preparar o Change Tracking e criar o DW

No PowerShell, prepare a origem:

```powershell
docker compose run --rm etl prepare-source
if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o Change Tracking.' }
```

Esperado: saída zero. No DBeaver **SQL Server / AdventureWorks2016**, execute primeiro `USE [AdventureWorks2016];` isoladamente e confira `SELECT DB_NAME();` no mesmo editor. Só continue se retornar `AdventureWorks2016`, pois as consultas abaixo dependem do banco ativo:

```sql
SELECT name, snapshot_isolation_state_desc
FROM sys.databases WHERE name = DB_NAME();
SELECT DB_NAME(database_id) AS banco, retention_period, retention_period_units_desc
FROM sys.change_tracking_databases WHERE database_id = DB_ID();
SELECT OBJECT_SCHEMA_NAME(object_id) AS esquema, OBJECT_NAME(object_id) AS tabela
FROM sys.change_tracking_tables ORDER BY esquema, tabela;
```

Esperado: snapshot isolation `ON`, uma configuração CT para o banco e dez tabelas monitoradas. O CT identifica mudanças confirmadas; ele será usado nas próximas cargas.

No PowerShell, crie os esquemas, tabelas e indicadores no destino:

```powershell
docker compose run --rm etl init
if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o DW.' }
```

No DBeaver, crie uma segunda conexão, agora **PostgreSQL**:

| Campo | Valor |
|---|---|
| Host | `localhost` |
| Porta | `54330` |
| Banco | `adventureworks_dw` |
| Usuário | `dw` |
| Senha | Valor de `PGPASSWORD` no `.env` |
| SSL | Desabilitado neste laboratório local |

Teste a conexão e abra um editor SQL nela:

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'dw' AND table_type = 'BASE TABLE' ORDER BY table_name;
SELECT table_name FROM information_schema.views
WHERE table_schema = 'dw' AND table_name LIKE 'kpi_%' ORDER BY table_name;
```

Esperado: **sete tabelas** (seis dimensões e `fato_venda`) e **dez views de KPI**. A fato estará vazia antes da carga. `etl.controle` e `etl.execucao` são tabelas técnicas em outro esquema.

## 9. Executar a primeira carga

```powershell
docker compose run --rm etl run
if ($LASTEXITCODE -ne 0) { throw 'A carga falhou; confira a mensagem antes de continuar.' }
```

Aguarde o comando terminar. Esperado em bancos novos: `modo = initial`, fatos extraídos e escritos em quantidade positiva e um checkpoint gravado. Se aparecer `incremental`, já havia checkpoint: essa execução não é a primeira carga de um ambiente vazio.

No **PostgreSQL**, confirme:

```sql
SELECT COUNT(*) AS itens_dw FROM dw.fato_venda;
SELECT * FROM etl.controle WHERE pipeline = 'vendas';
SELECT inicio, fim, fim - inicio AS duracao, status, modo,
       versao_anterior, versao_nova, estatisticas, erro
FROM etl.execucao ORDER BY inicio DESC LIMIT 5;
```

Esperado: contagem positiva, checkpoint presente, última execução `success` e modo `initial`. A contagem deve coincidir com a origem da etapa 7 quando não houver mudanças concorrentes. A próxima etapa faz a comparação completa dos fatos.

## 10. Reconciliar origem e destino

Sem alterar dados no SQL Server:

```powershell
docker compose run --rm etl verify
if ($LASTEXITCODE -ne 0) { throw 'A reconciliação não foi aprovada.' }
Get-Content -LiteralPath .\evidence\reconciliation.json
```

Esperado:

- `resultado`: `PASS`;
- `itens_divergentes`: `0`;
- `itens_origem` igual a `itens_dw`;
- `receita_origem_todos_status` igual a `receita_dw_todos_status`.

A verificação compara chaves e atributos dos fatos com uma leitura consistente da fonte. Os valores de receita incluem todos os status e não precisam coincidir com os KPIs, que filtram `status = 5`.

Se a origem mudou desde a carga, faça `run` e depois `verify` em uma janela sem escritas. Se houver divergências, registre a falha e as chaves indicadas; não marque a etapa como aprovada.

## 11. Comprovar a carga incremental

**Se uma versão anterior falhou com o erro SQL Server 3964:** atualize o código e execute `docker compose build etl` antes de repetir o ciclo abaixo. O defeito era a criação de um índice temporário dentro da transação snapshot; a estrutura agora é preparada antes da transação, mantendo a leitura consistente das mudanças. O erro ocorria durante a extração, antes da gravação do lote no DW. Não apague os volumes, não restaure novamente e não use `--resync` para corrigir esse erro. A próxima carga normal retoma a partir do checkpoint anterior. O registro `failed` pode permanecer no histórico da ETL.

Sem editar a origem, rode outra carga:

```powershell
docker compose run --rm etl run
if ($LASTEXITCODE -ne 0) { throw 'O ciclo incremental falhou.' }
```

Esperado:

```text
modo: incremental
facts_extracted: 0
facts_written: 0
facts_deleted: 0
```

Consulte `etl.execucao` novamente para guardar o registro. A versão pode permanecer igual se não houver mudanças; ela não precisa aumentar a cada execução. O DW não deve ganhar linhas duplicadas.

```powershell
docker compose run --rm etl verify
if ($LASTEXITCODE -ne 0) { throw 'Falha na reconciliação após o incremental.' }
```

Esperado: `PASS` novamente. A ETL só roda quando você chama `run`; ela não monitora a origem continuamente em segundo plano.

## 12. Consultar qualidade, diagrama e dez KPIs

No **PostgreSQL**, abra `sql/postgres/004_qualidade.sql` no editor SQL. Selecione a conexão correta e execute as instruções, ou use executar script (normalmente `Alt+X`). As três primeiras consultas devem retornar **zero linhas**, indicando ausência das inconsistências verificadas. As demais mostram dados por status e histórico da ETL; elas não precisam estar vazias.

Expanda o esquema `dw`, selecione suas sete tabelas e abra um diagrama ER pelo menu de contexto. Confira as seis dimensões ligadas à fato e os três relacionamentos com a dimensão data. O desenho também está em [modelo_estrela.png](modelo_estrela.png).

Para conferir as oito FKs da fato:

```sql
SELECT conname, convalidated FROM pg_constraint
WHERE conrelid = 'dw.fato_venda'::regclass AND contype = 'f'
ORDER BY conname;
```

Esperado: oito linhas com `convalidated = true`.

No PowerShell, exporte os indicadores:

```powershell
docker compose run --rm etl report
if ($LASTEXITCODE -ne 0) { throw 'Falha ao exportar os indicadores.' }
Get-Content -LiteralPath .\evidence\kpis.json
```

No **PostgreSQL**, execute `sql/postgres/003_comprovar_kpis.sql`. Há dez consultas de indicadores e uma consulta adicional de análise por mês, categoria, território e canal. Compare os resultados com as dez entradas de `indicadores` no JSON da mesma carga.

| Indicador | O que conferir |
|---|---|
| 1. Receita bruta | Soma da quantidade × preço dos itens expedidos |
| 2. Descontos | Soma dos descontos monetários |
| 3. Receita líquida | Receita bruta − descontos |
| 4. Unidades | Soma das quantidades |
| 5. Pedidos | Pedidos distintos, não quantidade de itens |
| 6. Ticket médio | Receita líquida / pedidos distintos |
| 7. Taxa de desconto | 100 × descontos / receita bruta |
| 8. Clientes ativos | Clientes distintos com compra no filtro |
| 9. Crescimento mensal | Comparação com o mês anterior; base zero pode gerar `NULL` |
| 10. Expedição no prazo | ShipDate até DueDate; não é confirmação de entrega ao cliente |

As fórmulas, o tratamento de denominadores zero e as limitações estão em [KPIS.md](KPIS.md). Valores monetários são UM da fonte; receita líquida aqui não é lucro. No **SQL Server**, `sql/sqlserver/002_analise_oltp.sql` permite examinar a estrutura e os dados de origem.

## 13. Executar a suíte de testes em bases separadas

Primeiro, testes de transformação:

```powershell
docker compose run --rm --entrypoint python etl -m pytest tests/test_transform.py -q
if ($LASTEXITCODE -ne 0) { throw 'Os testes de transformação falharam.' }
```

Esperado: testes aprovados, sem falhas. Agora crie **uma vez** um banco PostgreSQL exclusivo para os testes:

```powershell
docker compose exec postgres createdb -U dw test_aw_dw
if ($LASTEXITCODE -ne 0) { throw 'Confira se test_aw_dw já existe antes de continuar.' }
```

Em execuções posteriores, se o banco já existir e for a base descartável deste roteiro, pule apenas o `createdb`. Os testes apagam e recriam os esquemas `dw` e `etl` nessa base. Nunca substitua `test_aw_dw` pelo banco principal.

Execute a suíte completa, incluindo Change Tracking real:

```powershell
docker compose run --rm -e PGDATABASE=test_aw_dw -e DW_TEST_DATABASE=test_aw_dw -e RUN_SQLSERVER_TESTS=1 --entrypoint python etl -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'A suíte completa falhou.' }
```

Esperado: todos aprovados, sem `failed`, sem `error` e sem `skipped`. Registre a quantidade realmente exibida. Os testes SQL Server criam uma base sintética temporária e a removem ao finalizar; os testes PostgreSQL usam `test_aw_dw`. As opções `-e` valem para esse container e não alteram `.env` nem apontam a próxima carga normal para o banco de testes.

A suíte verifica inserção, atualização, exclusão, dependências de cabeçalho e categoria, SCD1, KPIs, reexecução, rollback, recuperação e concorrência. Massa sintética comprova esses cenários controlados; `verify` comprova a carga do AdventureWorks restaurado.

Se os testes SQL Server ficarem pulados, confira `RUN_SQLSERVER_TESTS=1`: nesse caso, não registre CT como validado. A suíte inclui uma regressão específica do erro 3964: ciclo vazio, pedido alterado em cabeçalho e item sem duplicação e exclusão do último item.

## 14. Guardar os resultados finais e apresentar

Ao terminar a suíte, rode novamente os comandos normais contra os bancos principais:

```powershell
docker compose run --rm etl verify
if ($LASTEXITCODE -ne 0) { throw 'Falha na reconciliação final.' }
docker compose run --rm etl report
if ($LASTEXITCODE -ne 0) { throw 'Falha no relatório final.' }
```

Preencha [evidence/RESULTADOS.md](../evidence/RESULTADOS.md) com a data, responsável, contagens, receitas, versões, duração da carga, estatísticas do incremental e saída da suíte. Registre o SHA-256 do backup e as versões de software:

```powershell
docker version
docker compose version
docker compose images
docker image inspect postgres:17 --format '{{json .RepoDigests}}'
docker image inspect mcr.microsoft.com/mssql/server:2022-latest --format '{{json .RepoDigests}}'
```

Se recebeu o projeto via Git, registre também `git rev-parse HEAD` e `git status --short`. Um ZIP sem `.git` não terá commit disponível; indique a origem e a versão do pacote recebido.

O resultado final esperado é:

- Dois bancos acessíveis pelo DBeaver, origem online e DW preenchido.
- Seis dimensões, uma fato, oito FKs e dez views de KPI.
- Carga inicial `success` e ciclo incremental sem mudanças com zero fatos extraídos/escritos/excluídos.
- Reconciliação `PASS`, sem divergências.
- Consultas de qualidade aprovadas e indicadores conferidos.
- Suíte completa aprovada, incluindo CT.
- `evidence/reconciliation.json`, `evidence/kpis.json`, ficha preenchida e capturas de diagrama, consultas e testes.

`verify` e `report` sobrescrevem seus JSONs. Para comparar cenários, copie os resultados intermediários antes de executar novamente. Os JSONs são ignorados pelo Git por padrão; após revisão, podem acompanhar a entrega como anexos. O apoio do grupo fica em `apoio-interno/` e não faz parte da entrega.

O professor pode executar este roteiro completo em outra máquina. Para uma avaliação curta do ambiente já pronto, pode conferir as etapas 10 a 12 e a evidência da suíte. A demonstração de atualização no backup, SCD1 e falha injetada está na etapa 8 do [guia de testes detalhado](GUIA_TESTES.md); ela é opcional e exige restaurar os valores ao terminar.

## 15. Encerrar e retomar sem perder os dados

Para pausar:

```powershell
docker compose stop
```

Para retomar em outro dia:

```powershell
docker compose up -d --wait --wait-timeout 300 postgres sqlserver
```

Depois, use `run`, `verify` e `report` conforme necessário. Não repita a restauração nem apague volumes em uma retomada normal. `docker compose down` remove os containers e a rede preservando os volumes. A opção `--volumes` fica reservada ao reinício deliberado explicado na etapa 3.

## 16. Erros comuns e ponto de retomada

| Sintoma | Como agir |
|---|---|
| Docker mostra `permission denied` ou não mostra Server | Abra o Docker Desktop, aguarde o motor e teste `docker version` no terminal local com acesso ao Docker. Não avance para comandos de banco. |
| `no configuration file provided` | Volte à raiz que contém `compose.yaml`. |
| `.env` não encontrado | Confira a etapa 3 e se o nome não virou `.env.txt`. |
| Porta já ocupada | Mude somente `MSSQL_PORT` ou `PGPORT_EXTERNAL` no `.env`, suba os serviços novamente e use a nova porta no DBeaver. |
| SQL Server não fica healthy | Consulte os logs da etapa 5; confira senha, memória e arquitetura x86-64. |
| `18456, State: 8` | Senha de `sa` incorreta. Compare a senha digitada no DBeaver com a usada para inicializar o SQL Server. Alterar apenas o `.env` não redefine a senha de um banco persistido. |
| `208: Invalid object name 'Sales.SalesOrderDetail'` | Execute `SELECT DB_NAME();` no editor. Se retornar `master`, execute `USE [AdventureWorks2016];` isoladamente e confira o contexto novamente. Salve a conexão, reconecte e abra um novo editor. A contagem com `[AdventureWorks2016].[Sales].[SalesOrderDetail]` elimina a ambiguidade; persistindo o erro no banco correto, confira o backup restaurado. |
| `18456, State: 38` | Banco solicitado não pôde ser aberto. Conecte a `master`, consulte `sys.databases` como na etapa 7 e confirme nome e estado. Se ausente, faça `restore`; se estiver offline/restoring/suspect, investigue esse estado antes de continuar. |
| `restore` informa que a base já existe | A restauração é preservadora e foi pulada. Consulte o estado do banco; para laboratório realmente novo, utilize o reset completo da etapa 3. |
| Backup não encontrado ou inválido | Confira o arquivo da etapa 4 e a mensagem do `restore`. Não crie um banco vazio com o mesmo nome para tentar resolver. |
| `prepare-source` ou `run` não encontra tabelas | Confirme AdventureWorks2016 completo e que o `restore` terminou com sucesso. |
| PostgreSQL recusa a senha | Use `PGPASSWORD`. Uma senha editada no `.env` não é reaplicada a um volume já inicializado. |
| DBeaver tenta autenticação Windows | Escolha autenticação SQL Server com `sa` na conexão SQL Server. |
| `Origem mudou desde a carga` | Execute `run` e depois `verify` sem escritas concorrentes. |
| `Já existe uma carga ou reconciliação` | Aguarde o processo ativo; não execute cargas em paralelo. |
| `3964: DDL statement is not allowed inside a snapshot isolation transaction` | Use o código corrigido, reconstrua a imagem com `docker compose build etl` e repita `run` seguido de `verify`. A tabela de pedidos e seu índice precisam ser criados antes do snapshot. Não apague a carga nem mude o isolamento para contornar o erro. |
| Checkpoint CT expirado ou origem restaurada | Leia [ETL.md](ETL.md); uma ressincronização deliberada usa `docker compose run --rm etl run --resync`, seguida de `verify`. |
| `.bak` existe, mas a restauração falha | Preserve a mensagem de erro; o tamanho e o hash sozinhos não garantem backup válido. |

As mensagens de carregamento de `xplog70.dll` e `dbghelp.dll` não são, por si só, falhas de autenticação ou restauração.

## Referências dos comandos de infraestrutura

O comportamento de remoção de containers e volumes está documentado em [Docker Compose down](https://docs.docker.com/reference/cli/docker/compose/down/). A espera pela prontidão está em [Docker Compose up](https://docs.docker.com/reference/cli/docker/compose/up/). A separação entre iniciar SQL Server e restaurar um banco está no [tutorial de restauração da Microsoft](https://learn.microsoft.com/en-us/sql/linux/migrate/tutorial-restore-backup-sql-server-container?view=sql-server-ver17). Os estados de falha de login estão na [referência Microsoft do erro 18456](https://learn.microsoft.com/en-us/sql/relational-databases/errors-events/mssqlserver-18456-database-engine-error?view=sql-server-ver17).

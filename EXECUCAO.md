# Como executar

Use o **PowerShell no Windows**, **Python 3.8 ou superior instalado localmente** para baixar o backup e o **Docker Desktop com containers Linux**. Abra o Docker Desktop e aguarde o motor iniciar. O ETL e os bancos serão executados nos containers.

## 1. Abrir o projeto e configurar

Todos os comandos deste guia partem desta pasta:

```powershell
Set-Location 'C:\Users\lucas\OneDrive\Documentos\codes\adventureworks-dw'
docker version
docker compose version
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
notepad .env
```

O `.env` já está preparado com estas credenciais padrão do laboratório:

| Serviço | Usuário | Senha padrão | Variável da senha |
|---|---|---|---|
| Airflow — interface | `aluno` | `Airflow2026!` | `AIRFLOW_PASSWORD` |
| SQL Server | `sa` | `SqlServer2026!` | `MSSQL_SA_PASSWORD` |
| PostgreSQL — DW | `dw` | `Postgres2026!` | `PGPASSWORD` |
| PostgreSQL — metadados do Airflow | `airflow` | `AirflowDB2026!` | `AIRFLOW_DB_PASSWORD` |

As senhas são padrões locais deliberados. Para mudar o login da interface, edite `AIRFLOW_USER` e `AIRFLOW_PASSWORD`. Se um valor contiver `$`, coloque-o entre aspas simples no `.env`. Não publique o `.env`.

Confira também `BACKUP_DIR=./backups`. Se já existirem bancos inicializados, preserve suas senhas: editar o `.env` não muda a senha armazenada no banco. Salve e feche o editor.

## 2. Disponibilizar o backup

Na raiz do projeto, execute o script abaixo. Ele baixa **AdventureWorks2016.bak** da [publicação oficial da Microsoft](https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks2016.bak) e salva na pasta `backups`, sem exigir bibliotecas adicionais.

```powershell
python baixar_backup.py
Get-Item -LiteralPath '.\backups\AdventureWorks2016.bak'
docker compose config --quiet
```

Execute um comando de cada vez e interrompa se algum falhar. O download mostra o progresso e só publica o arquivo final após concluir a transferência. Se o destino já existir, ele é preservado sem verificar sua integridade. A checagem de tamanho da transferência não confirma que o SQL Server conseguirá restaurar o backup.

O `Get-Item` deve encontrar o arquivo. O `config --quiet` deve terminar sem erro; sucesso não imprime a configuração nem as senhas. Depois, siga para a preparação dos bancos.

## 3. Preparar e fazer a primeira carga

```powershell
docker compose build etl
docker compose up -d --wait sqlserver postgres
docker compose run --rm etl restore
docker compose run --rm etl prepare-source
docker compose run --rm etl init
docker compose run --rm etl check
docker compose run --rm etl run
docker compose run --rm etl kpis
```

O `up --wait` aguarda os bancos ficarem saudáveis. A sequência restaura a origem, habilita o Change Tracking, cria o DW, confere as pré-condições, carrega os dados e apresenta os dez indicadores. A restauração ignora um banco já existente. Não é necessário repetir essa preparação na rotina.

O código Python está em `etl/`; os três scripts SQL estão em `sql/`. Os comandos Docker acima continuam sendo executados na raiz, onde fica `compose.yaml`.

## 4. Executar a rotina incremental

Com o Docker Desktop aberto:

```powershell
docker compose up -d --wait sqlserver postgres
docker compose run --rm etl check
docker compose run --rm etl run
docker compose run --rm etl kpis
```

`run` processa as mudanças desde o checkpoint. Se o Change Tracking indicar checkpoint expirado ou origem incompatível, interrompa e avalie a recuperação antes de continuar.

## 5. Executar pelo Airflow

Depois da preparação inicial:

```powershell
docker compose --profile airflow up -d --build airflow
docker compose --profile airflow ps
```

Aguarde a inicialização e abra [http://localhost:8081](http://localhost:8081). Entre com o usuário **aluno** e a senha **Airflow2026!**. Essa senha é diferente de `AIRFLOW_DB_PASSWORD`, usada no banco de metadados.

O inicializador aplica `AIRFLOW_USER` e `AIRFLOW_PASSWORD` ao arquivo de senhas do [Simple Auth Manager](https://airflow.apache.org/docs/apache-airflow/3.3.2/core-concepts/auth-manager/simple/index.html), preservando as demais entradas desse arquivo. Depois de alterar essas variáveis no `.env`, recrie o container para aplicar o login:

```powershell
docker compose --profile airflow up -d --force-recreate airflow
```

As três senhas de banco são usadas na primeira inicialização dos volumes. Mudar esses valores no `.env` não altera as senhas dos bancos já existentes.

Na interface, localize **adventureworks_simples**, ative a DAG e clique em **Trigger DAG** para disparar manualmente. Acompanhe as quatro tarefas: pré-condições, ETL incremental, validação e geração de evidências. Não é necessário executar `run` pelo terminal junto com a DAG.

### Connections usadas pela DAG

O inicializador cadastra as duas Connections no banco de metadados do Airflow. Na interface, abra **Admin → Connections** para consultar ou editar:

| Connection ID | Tipo | Host | Port | Schema (banco) | Login |
|---|---|---|---|---|---|
| `adventureworks_source` | Microsoft SQL Server | `sqlserver` | `1433` | `AdventureWorks2016` | `sa` |
| `adventureworks_dw` | Postgres | `postgres` | `5432` | `adventureworks_dw` | `dw` |

O campo **Schema** representa o nome do banco, não o esquema SQL `dbo` ou `dw`. Os valores iniciais e as senhas vêm do `.env` efetivo do Compose. O cadastro só cria IDs ausentes: alterações feitas na interface são preservadas nas próximas inicializações. A chave Fernet que criptografa as senhas permanece no volume `airflow`.

Cada tarefa consulta essas Connections pelo SDK do Airflow e usa seus valores para conectar. Uma Connection ausente ou inválida interrompe a tarefa. Os comandos `docker compose run --rm etl ...` continuam usando o `.env`; editar a Connection muda a execução pela DAG, sem alterar a configuração da CLI. Evite definir `AIRFLOW_CONN_ADVENTUREWORKS_SOURCE` ou `AIRFLOW_CONN_ADVENTUREWORKS_DW`, pois sobreporiam o cadastro visível.

Para aplicar esta atualização quando os serviços já estiverem saudáveis, reconstrua somente o Airflow, preservando bancos e volumes:

```powershell
docker compose --profile airflow up -d --build --no-deps airflow
```

## 6. Parar e retomar

```powershell
docker compose --profile airflow stop
```

Esse comando para os containers e preserva os volumes com os bancos e o histórico. Para retomar, use o comando de inicialização dos bancos ou do Airflow mostrado acima. Não use `down -v` para encerrar a rotina, pois ele remove os volumes.

Portas padrão no Windows: SQL Server `localhost:14331`, PostgreSQL `localhost:54331` e Airflow `localhost:8081`. Dentro dos containers, as conexões usam `sqlserver:1433` e `postgres:5432`.

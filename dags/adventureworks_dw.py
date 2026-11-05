"""DAG em blocos: preparação, extração para a stage, dimensões, fato, qualidade e evidências.

Só o bloco de extração acessa o banco de produção, com leituras curtas por chave e
limitadas pelo pool "origem_sqlserver". As transformações rodam em SQL dentro do DW,
em tarefas paralelas, sem segurar recursos da origem.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from uuid import NAMESPACE_URL, uuid5

from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.sdk import TaskGroup, dag, get_current_context, task

DW = "adventureworks_dw"
GRUPOS = ("produto", "cliente", "territorio", "vendedor", "vendas")
DIMENSOES = ("produto", "cliente", "territorio", "vendedor")


@contextmanager
def conexoes_do_airflow():
    """Adapta as Connections ao código Python do ETL apenas durante cada tarefa."""
    from airflow.sdk import Connection

    specs = (
        ("adventureworks_source", "mssql",
         ("SOURCE_HOST", "SOURCE_PORT", "SOURCE_DB", "SOURCE_USER", "MSSQL_SA_PASSWORD")),
        (DW, "postgres", ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")),
    )
    updates = {}
    for conn_id, expected_type, names in specs:
        try:
            if "AIRFLOW_CONN_" + conn_id.upper() in os.environ:
                raise ValueError("Sobreposição por ambiente")
            connection = Connection.get(conn_id)
            values = (connection.host, connection.port, connection.schema,
                      connection.login, connection.password)
            if (connection.conn_type != expected_type or not all(values)
                    or not isinstance(connection.port, int) or not 1 <= connection.port <= 65535):
                raise ValueError("Campos inválidos")
            updates.update(zip(names, map(str, values)))
        except Exception:
            raise RuntimeError("Connection inválida ou indisponível no Airflow: " + conn_id) from None
    previous = {name: os.environ.get(name) for name in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def execucao_id():
    """Mesmo ID em todas as tarefas da execução (e nas novas tentativas)."""
    context = get_current_context()
    return str(uuid5(NAMESPACE_URL, context["dag"].dag_id + "/" + context["run_id"]))


def sql(task_id, arquivo):
    """Tarefa de SQL puro no DW; o arquivo inteiro roda em uma transação."""
    return SQLExecuteQueryOperator(task_id=task_id, conn_id=DW, sql=arquivo, autocommit=False)


@dag(
    dag_id="adventureworks_simples",
    schedule="@daily",
    start_date=datetime(2026, 10, 21, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=4,
    dagrun_timeout=timedelta(minutes=45),
    template_searchpath=["/app/sql"],
    default_args={
        "retries": 2,
        "retry_delay": timedelta(seconds=30),
        "execution_timeout": timedelta(minutes=15),
    },
    tags=["adventureworks", "incremental", "stage"],
    doc_md=__doc__,
)
def vendas():
    # Bloco 1: pré-condições em paralelo, sem gravar nada.
    with TaskGroup("preparacao", tooltip="Confere DW, Change Tracking e checkpoints"):
        estrutura = sql("verificar_dw", "preparacao/estrutura.sql")

        @task(task_id="verificar_origem")
        def verificar_origem():
            from etl import check

            with conexoes_do_airflow():
                return check()

        origem_ok = verificar_origem()

    # Bloco 2: origem -> stage. Única leitura do banco de produção; no máximo
    # duas extrações simultâneas (pool), cada uma em seu próprio snapshot.
    @task(pool="origem_sqlserver")
    def extrair(grupo):
        from etl import extrair as extrair_grupo

        with conexoes_do_airflow():
            return extrair_grupo(grupo, execucao_id())

    with TaskGroup("extracao", tooltip="Origem (produção) -> stage, só chaves alteradas"):
        extracoes = {g: extrair.override(task_id=f"extrair_{g}")(g) for g in GRUPOS}

    # Bloco 3: stage -> dimensões, em paralelo. Cada dimensão começa assim que a
    # sua extração termina e avança o próprio checkpoint.
    with TaskGroup("dimensoes", tooltip="Stage -> dimensões (SCD Tipo 1)"):
        cargas_dim = {d: sql(f"carregar_dim_{d}", f"carga/dim_{d}.sql") for d in DIMENSOES}
        dim_data = sql("carregar_dim_data", "carga/dim_data.sql")

    # Bloco 4: stage -> fato, depois de todas as dimensões.
    with TaskGroup("fato", tooltip="Stage -> fato_venda"):
        fato = sql("carregar_fato_venda", "carga/fato_venda.sql")

    # Bloco 5: validações independentes, em paralelo.
    with TaskGroup("qualidade", tooltip="Regras de consistência do DW"):
        validacoes = [sql(f"validar_{n}", f"qualidade/{n}.sql") for n in ("cabecalhos", "datas", "checkpoints")]

    # Bloco 6: indicadores e auditoria da execução em um arquivo JSON.
    @task(task_id="gerar_evidencias")
    def gerar_evidencias():
        import json
        from pathlib import Path
        from uuid import uuid4

        from etl import kpis

        context = get_current_context()
        identificador = execucao_id()
        with conexoes_do_airflow():
            result = kpis(identificador)
        result.update(dag_id=context["dag"].dag_id, dag_run_id=context["run_id"],
                      tentativa=context["ti"].try_number)
        folder = Path(os.environ["AIRFLOW_HOME"]) / "saidas" / identificador
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"kpis-{uuid4()}.json"
        with path.open("x", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
        return {"execucao_id": identificador, "arquivo": str(path)}

    evidencias = gerar_evidencias()

    # Dependências: blocos em leque, não uma fila única.
    for extracao in extracoes.values():
        [estrutura, origem_ok] >> extracao
    for d in DIMENSOES:
        extracoes[d] >> cargas_dim[d]
    extracoes["vendas"] >> dim_data
    [*cargas_dim.values(), dim_data] >> fato
    fato >> validacoes >> evidencias


vendas()

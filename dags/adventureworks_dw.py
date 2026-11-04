"""Quatro etapas; extração e carga juntas preservam a transação do ETL."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from uuid import NAMESPACE_URL, uuid5

from airflow.sdk import dag, get_current_context, task


@contextmanager
def conexoes_do_airflow():
    """Adapta as Connections ao ETL existente apenas durante cada tarefa."""
    # O SDK consulta as Connections em execução; o parser da DAG não acessa bancos.
    from airflow.sdk import Connection

    specs = (
        (
            "adventureworks_source",
            "mssql",
            (
                "SOURCE_HOST",
                "SOURCE_PORT",
                "SOURCE_DB",
                "SOURCE_USER",
                "MSSQL_SA_PASSWORD",
            ),
        ),
        (
            "adventureworks_dw",
            "postgres",
            ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"),
        ),
    )
    updates = {}
    for conn_id, expected_type, names in specs:
        try:
            if "AIRFLOW_CONN_" + conn_id.upper() in os.environ:
                raise ValueError("Sobreposição por ambiente")
            connection = Connection.get(conn_id)
            values = (
                connection.host,
                connection.port,
                connection.schema,
                connection.login,
                connection.password,
            )
            if (
                connection.conn_type != expected_type
                or not all(values)
                or not isinstance(connection.port, int)
                or not 1 <= connection.port <= 65535
            ):
                raise ValueError("Campos inválidos")
            updates.update(zip(names, map(str, values)))
        except Exception:
            raise RuntimeError(
                "Connection inválida ou indisponível no Airflow: " + conn_id
            ) from None
    # Uma falha ou sucesso restaura as variáveis anteriores; não existe fallback.
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


@dag(
    dag_id="adventureworks_simples",
    schedule=None,
    start_date=datetime(2026, 10, 21, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    dagrun_timeout=timedelta(minutes=45),
    default_args={
        "retries": 1,
        "retry_delay": timedelta(seconds=30),
        "execution_timeout": timedelta(minutes=15),
    },
    tags=["adventureworks", "incremental"],
)
def vendas():
    @task(task_id="preconditions", multiple_outputs=False)
    def conferir():
        from etl import check

        with conexoes_do_airflow():
            check()
        context = get_current_context()
        # A mesma tentativa lógica conserva o ID mesmo se perder a resposta.
        return str(
            uuid5(NAMESPACE_URL, context["dag"].dag_id + "/" + context["run_id"])
        )

    @task(task_id="incremental_etl", multiple_outputs=False)
    def carregar(execucao_id):
        from etl import run

        with conexoes_do_airflow():
            run(run_id=execucao_id)
        return execucao_id

    @task(task_id="validate_dw", multiple_outputs=False)
    def validar(execucao_id):
        from etl import validate

        with conexoes_do_airflow():
            validate(execucao_id)
        return execucao_id

    @task(task_id="generate_evidence", multiple_outputs=False)
    def registrar(execucao_id):
        import json
        import os
        from pathlib import Path

        from etl import kpis

        context = get_current_context()
        with conexoes_do_airflow():
            result = kpis(execucao_id)
        result["dag_id"] = context["dag"].dag_id
        result["dag_run_id"] = context["run_id"]
        result["tentativa"] = context["ti"].try_number
        folder = Path(os.environ["AIRFLOW_HOME"]) / "saidas" / execucao_id
        folder.mkdir(parents=True, exist_ok=True)
        # UUID do arquivo evita substituir evidências até ao limpar/repetir tarefas.
        from uuid import uuid4

        path = folder / f"kpis-{uuid4()}.json"
        with path.open("x", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
        return {"execucao_id": execucao_id, "arquivo": str(path)}

    registrar(validar(carregar(conferir())))


vendas()

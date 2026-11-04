"""Inicialização do laboratório; não prepara nem carrega os bancos de vendas."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import quote


def registrar_conexoes():
    """Cadastro administrativo inicial; nunca sobrescreve edições da interface."""
    # Imports após a migração: o airflow.cfg e sua chave persistente já existem.
    from airflow.configuration import conf
    from airflow.models.connection import Connection
    from airflow.utils.session import create_session
    from cryptography.fernet import Fernet

    key = conf.get("core", "fernet_key").strip()
    if not key:
        raise RuntimeError("Chave Fernet ausente no volume persistente do Airflow.")
    for part in key.split(","):
        Fernet(part.strip().encode())
    specs = (
        ("adventureworks_source", "mssql", ("SOURCE_HOST", "SOURCE_PORT", "SOURCE_DB", "SOURCE_USER", "MSSQL_SA_PASSWORD")),
        ("adventureworks_dw", "postgres", ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")),
    )
    with create_session() as session:
        for conn_id, conn_type, names in specs:
            if "AIRFLOW_CONN_" + conn_id.upper() in os.environ:
                raise RuntimeError("Remova a sobreposição por ambiente de " + conn_id)
            connection = session.query(Connection).filter_by(conn_id=conn_id).one_or_none()
            if connection is None:
                host, port, database, login, password = (os.environ[name] for name in names)
                connection = Connection(conn_id=conn_id, conn_type=conn_type, host=host,
                                        port=int(port), schema=database, login=login, password=password)
                session.add(connection)
            # Campos existentes também são conferidos; a senha nunca vai para logs.
            if (connection.conn_type != conn_type or
                    not all((connection.host, connection.schema, connection.login, connection.password)) or
                    not isinstance(connection.port, int) or not 1 <= connection.port <= 65535):
                raise RuntimeError("Connection incompleta ou de tipo incorreto: " + conn_id)
            session.flush()
            if not connection.is_encrypted:
                raise RuntimeError("Senha não criptografada na Connection " + conn_id)


def main():
    password = os.environ.get("AIRFLOW_DB_PASSWORD")
    user = os.environ.get("AIRFLOW_USER")
    ui_password = os.environ.get("AIRFLOW_PASSWORD")
    if not all((password, user, ui_password)):
        raise SystemExit("Confira AIRFLOW_DB_PASSWORD, AIRFLOW_USER e AIRFLOW_PASSWORD no .env.")
    if any(character in user for character in ":,\r\n") or user.strip() != user:
        raise SystemExit("AIRFLOW_USER contém caracteres inválidos.")
    # O Simple Auth Manager lê o mapa usuário/senha antes de iniciar a interface.
    path = Path(os.environ["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE"])
    path.parent.mkdir(parents=True, exist_ok=True)
    users = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(users, dict):
        raise SystemExit("O arquivo de senhas do Airflow deve conter um objeto JSON.")
    users[user] = ui_password
    descriptor, temporary = tempfile.mkstemp(prefix=".airflow-passwords-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(users, stream, ensure_ascii=False)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    os.environ["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS"] = f"{user}:admin"
    # A URI fica somente no ambiente do processo, sem aparecer no comando/log.
    os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = (
        "postgresql+psycopg2://airflow:"
        + quote(password, safe="")
        + "@airflow-db:5432/airflow"
    )
    # Migração e cadastro cuidam só dos metadados do Airflow, sem carregar o DW.
    try:
        subprocess.run(["airflow", "db", "migrate"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        registrar_conexoes()
    except Exception:
        raise SystemExit("Inicialização interrompida: confira metadados, Fernet e Connections. Credenciais omitidas.") from None
    os.execvp("airflow", ["airflow", "standalone"])


if __name__ == "__main__":
    main()

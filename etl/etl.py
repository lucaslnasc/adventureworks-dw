"""ETL incremental em duas etapas: origem -> stage (Python) e stage -> DW (SQL).

As mesmas funções atendem à DAG do Airflow (uma tarefa por etapa e grupo) e à
linha de comando (execução sequencial, útil para a primeira carga e testes).
"""

import argparse
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
import pymssql

import origem

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql"
GRUPOS = tuple(origem.GRUPOS)
# Ordem da execução sequencial; na DAG, as dimensões correm em paralelo.
CARGAS = ("dim_produto", "dim_cliente", "dim_territorio", "dim_vendedor", "dim_data", "fato_venda")
VALIDACOES = ("cabecalhos", "datas", "checkpoints")
INDICADORES = (
    "receita_bruta", "descontos", "receita_liquida", "unidades", "pedidos",
    "ticket_medio", "taxa_desconto", "clientes_ativos", "crescimento_mensal", "expedicao_no_prazo",
)


# Decimal vira texto no JSON para preservar a precisão; datas usam o formato ISO.
def json_value(value):
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Tipo não serializável: {type(value).__name__}")


@contextmanager
def banco():
    ausentes = [n for n in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD") if not os.getenv(n)]
    if ausentes:
        raise RuntimeError("Configuração PostgreSQL incompleta: " + ", ".join(ausentes))
    try:
        # libpq lê PGHOST, PGPORT, PGDATABASE, PGUSER e PGPASSWORD.
        with psycopg.connect(autocommit=True, connect_timeout=15) as conn:
            yield conn
    except psycopg.Error as exc:
        detalhe = getattr(getattr(exc, "diag", None), "message_primary", None)
        raise RuntimeError("Operação PostgreSQL falhou" + (f": {detalhe}" if detalhe else ".")) from None


def checkpoint(conn, grupo):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM etl.controle WHERE grupo = %s", (grupo,))
        return cur.fetchone()


def check():
    """Pré-condições somente leitura: estrutura do DW, Change Tracking e checkpoints válidos."""
    with banco() as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        for tabela in ("dw.fato_venda", "dw.dim_data", "etl.controle", "stage.lote"):
            if conn.execute("SELECT to_regclass(%s)", (tabela,)).fetchone()[0] is None:
                raise RuntimeError("DW incompleto. Execute init explicitamente.")
        estados = {g: checkpoint(conn, g) for g in GRUPOS}
    resultado = {}
    with origem.snapshot() as cur:
        for grupo, state in estados.items():
            fonte = origem.estado(
                cur, grupo,
                state["versao"] if state else None,
                state["identidade_origem"] if state else None,
            )
            resultado[grupo] = {"checkpoint": state["versao"] if state else None, "versao_origem": fonte["versao"]}
    return {"pronto": True, "grupos": resultado}


def extrair(grupo, execucao_id, completo=False):
    """Origem -> stage de um grupo. A stage do grupo é trocada em uma única transação."""
    with banco() as conn:
        state = None if completo else checkpoint(conn, grupo)
        anterior = state["versao"] if state else None
        lote = origem.extrair(grupo, anterior, state["identidade_origem"] if state else None)
        linhas = 0
        with conn.transaction():
            # Impede duas extrações do mesmo grupo ao mesmo tempo.
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("stage:" + grupo,))
            with conn.cursor() as cur:
                for tabela, (colunas, rows) in lote["tabelas"].items():
                    cur.execute(f"TRUNCATE stage.{tabela}")
                    with cur.copy(f"COPY stage.{tabela} ({','.join(colunas)}) FROM STDIN") as copy:
                        for row in rows:
                            copy.write_row(row)
                    linhas += len(rows)
            conn.execute(
                """INSERT INTO stage.lote(grupo, execucao_id, versao_de, versao_ate, identidade_origem, linhas)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (grupo) DO UPDATE SET execucao_id = EXCLUDED.execucao_id,
                       versao_de = EXCLUDED.versao_de, versao_ate = EXCLUDED.versao_ate,
                       identidade_origem = EXCLUDED.identidade_origem, linhas = EXCLUDED.linhas,
                       extraido_em = now()""",
                (grupo, UUID(str(execucao_id)), anterior, lote["versao"], lote["identidade"], linhas),
            )
    return {
        "grupo": grupo,
        "modo": "completa" if anterior is None else "incremental",
        "versao_de": anterior,
        "versao_ate": lote["versao"],
        "linhas_stage": {t: len(r) for t, (_, r) in lote["tabelas"].items()},
    }


def executar_sql(caminho):
    """Executa um arquivo de sql/ em uma única transação (o mesmo que a DAG faz)."""
    texto = (SQL / caminho).read_text(encoding="utf-8")
    with banco() as conn, conn.transaction():
        cur = conn.execute(texto)
        # Com vários comandos, o resultado útil é o do último SELECT.
        resultado = None
        while True:
            if cur.description:
                resultado = cur.fetchall()
            if not cur.nextset():
                break
        return resultado


def kpis(execucao_id=None):
    """Lê as dez views e a auditoria da execução no mesmo snapshot."""
    with banco() as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        with conn.cursor(row_factory=dict_row) as cur:
            if execucao_id is None:
                cur.execute("SELECT execucao_id FROM etl.controle ORDER BY atualizado_em DESC LIMIT 1")
                row = cur.fetchone()
                execucao_id = row["execucao_id"] if row else None
            cur.execute(
                "SELECT * FROM etl.carga WHERE execucao_id = %s ORDER BY grupo",
                (str(execucao_id) if execucao_id else None,),
            )
            resultado = {"execucao_id": str(execucao_id) if execucao_id else None, "carga": cur.fetchall(), "indicadores": {}}
            for numero, nome in enumerate(INDICADORES, 1):
                view = f"kpi_{numero:02d}_{nome}"
                cur.execute(f"SELECT * FROM dw.{view}" + (" ORDER BY mes" if numero == 9 else ""))
                resultado["indicadores"][view] = cur.fetchall()
    return json.loads(json.dumps(resultado, default=json_value, ensure_ascii=False))


def run(resync=False):
    """Execução sequencial: extrai os cinco grupos, carrega dimensões, fato e valida."""
    execucao_id = uuid4()
    if not resync:
        check()
    extracoes = [extrair(g, execucao_id, completo=resync) for g in GRUPOS]
    for carga in CARGAS:
        executar_sql(f"carga/{carga}.sql")
    for validacao in VALIDACOES:
        executar_sql(f"qualidade/{validacao}.sql")
    return {"execucao_id": str(execucao_id), "extracoes": extracoes, **{"carga": kpis(execucao_id)["carga"]}}


def init():
    """Cria stage, DW, controle e views de indicadores."""
    with banco() as conn:
        antigo = conn.execute(
            """SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'etl' AND table_name = 'controle' AND column_name = 'pipeline'"""
        ).fetchone()
        if antigo:
            raise RuntimeError(
                "Este banco pertence à versão anterior (sem stage). Recrie os esquemas dw, etl e stage."
            )
        with conn.transaction():
            for arquivo in ("stage.sql", "dw.sql", "kpis.sql"):
                conn.execute((SQL / arquivo).read_text(encoding="utf-8"))
    return {"estrutura": "pronta"}


# Habilitar Change Tracking altera a origem; por isso é uma preparação separada.
def prepare_source():
    conn = origem.conectar()
    try:
        cur = conn.cursor()
        cur.execute((SQL / "origem.sql").read_text(encoding="utf-8"))
        while cur.nextset():
            pass
    except pymssql.Error:
        raise RuntimeError("Preparação da origem falhou; confira banco, tabelas e permissões.") from None
    finally:
        conn.close()
    return {"change_tracking": "preparado"}


# Restauração é explícita e só ocorre se o banco ainda não existir; não usa REPLACE.
def restore():
    nome = os.getenv("SOURCE_DB", "AdventureWorks2016")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,60}", nome):
        raise ValueError("Nome de banco inválido.")
    conn = origem.conectar("master")
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT DB_ID(%s) id", (nome,))
        if cur.fetchone()["id"] is not None:
            return {"restauracao": "ignorada", "motivo": "banco já existente"}
        backup = "/var/opt/mssql/backup/AdventureWorks2016.bak"
        cur.execute("RESTORE FILELISTONLY FROM DISK=%s", (backup,))
        arquivos = list(cur.fetchall())
        if len(arquivos) != 2 or {a["Type"] for a in arquivos} != {"D", "L"}:
            raise RuntimeError("Backup diferente do esperado; restauração não iniciada.")
        parametros = [backup]
        for arquivo in arquivos:
            sufixo = ".mdf" if arquivo["Type"] == "D" else "_log.ldf"
            parametros += [arquivo["LogicalName"], f"/var/opt/mssql/data/{nome}{sufixo}"]
        cur.execute(
            f"RESTORE DATABASE [{nome}] FROM DISK=%s WITH MOVE %s TO %s, MOVE %s TO %s",
            tuple(parametros),
        )
        while cur.nextset():
            pass
    except pymssql.Error:
        raise RuntimeError("Restauração falhou; confira backup, permissões e espaço disponível.") from None
    finally:
        conn.close()
    return {"restauracao": "concluida", "banco": nome}


def main():
    parser = argparse.ArgumentParser(description="AdventureWorks: ETL incremental com stage e dez indicadores")
    parser.add_argument("comando", choices=("restore", "prepare-source", "init", "run", "check", "kpis"))
    parser.add_argument("--resync", action="store_true",
                        help="Relê toda a origem e reconcilia o DW, preservando SKs; somente com run")
    args = parser.parse_args()
    if args.resync and args.comando != "run":
        parser.error("--resync só pode ser usado com run")
    comandos = {"restore": restore, "prepare-source": prepare_source, "init": init, "check": check, "kpis": kpis}
    try:
        resultado = run(resync=args.resync) if args.comando == "run" else comandos[args.comando]()
        print(json.dumps(resultado, default=json_value, ensure_ascii=False, indent=2))
    except Exception as exc:
        mensagem = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__
        parser.exit(1, f"ETL interrompida: {mensagem}\n")


if __name__ == "__main__":
    main()

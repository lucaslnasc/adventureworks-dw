"""ETL incremental: dimensões, fatos e checkpoint em uma transação PostgreSQL."""

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
from psycopg.types.json import Jsonb
import pymssql

import origem

# Caminhos partem do projeto; LOCK identifica a trava compartilhada entre execuções.
ROOT = Path(__file__).resolve().parent.parent
LOCK = 601602603
# O primeiro campo é a chave da origem; os demais são atributos atualizados por SCD Tipo 1.
DIMENSOES = {
    "produto": (
        "produto_id",
        "nome",
        "numero_produto",
        "cor",
        "subcategoria",
        "categoria",
    ),
    "cliente": ("cliente_id", "nome", "tipo"),
    "territorio": ("territorio_id", "nome", "pais_codigo", "grupo"),
    "vendedor": ("vendedor_id", "nome"),
}
# A ordem deve coincidir com a tupla de _item e com o COPY da tabela temporária.
COLUNAS = (
    "pedido_id",
    "item_id",
    "data_pedido_sk",
    "data_vencimento_sk",
    "data_envio_sk",
    "produto_sk",
    "cliente_sk",
    "territorio_sk",
    "vendedor_sk",
    "canal_sk",
    "status",
    "quantidade",
    "preco_unitario",
    "taxa_desconto",
    "receita_liquida",
    "versao_origem",
)
INDICADORES = (
    "receita_bruta",
    "descontos",
    "receita_liquida",
    "unidades",
    "pedidos",
    "ticket_medio",
    "taxa_desconto",
    "clientes_ativos",
    "crescimento_mensal",
    "expedicao_no_prazo",
)


# Decimal vira texto no JSON para preservar a precisão; datas usam o formato ISO.
def json_value(value):
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Tipo não serializável: {type(value).__name__}")


# Abre e fecha a conexão; os blocos conn.transaction() delimitam as escritas atômicas.
@contextmanager
def banco():
    ausentes = [
        nome
        for nome in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
        if not os.getenv(nome)
    ]
    if ausentes:
        raise RuntimeError("Configuração PostgreSQL incompleta: " + ", ".join(ausentes))
    try:
        # libpq lê PGHOST, PGPORT, PGDATABASE, PGUSER e PGPASSWORD.
        with psycopg.connect(autocommit=True, connect_timeout=15) as conn:
            yield conn
    except psycopg.Error:
        raise RuntimeError(
            "Operação PostgreSQL falhou; confira configuração, esquema e integridade dos dados."
        ) from None


# O checkpoint registra até qual versão de Change Tracking a carga foi confirmada.
def checkpoint(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM etl.controle WHERE pipeline='vendas'")
        return cur.fetchone()


# Trava de sessão impede duas cargas simultâneas; fechar a conexão libera a trava.
def bloquear(conn):
    if not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,)).fetchone()[0]:
        raise RuntimeError(
            "Outra operação ETL está em execução. Aguarde antes de repetir."
        )


# Verifica estrutura e validade do checkpoint sem gravar dados nos bancos.
def check():
    """Pré-condições somente leitura; a carga confere novamente sob sua trava."""
    with banco() as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        state = checkpoint(conn)
        for tabela in (
            "dim_data",
            "dim_canal",
            "fato_venda",
            *["dim_" + n for n in DIMENSOES],
        ):
            if (
                conn.execute("SELECT to_regclass(%s)", ("dw." + tabela,)).fetchone()[0]
                is None
            ):
                raise RuntimeError("DW incompleto. Execute init explicitamente.")
        with origem.snapshot() as cur:
            source = origem.estado(
                cur,
                state["versao"] if state else None,
                state["identidade_origem"] if state else None,
            )
        return {
            "pronto": True,
            "versao_origem": source["versao"],
            "checkpoint": state["versao"] if state else None,
        }


# SCD Tipo 1 atualiza atributos na mesma linha: não mantém versões históricas.
def _dimensoes(conn, lote):
    escritos = {}
    for nome, campos in DIMENSOES.items():
        chave = campos[0]
        linhas = lote["dimensoes"][nome]
        vivos = {r[chave] for r in linhas}
        if lote["completo"]:
            atuais = {
                r[0]
                for r in conn.execute(
                    f"SELECT {chave} FROM dw.dim_{nome} WHERE {chave}<>0"
                )
            }
        else:
            atuais = set(lote["afetados"][nome])
        # Ausentes na origem ficam inativos; manter a linha preserva FKs da fato.
        conn.execute(
            f"""UPDATE dw.dim_{nome} SET ativo_origem=false, atualizado_em=now()
            WHERE {chave}=ANY(%s) AND ativo_origem""",
            (sorted(atuais - vivos),),
        )
        alteracoes = ", ".join(f"{c}=EXCLUDED.{c}" for c in campos[1:])
        diferencas = " OR ".join(
            f"d.{c} IS DISTINCT FROM EXCLUDED.{c}" for c in campos[1:]
        )
        consulta = f"""INSERT INTO dw.dim_{nome} AS d ({','.join(campos)})
            VALUES ({','.join(['%s']*len(campos))})
            ON CONFLICT ({chave}) DO UPDATE SET {alteracoes}, ativo_origem=true, atualizado_em=now()
            WHERE NOT d.ativo_origem OR {diferencas}"""
        with conn.cursor() as cur:
            cur.executemany(consulta, [tuple(row[c] for c in campos) for row in linhas])
            escritos[nome] = cur.rowcount
    return escritos


# Preenche os dias do intervalo para os três papéis da data, sem duplicar datas.
def _calendario(conn, itens):
    datas = [
        r[c]
        for r in itens
        for c in ("data_pedido", "data_vencimento", "data_envio")
        if r[c] is not None
    ]
    if not datas:
        return
    minimo, maximo = conn.execute(
        "SELECT min(data),max(data) FROM dw.dim_data"
    ).fetchone()
    inicio = min(min(datas), minimo) if minimo else min(datas)
    fim = max(max(datas), maximo) if maximo else max(datas)
    conn.execute(
        """INSERT INTO dw.dim_data
        SELECT to_char(d,'YYYYMMDD')::integer, d::date, extract(year FROM d),
               extract(quarter FROM d), extract(month FROM d), extract(day FROM d),
               extract(isodow FROM d), date_trunc('month',d)::date
        FROM generate_series(%s::timestamp,%s::timestamp,interval '1 day') d
        ON CONFLICT DO NOTHING""",
        (inicio, fim),
    )


# Valida as medidas com Decimal e converte IDs da origem nas SKs do DW.
def _item(row, mapas, versao):
    q, p, t, liquido = (
        row[c]
        for c in ("quantidade", "preco_unitario", "taxa_desconto", "receita_liquida")
    )
    if (
        q <= 0
        or p < 0
        or not 0 <= t <= 1
        or liquido < 0
        or abs(q * p * (1 - t) - liquido) > Decimal("0.000001")
    ):
        raise ValueError(f"Medidas inválidas no item {row['item_id']}.")
    pedido, vencimento, envio = (
        row[c] for c in ("data_pedido", "data_vencimento", "data_envio")
    )
    if (
        pedido is None
        or vencimento is None
        or vencimento < pedido
        or (envio is not None and envio < pedido)
    ):
        raise ValueError(f"Datas inválidas no pedido {row['pedido_id']}.")
    datas = [
        d.year * 10000 + d.month * 100 + d.day if d else None
        for d in (pedido, vencimento, envio)
    ]
    # Uma dimensão ausente interrompe a carga, evitando uma fato sem referência válida.
    try:
        chaves = [mapas[n][row[n + "_id"]] for n in DIMENSOES]
    except KeyError:
        raise ValueError(f"Dimensão ausente para o item {row['item_id']}.") from None
    return (
        row["pedido_id"],
        row["item_id"],
        *datas,
        *chaves,
        row["canal_sk"],
        row["status"],
        q,
        p,
        t,
        liquido,
        versao,
    )


# Dimensões vêm antes da fato; o chamador mantém tudo dentro da mesma transação.
def _carregar(conn, lote):
    stats = {
        "dimensoes_gravadas": _dimensoes(conn, lote),
        "pedidos_afetados": len(lote["pedidos"]),
        "itens_extraidos": len(lote["itens"]),
        "mudancas_origem": lote["mudancas"],
    }
    _calendario(conn, lote["itens"])
    mapas = {
        n: dict(
            conn.execute(f"SELECT {n}_id,{n}_sk FROM dw.dim_{n} WHERE ativo_origem")
        )
        for n in DIMENSOES
    }
    # A tabela temporária recebe o lote via COPY e desaparece ao concluir a transação.
    conn.execute(
        """CREATE TEMP TABLE lote_venda
        (LIKE dw.fato_venda INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING CONSTRAINTS) ON COMMIT DROP"""
    )
    campos = ",".join(COLUNAS)
    with conn.cursor() as cur, cur.copy(
        f"COPY lote_venda ({campos}) FROM STDIN"
    ) as copy:
        for row in lote["itens"]:
            copy.write_row(_item(row, mapas, lote["versao"]))
    conn.execute("ALTER TABLE lote_venda ADD PRIMARY KEY(pedido_id,item_id)")
    excluir = """DELETE FROM dw.fato_venda f WHERE NOT EXISTS
        (SELECT 1 FROM lote_venda l WHERE l.pedido_id=f.pedido_id AND l.item_id=f.item_id)"""
    # No incremental, só pedidos afetados são reconciliados, inclusive itens excluídos.
    if lote["completo"]:
        stats["itens_excluidos"] = conn.execute(excluir).rowcount
    else:
        stats["itens_excluidos"] = conn.execute(
            excluir + " AND f.pedido_id=ANY(%s)", (lote["pedidos"],)
        ).rowcount
    # A chave pedido/item evita duplicações; só medidas ou relações diferentes geram update.
    alteracoes = ",".join(f"{c}=EXCLUDED.{c}" for c in COLUNAS[2:])
    diferencas = " OR ".join(
        f"f.{c} IS DISTINCT FROM EXCLUDED.{c}" for c in COLUNAS[2:-1]
    )
    stats["itens_gravados"] = conn.execute(f"""INSERT INTO dw.fato_venda AS f ({campos})
        SELECT {campos} FROM lote_venda
        ON CONFLICT(pedido_id,item_id) DO UPDATE SET {alteracoes},carregado_em=now()
        WHERE {diferencas}""").rowcount
    return stats


# Vincula validações e KPIs à execução que corresponde ao checkpoint atual.
def _confirmar(conn, execucao_id):
    state = checkpoint(conn)
    if state is None:
        raise RuntimeError("Ainda não existe carga concluída.")
    identificador = UUID(str(execucao_id)) if execucao_id else state["execucao_id"]
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM etl.execucao WHERE execucao_id=%s", (identificador,))
        registro = cur.fetchone()
    if (
        registro is None
        or registro["status"] != "success"
        or identificador != state["execucao_id"]
        or registro["versao_nova"] != state["versao"]
    ):
        raise RuntimeError(
            "A execução não corresponde ao checkpoint atual. Não use resultados de outra carga."
        )
    return {
        "execucao_id": str(identificador),
        "versao": state["versao"],
        "modo": registro["modo"],
        "estatisticas": registro["estatisticas"],
    }


# Coordena extração, carga e auditoria; resync precisa ser solicitado explicitamente.
def run(run_id=None, resync=False):
    identificador = UUID(str(run_id)) if run_id else uuid4()
    with banco() as conn:
        bloquear(conn)
        anterior = conn.execute(
            "SELECT status FROM etl.execucao WHERE execucao_id=%s", (identificador,)
        ).fetchone()
        if anterior and anterior[0] == "success":
            # Retry após commit e perda da resposta devolve a mesma execução.
            return _confirmar(conn, identificador)
        state = checkpoint(conn)
        if (
            state is None
            and conn.execute("SELECT EXISTS(SELECT 1 FROM dw.fato_venda)").fetchone()[0]
            and not resync
        ):
            raise RuntimeError(
                "Há fatos sem checkpoint. Avalie run --resync explicitamente."
            )
        modo = "resync" if resync else ("incremental" if state else "initial")
        versao = state["versao"] if state and not resync else None
        identidade = state["identidade_origem"] if state and not resync else None
        conn.execute(
            """UPDATE etl.execucao SET status='failed',fim=now(),erro='Processo interrompido'
            WHERE status='running'"""
        )
        conn.execute(
            """INSERT INTO etl.execucao(execucao_id,status,modo,versao_anterior)
            VALUES(%s,'running',%s,%s) ON CONFLICT(execucao_id) DO UPDATE
            SET inicio=now(),fim=NULL,status='running',modo=EXCLUDED.modo,
                versao_anterior=EXCLUDED.versao_anterior,versao_nova=NULL,estatisticas=NULL,erro=NULL""",
            (identificador, modo, state["versao"] if state else None),
        )
        try:
            lote = origem.extrair(versao, identidade)
            # Dados, sucesso e checkpoint fazem commit juntos; falha desfaz os três.
            with conn.transaction():
                stats = _carregar(conn, lote)
                conn.execute(
                    """UPDATE etl.execucao SET status='success',fim=now(),versao_nova=%s,
                    estatisticas=%s WHERE execucao_id=%s""",
                    (lote["versao"], Jsonb(stats), identificador),
                )
                conn.execute(
                    """INSERT INTO etl.controle(pipeline,versao,identidade_origem,execucao_id)
                    VALUES('vendas',%s,%s,%s) ON CONFLICT(pipeline) DO UPDATE
                    SET versao=EXCLUDED.versao,identidade_origem=EXCLUDED.identidade_origem,
                        execucao_id=EXCLUDED.execucao_id,atualizado_em=now()""",
                    (lote["versao"], lote["identidade"], identificador),
                )
            return {
                "execucao_id": str(identificador),
                "versao": lote["versao"],
                "modo": modo,
                "estatisticas": stats,
            }
        # Após o rollback da carga, registra a falha sem avançar o checkpoint.
        except Exception as exc:
            conn.execute(
                """UPDATE etl.execucao SET status='failed',fim=now(),erro=%s
                WHERE execucao_id=%s""",
                (type(exc).__name__, identificador),
            )
            raise


# Verifica se itens do mesmo pedido compartilham cabeçalho e datas coerentes.
def validate(execucao_id):
    with banco() as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        resultado = _confirmar(conn, execucao_id)
        incoerentes = conn.execute("""SELECT count(*) FROM (
            SELECT pedido_id FROM dw.fato_venda GROUP BY pedido_id
            HAVING count(DISTINCT (data_pedido_sk,data_vencimento_sk,data_envio_sk,
                   cliente_sk,territorio_sk,vendedor_sk,canal_sk,status))>1
        ) pedidos""").fetchone()[0]
        datas_invalidas = conn.execute("""SELECT count(*) FROM dw.fato_venda f
            JOIN dw.dim_data p ON p.data_sk=f.data_pedido_sk
            JOIN dw.dim_data v ON v.data_sk=f.data_vencimento_sk
            LEFT JOIN dw.dim_data e ON e.data_sk=f.data_envio_sk
            WHERE v.data<p.data OR e.data<p.data""").fetchone()[0]
        if incoerentes or datas_invalidas:
            raise RuntimeError(
                "Validação falhou: cabeçalhos ou datas incoerentes no DW."
            )
        resultado["itens"] = conn.execute(
            "SELECT count(*) FROM dw.fato_venda"
        ).fetchone()[0]
        resultado["valido"] = True
        return resultado


# Lê as dez views no mesmo snapshot PostgreSQL, sem misturar estados da carga.
def kpis(execucao_id=None):
    with banco() as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        resultado = _confirmar(conn, execucao_id)
        resultado["indicadores"] = {}
        with conn.cursor(row_factory=dict_row) as cur:
            for numero, nome in enumerate(INDICADORES, 1):
                view = f"kpi_{numero:02d}_{nome}"
                cur.execute(
                    f"SELECT * FROM dw.{view}"
                    + (" ORDER BY mes" if numero == 9 else "")
                )
                resultado["indicadores"][view] = cur.fetchall()
        return json.loads(json.dumps(resultado, default=json_value, ensure_ascii=False))


# Cria a estrutura e as views por comando explícito, sob a mesma trava do ETL.
def init():
    with banco() as conn:
        bloquear(conn)
        if conn.execute("SELECT to_regclass('etl.controle')").fetchone()[0]:
            coluna = conn.execute(
                """SELECT 1 FROM information_schema.columns
                WHERE table_schema='etl' AND table_name='controle' AND column_name='execucao_id'"""
            ).fetchone()
            if not coluna:
                raise RuntimeError(
                    "Este banco pertence à versão anterior. Use um banco novo para esta implementação."
                )
        with conn.transaction():
            for arquivo in ("dw.sql", "kpis.sql"):
                conn.execute((ROOT / "sql" / arquivo).read_text(encoding="utf-8"))
    return {"estrutura": "pronta"}


# Habilitar Change Tracking altera a origem; por isso é uma preparação separada.
def prepare_source():
    conn = origem.conectar()
    try:
        cur = conn.cursor()
        cur.execute((ROOT / "sql" / "origem.sql").read_text(encoding="utf-8"))
        while cur.nextset():
            pass
    except pymssql.Error:
        raise RuntimeError(
            "Preparação da origem falhou; confira banco, tabelas e permissões."
        ) from None
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
            raise RuntimeError(
                "Backup diferente do esperado; restauração não iniciada."
            )
        parametros = [backup]
        for arquivo in arquivos:
            sufixo = ".mdf" if arquivo["Type"] == "D" else "_log.ldf"
            parametros += [
                arquivo["LogicalName"],
                f"/var/opt/mssql/data/{nome}{sufixo}",
            ]
        cur.execute(
            f"RESTORE DATABASE [{nome}] FROM DISK=%s WITH MOVE %s TO %s, MOVE %s TO %s",
            tuple(parametros),
        )
        while cur.nextset():
            pass
    except pymssql.Error:
        raise RuntimeError(
            "Restauração falhou; confira backup, permissões e espaço disponível."
        ) from None
    finally:
        conn.close()
    return {"restauracao": "concluida", "banco": nome}


# A CLI seleciona a operação; --resync só vale para run e reconcilia toda a origem.
def main():
    parser = argparse.ArgumentParser(
        description="AdventureWorks: ETL incremental e dez indicadores"
    )
    parser.add_argument(
        "comando", choices=("restore", "prepare-source", "init", "run", "check", "kpis")
    )
    parser.add_argument(
        "--resync",
        action="store_true",
        help="Reconcilia toda a origem, preservando SKs; somente com run",
    )
    args = parser.parse_args()
    if args.resync and args.comando != "run":
        parser.error("--resync só pode ser usado com run")
    comandos = {
        "restore": restore,
        "prepare-source": prepare_source,
        "init": init,
        "check": check,
        "kpis": kpis,
    }
    try:
        resultado = (
            run(resync=args.resync)
            if args.comando == "run"
            else comandos[args.comando]()
        )
        print(json.dumps(resultado, default=json_value, ensure_ascii=False, indent=2))
    except Exception as exc:
        mensagem = (
            str(exc)
            if isinstance(exc, (RuntimeError, ValueError))
            else type(exc).__name__
        )
        parser.exit(1, f"ETL interrompida: {mensagem}\n")


if __name__ == "__main__":
    main()

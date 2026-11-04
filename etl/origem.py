"""Leitura consistente do AdventureWorks e das alterações de Change Tracking."""

from contextlib import contextmanager
import os

import pymssql

# Chaves das dez tabelas que podem alterar fatos ou atributos dimensionais.
TABELAS = {
    "pedido": ("Sales.SalesOrderHeader", "SalesOrderID"),
    "item": ("Sales.SalesOrderDetail", "SalesOrderID, SalesOrderDetailID"),
    "produto": ("Production.Product", "ProductID"),
    "subcategoria": ("Production.ProductSubcategory", "ProductSubcategoryID"),
    "categoria": ("Production.ProductCategory", "ProductCategoryID"),
    "cliente": ("Sales.Customer", "CustomerID"),
    "pessoa": ("Person.Person", "BusinessEntityID"),
    "loja": ("Sales.Store", "BusinessEntityID"),
    "territorio": ("Sales.SalesTerritory", "TerritoryID"),
    "vendedor": ("Sales.SalesPerson", "BusinessEntityID"),
}

# Cada consulta entrega uma dimensão já achatada, sem relações entre dimensões.
DIMENSOES = {
    "produto": """
        SELECT p.ProductID produto_id, p.Name nome, p.ProductNumber numero_produto,
               p.Color cor, COALESCE(s.Name, N'Sem subcategoria') subcategoria,
               COALESCE(c.Name, N'Sem categoria') categoria
        FROM Production.Product p
        LEFT JOIN Production.ProductSubcategory s ON s.ProductSubcategoryID=p.ProductSubcategoryID
        LEFT JOIN Production.ProductCategory c ON c.ProductCategoryID=s.ProductCategoryID
    """,
    "cliente": """
        SELECT c.CustomerID cliente_id,
               COALESCE(s.Name, NULLIF(LTRIM(RTRIM(CONCAT(p.FirstName,N' ',p.MiddleName,N' ',p.LastName))),N''), N'Não informado') nome,
               CASE WHEN c.StoreID IS NOT NULL THEN N'Loja'
                    WHEN c.PersonID IS NOT NULL THEN N'Pessoa' ELSE N'Não informado' END tipo
        FROM Sales.Customer c
        LEFT JOIN Person.Person p ON p.BusinessEntityID=c.PersonID
        LEFT JOIN Sales.Store s ON s.BusinessEntityID=c.StoreID
    """,
    "territorio": """
        SELECT TerritoryID territorio_id, Name nome, CountryRegionCode pais_codigo,
               [Group] grupo FROM Sales.SalesTerritory
    """,
    "vendedor": """
        SELECT s.BusinessEntityID vendedor_id,
               LTRIM(RTRIM(CONCAT(p.FirstName,N' ',p.MiddleName,N' ',p.LastName))) nome
        FROM Sales.SalesPerson s JOIN Person.Person p ON p.BusinessEntityID=s.BusinessEntityID
    """,
}

# Mudanças em categoria, pessoa ou loja também afetam atributos de suas dimensões.
IMPACTOS = {
    "produto": """
        SELECT ProductID id FROM #produto
        UNION SELECT p.ProductID FROM Production.Product p
            JOIN #subcategoria s ON s.ProductSubcategoryID=p.ProductSubcategoryID
        UNION SELECT p.ProductID FROM Production.Product p
            JOIN Production.ProductSubcategory s ON s.ProductSubcategoryID=p.ProductSubcategoryID
            JOIN #categoria c ON c.ProductCategoryID=s.ProductCategoryID
    """,
    "cliente": """
        SELECT CustomerID id FROM #cliente
        UNION SELECT c.CustomerID FROM Sales.Customer c JOIN #pessoa p ON p.BusinessEntityID=c.PersonID
        UNION SELECT c.CustomerID FROM Sales.Customer c JOIN #loja l ON l.BusinessEntityID=c.StoreID
    """,
    "territorio": "SELECT TerritoryID id FROM #territorio",
    "vendedor": """
        SELECT BusinessEntityID id FROM #vendedor
        UNION SELECT s.BusinessEntityID FROM Sales.SalesPerson s JOIN #pessoa p ON p.BusinessEntityID=s.BusinessEntityID
    """,
}

# Cada linha é um item; dados do cabeçalho se repetem entre itens do mesmo pedido.
ITENS = """
    SELECT h.SalesOrderID pedido_id, i.SalesOrderDetailID item_id,
           CAST(h.OrderDate AS date) data_pedido, CAST(h.DueDate AS date) data_vencimento,
           CAST(h.ShipDate AS date) data_envio, i.ProductID produto_id,
           h.CustomerID cliente_id, COALESCE(h.TerritoryID,0) territorio_id,
           COALESCE(h.SalesPersonID,0) vendedor_id, CAST(h.OnlineOrderFlag AS int) canal_sk,
           h.Status status, i.OrderQty quantidade, i.UnitPrice preco_unitario,
           i.UnitPriceDiscount taxa_desconto, i.LineTotal receita_liquida
    FROM Sales.SalesOrderHeader h
    JOIN Sales.SalesOrderDetail i ON i.SalesOrderID=h.SalesOrderID
"""


# Obtém credenciais do ambiente; mensagens de falha não mostram a senha.
def conectar(database=None):
    obrigatorias = (
        "SOURCE_HOST",
        "SOURCE_PORT",
        "SOURCE_DB",
        "SOURCE_USER",
        "MSSQL_SA_PASSWORD",
    )
    ausentes = [nome for nome in obrigatorias if not os.getenv(nome)]
    if ausentes:
        raise RuntimeError("Configuração SQL Server incompleta: " + ", ".join(ausentes))
    try:
        return pymssql.connect(
            server=os.environ["SOURCE_HOST"],
            port=int(os.environ["SOURCE_PORT"]),
            user=os.environ["SOURCE_USER"],
            password=os.environ["MSSQL_SA_PASSWORD"],
            database=database or os.environ["SOURCE_DB"],
            charset="UTF-8",
            autocommit=True,
            login_timeout=15,
            timeout=180,
        )
    except pymssql.Error:
        raise RuntimeError(
            "Não foi possível conectar ao SQL Server; confira a configuração."
        ) from None


# O snapshot lê versões e dados em um estado consistente, mesmo com alterações concorrentes.
@contextmanager
def snapshot():
    conn = conectar()
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SET TRANSACTION ISOLATION LEVEL SNAPSHOT; BEGIN TRANSACTION;")
        yield cur
        cur.execute("COMMIT TRANSACTION;")
    except pymssql.Error:
        raise RuntimeError(
            "Leitura SQL Server falhou; confira permissões, tabelas e isolamento snapshot."
        ) from None
    finally:
        # Fechar a conexão também desfaz uma transação de leitura interrompida.
        conn.close()


# A retenção pode invalidar o checkpoint; identidade e versões impedem continuidade insegura.
def estado(cur, anterior=None, identidade=None):
    """Versão mínima, identidade e versão atual são lidas no mesmo snapshot."""
    inicios = []
    for tabela, _ in TABELAS.values():
        cur.execute(
            """SELECT CHANGE_TRACKING_MIN_VALID_VERSION(OBJECT_ID(%s)) minimo,
            (SELECT begin_version FROM sys.change_tracking_tables
             WHERE object_id=OBJECT_ID(%s)) inicio""",
            (tabela, tabela),
        )
        row = cur.fetchone()
        if row["minimo"] is None or row["inicio"] is None:
            raise RuntimeError(
                "Change Tracking ausente. Execute prepare-source explicitamente."
            )
        if anterior is not None and anterior < row["minimo"]:
            raise RuntimeError(
                "Checkpoint expirado. Avalie uma execução explícita com run --resync."
            )
        inicios.append(str(row["inicio"]))
    cur.execute("SELECT CHANGE_TRACKING_CURRENT_VERSION() versao")
    versao = cur.fetchone()["versao"]
    if versao is None or (anterior is not None and anterior > versao):
        raise RuntimeError("Versão da origem incompatível com o checkpoint.")
    cur.execute(
        """SELECT CONVERT(nvarchar(128),value) epoca FROM sys.extended_properties
        WHERE class=0 AND name=N'DWSourceEpoch'"""
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            "Origem sem identificação. Execute prepare-source explicitamente."
        )
    atual = "|".join([row["epoca"], *inicios])
    if identidade is not None and atual != identidade:
        raise RuntimeError(
            "A identidade da origem mudou. Avalie run --resync explicitamente."
        )
    return {"versao": versao, "identidade": atual}


# Sem versão anterior lê tudo; com checkpoint, busca chaves alteradas via Change Tracking.
def extrair(anterior=None, identidade=None):
    with snapshot() as cur:
        lote = {
            **estado(cur, anterior, identidade),
            "completo": anterior is None,
            "dimensoes": {},
            "afetados": {},
            "mudancas": {},
        }
        # CT informa chaves afetadas; os valores atuais são consultados nas tabelas da origem.
        if anterior is not None:
            # Somente constantes do módulo formam identificadores SQL.
            for nome, (tabela, chave) in TABELAS.items():
                cur.execute(
                    f"SELECT {chave} INTO #{nome} FROM CHANGETABLE(CHANGES {tabela}, %s) ct",
                    (anterior,),
                )
                cur.execute(f"SELECT COUNT(*) n FROM #{nome}")
                lote["mudancas"][nome] = cur.fetchone()["n"]
        # Expande alterações indiretas para atualizar dimensões achatadas por SCD Tipo 1.
        for nome, consulta in DIMENSOES.items():
            if anterior is not None:
                cur.execute(
                    f"SELECT id INTO #afetados_{nome} FROM ({IMPACTOS[nome]}) x"
                )
                cur.execute(f"SELECT id FROM #afetados_{nome}")
                lote["afetados"][nome] = [r["id"] for r in cur.fetchall()]
                consulta = f"SELECT * FROM ({consulta}) d WHERE {nome}_id IN (SELECT id FROM #afetados_{nome})"
            cur.execute(consulta)
            lote["dimensoes"][nome] = list(cur.fetchall())
        # Relê todos os itens dos pedidos afetados para reconhecer também exclusões no destino.
        consulta = ITENS
        if anterior is not None:
            cur.execute(
                "SELECT SalesOrderID INTO #pedidos FROM #pedido UNION SELECT SalesOrderID FROM #item"
            )
            cur.execute("SELECT SalesOrderID FROM #pedidos")
            lote["pedidos"] = [r["SalesOrderID"] for r in cur.fetchall()]
            consulta += " WHERE h.SalesOrderID IN (SELECT SalesOrderID FROM #pedidos)"
        cur.execute(consulta)
        lote["itens"] = list(cur.fetchall())
        if anterior is None:
            lote["pedidos"] = sorted({r["pedido_id"] for r in lote["itens"]})
        return lote

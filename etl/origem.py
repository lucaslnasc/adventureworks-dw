"""Leitura do AdventureWorks por grupo, usando Change Tracking e isolamento snapshot.

Esta é a única parte do pipeline que acessa o banco de produção. Cada grupo lê só as
chaves alteradas desde o seu checkpoint (buscas por chave primária) e devolve as linhas
no formato da stage. Nenhuma regra de negócio é aplicada aqui.
"""

from contextlib import contextmanager
import os

import pymssql

# Cada grupo tem: as tabelas monitoradas, as chaves afetadas (carga completa ou
# incremental) e a consulta que monta as linhas de cada tabela da stage.
# %(versao)s é o checkpoint do grupo. Na consulta de dados, a linha ausente na
# origem (LEFT JOIN nulo) é uma exclusão: operacao = 'D'.
GRUPOS = {
    "produto": {
        "tabelas": ("Production.Product", "Production.ProductSubcategory", "Production.ProductCategory"),
        "chaves": [(
            "chaves", "id",
            "SELECT ProductID id, 'I' op FROM Production.Product",
            """SELECT ct.ProductID id, ct.SYS_CHANGE_OPERATION op
               FROM CHANGETABLE(CHANGES Production.Product, %(versao)s) ct
               UNION ALL
               SELECT p.ProductID, 'U' FROM Production.Product p
               JOIN CHANGETABLE(CHANGES Production.ProductSubcategory, %(versao)s) ct
                 ON ct.ProductSubcategoryID = p.ProductSubcategoryID
               UNION ALL
               SELECT p.ProductID, 'U' FROM Production.Product p
               JOIN Production.ProductSubcategory s ON s.ProductSubcategoryID = p.ProductSubcategoryID
               JOIN CHANGETABLE(CHANGES Production.ProductCategory, %(versao)s) ct
                 ON ct.ProductCategoryID = s.ProductCategoryID""",
        )],
        "stage": {
            "produto": """
                SELECT CASE WHEN p.ProductID IS NULL THEN 'D' WHEN k.op = 'I' THEN 'I' ELSE 'U' END operacao,
                       k.id product_id, p.Name name, p.ProductNumber product_number, p.Color color,
                       s.Name subcategoria, c.Name categoria
                FROM #chaves k
                LEFT JOIN Production.Product p ON p.ProductID = k.id
                LEFT JOIN Production.ProductSubcategory s ON s.ProductSubcategoryID = p.ProductSubcategoryID
                LEFT JOIN Production.ProductCategory c ON c.ProductCategoryID = s.ProductCategoryID""",
        },
    },
    "cliente": {
        "tabelas": ("Sales.Customer", "Person.Person", "Sales.Store"),
        "chaves": [(
            "chaves", "id",
            "SELECT CustomerID id, 'I' op FROM Sales.Customer",
            """SELECT ct.CustomerID id, ct.SYS_CHANGE_OPERATION op
               FROM CHANGETABLE(CHANGES Sales.Customer, %(versao)s) ct
               UNION ALL
               SELECT c.CustomerID, 'U' FROM Sales.Customer c
               JOIN CHANGETABLE(CHANGES Person.Person, %(versao)s) ct ON ct.BusinessEntityID = c.PersonID
               UNION ALL
               SELECT c.CustomerID, 'U' FROM Sales.Customer c
               JOIN CHANGETABLE(CHANGES Sales.Store, %(versao)s) ct ON ct.BusinessEntityID = c.StoreID""",
        )],
        "stage": {
            "cliente": """
                SELECT CASE WHEN c.CustomerID IS NULL THEN 'D' WHEN k.op = 'I' THEN 'I' ELSE 'U' END operacao,
                       k.id customer_id, c.PersonID person_id, c.StoreID store_id,
                       p.FirstName first_name, p.MiddleName middle_name, p.LastName last_name,
                       s.Name store_name
                FROM #chaves k
                LEFT JOIN Sales.Customer c ON c.CustomerID = k.id
                LEFT JOIN Person.Person p ON p.BusinessEntityID = c.PersonID
                LEFT JOIN Sales.Store s ON s.BusinessEntityID = c.StoreID""",
        },
    },
    "territorio": {
        "tabelas": ("Sales.SalesTerritory",),
        "chaves": [(
            "chaves", "id",
            "SELECT TerritoryID id, 'I' op FROM Sales.SalesTerritory",
            """SELECT ct.TerritoryID id, ct.SYS_CHANGE_OPERATION op
               FROM CHANGETABLE(CHANGES Sales.SalesTerritory, %(versao)s) ct""",
        )],
        "stage": {
            "territorio": """
                SELECT CASE WHEN t.TerritoryID IS NULL THEN 'D' WHEN k.op = 'I' THEN 'I' ELSE 'U' END operacao,
                       k.id territory_id, t.Name name, t.CountryRegionCode country_region_code,
                       t.[Group] grupo
                FROM #chaves k
                LEFT JOIN Sales.SalesTerritory t ON t.TerritoryID = k.id""",
        },
    },
    "vendedor": {
        "tabelas": ("Sales.SalesPerson", "Person.Person"),
        "chaves": [(
            "chaves", "id",
            "SELECT BusinessEntityID id, 'I' op FROM Sales.SalesPerson",
            """SELECT ct.BusinessEntityID id, ct.SYS_CHANGE_OPERATION op
               FROM CHANGETABLE(CHANGES Sales.SalesPerson, %(versao)s) ct
               UNION ALL
               SELECT s.BusinessEntityID, 'U' FROM Sales.SalesPerson s
               JOIN CHANGETABLE(CHANGES Person.Person, %(versao)s) ct
                 ON ct.BusinessEntityID = s.BusinessEntityID""",
        )],
        "stage": {
            "vendedor": """
                SELECT CASE WHEN s.BusinessEntityID IS NULL THEN 'D' WHEN k.op = 'I' THEN 'I' ELSE 'U' END operacao,
                       k.id business_entity_id, p.FirstName first_name, p.MiddleName middle_name,
                       p.LastName last_name
                FROM #chaves k
                LEFT JOIN Sales.SalesPerson s ON s.BusinessEntityID = k.id
                LEFT JOIN Person.Person p ON p.BusinessEntityID = s.BusinessEntityID""",
        },
    },
    # Cabeçalho e itens ficam no mesmo grupo (mesmo snapshot): todo item alterado
    # chega à stage junto com o cabeçalho atual do seu pedido.
    "vendas": {
        "tabelas": ("Sales.SalesOrderHeader", "Sales.SalesOrderDetail"),
        "chaves": [
            (
                "itens", "pedido, item",
                "SELECT SalesOrderID pedido, SalesOrderDetailID item, 'I' op FROM Sales.SalesOrderDetail",
                """SELECT ct.SalesOrderID pedido, ct.SalesOrderDetailID item, ct.SYS_CHANGE_OPERATION op
                   FROM CHANGETABLE(CHANGES Sales.SalesOrderDetail, %(versao)s) ct""",
            ),
            (
                "pedidos", "id",
                "SELECT SalesOrderID id, 'I' op FROM Sales.SalesOrderHeader",
                """SELECT ct.SalesOrderID id, ct.SYS_CHANGE_OPERATION op
                   FROM CHANGETABLE(CHANGES Sales.SalesOrderHeader, %(versao)s) ct
                   UNION ALL
                   SELECT pedido, 'U' FROM #itens""",
            ),
        ],
        "stage": {
            "pedido": """
                SELECT CASE WHEN h.SalesOrderID IS NULL THEN 'D' WHEN k.op = 'I' THEN 'I' ELSE 'U' END operacao,
                       k.id sales_order_id, CAST(h.OrderDate AS date) order_date,
                       CAST(h.DueDate AS date) due_date, CAST(h.ShipDate AS date) ship_date,
                       h.CustomerID customer_id, h.TerritoryID territory_id,
                       h.SalesPersonID sales_person_id, h.OnlineOrderFlag online_order_flag, h.Status status
                FROM #pedidos k
                LEFT JOIN Sales.SalesOrderHeader h ON h.SalesOrderID = k.id""",
            "item": """
                SELECT CASE WHEN d.SalesOrderDetailID IS NULL THEN 'D' WHEN k.op = 'I' THEN 'I' ELSE 'U' END operacao,
                       k.pedido sales_order_id, k.item sales_order_detail_id, d.ProductID product_id,
                       d.OrderQty order_qty, d.UnitPrice unit_price,
                       d.UnitPriceDiscount unit_price_discount, d.LineTotal line_total
                FROM #itens k
                LEFT JOIN Sales.SalesOrderDetail d
                  ON d.SalesOrderID = k.pedido AND d.SalesOrderDetailID = k.item""",
        },
    },
}


# Obtém credenciais do ambiente; mensagens de falha não mostram a senha.
def conectar(database=None):
    obrigatorias = ("SOURCE_HOST", "SOURCE_PORT", "SOURCE_DB", "SOURCE_USER", "MSSQL_SA_PASSWORD")
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
        raise RuntimeError("Não foi possível conectar ao SQL Server; confira a configuração.") from None


# O snapshot lê versões e dados em um estado consistente, sem bloquear quem grava na origem.
@contextmanager
def snapshot():
    conn = conectar()
    try:
        cur = conn.cursor()
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


def estado(cur, grupo, anterior=None, identidade=None):
    """Versão atual e identidade das tabelas do grupo, conferidas contra o checkpoint."""
    inicios = []
    for tabela in GRUPOS[grupo]["tabelas"]:
        cur.execute(
            """SELECT CHANGE_TRACKING_MIN_VALID_VERSION(OBJECT_ID(%s)),
                      (SELECT begin_version FROM sys.change_tracking_tables
                       WHERE object_id = OBJECT_ID(%s))""",
            (tabela, tabela),
        )
        minimo, inicio = cur.fetchone()
        if minimo is None or inicio is None:
            raise RuntimeError("Change Tracking ausente. Execute prepare-source explicitamente.")
        if anterior is not None and anterior < minimo:
            raise RuntimeError(
                f"Checkpoint de {grupo} expirado. Avalie uma execução explícita com run --resync."
            )
        inicios.append(str(inicio))
    cur.execute("SELECT CHANGE_TRACKING_CURRENT_VERSION()")
    versao = cur.fetchone()[0]
    if versao is None or (anterior is not None and anterior > versao):
        raise RuntimeError(f"Versão da origem incompatível com o checkpoint de {grupo}.")
    cur.execute(
        """SELECT CONVERT(nvarchar(128), value) FROM sys.extended_properties
           WHERE class = 0 AND name = N'DWSourceEpoch'"""
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Origem sem identificação. Execute prepare-source explicitamente.")
    atual = "|".join([row[0], *inicios])
    if identidade is not None and atual != identidade:
        raise RuntimeError(f"A identidade da origem mudou ({grupo}). Avalie run --resync explicitamente.")
    return {"versao": versao, "identidade": atual}


def extrair(grupo, anterior=None, identidade=None):
    """Lê o grupo em um único snapshot. Sem checkpoint, lê todas as chaves."""
    definicao = GRUPOS[grupo]
    with snapshot() as cur:
        lote = estado(cur, grupo, anterior, identidade)
        # 1. Chaves afetadas, sem duplicatas (MIN prioriza D < I < U).
        for nome, colunas, completa, incremental in definicao["chaves"]:
            if anterior is None:
                cur.execute(
                    f"SELECT {colunas}, MIN(op) op INTO #{nome} FROM ({completa}) x GROUP BY {colunas}"
                )
            else:
                cur.execute(
                    f"SELECT {colunas}, MIN(op) op INTO #{nome} FROM ({incremental}) x GROUP BY {colunas}",
                    {"versao": anterior},
                )
        # 2. Linhas atuais dessas chaves, no formato da stage.
        lote["tabelas"] = {}
        for tabela, consulta in definicao["stage"].items():
            cur.execute(consulta)
            colunas = [c[0] for c in cur.description]
            lote["tabelas"][tabela] = (colunas, cur.fetchall())
    return lote

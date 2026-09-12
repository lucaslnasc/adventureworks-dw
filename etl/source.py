"""Snapshot consistente e identificação de dependências de dimensões achatadas."""
from dataclasses import dataclass
import os
import pymssql
from .transform import checked_version

TABLES = {
    'header': ('Sales.SalesOrderHeader', 'SalesOrderID'),
    'detail': ('Sales.SalesOrderDetail', 'SalesOrderID,SalesOrderDetailID'),
    'product': ('Production.Product', 'ProductID'),
    'subcategory': ('Production.ProductSubcategory', 'ProductSubcategoryID'),
    'category': ('Production.ProductCategory', 'ProductCategoryID'),
    'customer': ('Sales.Customer', 'CustomerID'),
    'person': ('Person.Person', 'BusinessEntityID'),
    'store': ('Sales.Store', 'BusinessEntityID'),
    'territory': ('Sales.SalesTerritory', 'TerritoryID'),
    'seller': ('Sales.SalesPerson', 'BusinessEntityID'),
}

DIMENSIONS = {
 'produto': ('''SELECT p.ProductID AS produto_id,p.Name AS nome,
 p.ProductNumber AS numero_produto,p.Color AS cor,
 COALESCE(s.Name,N'Sem subcategoria') AS subcategoria,
 COALESCE(c.Name,N'Sem categoria') AS categoria
 FROM Production.Product p
 LEFT JOIN Production.ProductSubcategory s ON s.ProductSubcategoryID=p.ProductSubcategoryID
 LEFT JOIN Production.ProductCategory c ON c.ProductCategoryID=s.ProductCategoryID''', 'p.ProductID', '''
 SELECT ProductID AS id FROM #ct_product
 UNION SELECT p.ProductID FROM Production.Product p
 JOIN #ct_subcategory s ON s.ProductSubcategoryID=p.ProductSubcategoryID
 UNION SELECT p.ProductID FROM Production.Product p
 JOIN Production.ProductSubcategory s ON s.ProductSubcategoryID=p.ProductSubcategoryID
 JOIN #ct_category c ON c.ProductCategoryID=s.ProductCategoryID'''),
 'cliente': ('''SELECT c.CustomerID AS cliente_id,
 COALESCE(s.Name,NULLIF(LTRIM(RTRIM(CONCAT(p.FirstName,N' ',p.MiddleName,N' ',p.LastName))),N''),N'Não informado') AS nome,
 CASE WHEN c.StoreID IS NOT NULL THEN N'Loja' WHEN c.PersonID IS NOT NULL THEN N'Pessoa' ELSE N'Não informado' END AS tipo
 FROM Sales.Customer c
 LEFT JOIN Person.Person p ON p.BusinessEntityID=c.PersonID
 LEFT JOIN Sales.Store s ON s.BusinessEntityID=c.StoreID''','c.CustomerID', '''
 SELECT CustomerID AS id FROM #ct_customer
 UNION SELECT c.CustomerID FROM Sales.Customer c JOIN #ct_person p ON p.BusinessEntityID=c.PersonID
 UNION SELECT c.CustomerID FROM Sales.Customer c JOIN #ct_store s ON s.BusinessEntityID=c.StoreID'''),
 'territorio': ('''SELECT t.TerritoryID AS territorio_id,t.Name AS nome,
 t.CountryRegionCode AS pais_codigo,t.[Group] AS grupo
 FROM Sales.SalesTerritory t''','t.TerritoryID','SELECT TerritoryID AS id FROM #ct_territory'),
 'vendedor': ('''SELECT s.BusinessEntityID AS vendedor_id,
 LTRIM(RTRIM(CONCAT(p.FirstName,N' ',p.MiddleName,N' ',p.LastName))) AS nome
 FROM Sales.SalesPerson s JOIN Person.Person p ON p.BusinessEntityID=s.BusinessEntityID''',
 's.BusinessEntityID','''SELECT BusinessEntityID AS id FROM #ct_seller
 UNION SELECT s.BusinessEntityID FROM Sales.SalesPerson s JOIN #ct_person p ON p.BusinessEntityID=s.BusinessEntityID'''),
}

FACT_SELECT = '''SELECT h.SalesOrderID AS pedido_id,d.SalesOrderDetailID AS item_id,
 CONVERT(date,h.OrderDate) AS data_pedido,CONVERT(date,h.DueDate) AS data_vencimento,
 CONVERT(date,h.ShipDate) AS data_envio,
 d.ProductID AS produto_id,h.CustomerID AS cliente_id,
 COALESCE(h.TerritoryID,0) AS territorio_id,COALESCE(h.SalesPersonID,0) AS vendedor_id,
 CONVERT(int,h.OnlineOrderFlag) AS canal_sk,h.Status AS status,
 d.OrderQty AS quantidade,d.UnitPrice AS preco_unitario,
 d.UnitPriceDiscount AS taxa_desconto,d.LineTotal AS receita_liquida
 FROM Sales.SalesOrderHeader h
 JOIN Sales.SalesOrderDetail d ON d.SalesOrderID=h.SalesOrderID'''


def connect(database=None, autocommit=False):
    return pymssql.connect(
        server=os.getenv('SOURCE_HOST', 'localhost'),
        port=int(os.getenv('SOURCE_PORT', '14330')),
        user=os.getenv('SOURCE_USER', 'sa'),
        password=os.environ['MSSQL_SA_PASSWORD'],
        database=database or os.getenv('SOURCE_DB', 'AdventureWorks2016'),
        charset='UTF-8', login_timeout=30, timeout=180,
        autocommit=autocommit)


@dataclass
class Batch:
    version: int
    identity: str
    full: bool
    dimensions: dict
    affected_dimensions: dict
    order_ids: list
    facts: list
    changes: dict


def extract(last, expected_identity=None):
    """Transação somente leitura na origem. Temporárias ficam no tempdb da sessão."""
    conn = connect(autocommit=True)
    cur = conn.cursor(as_dict=True)
    try:
        if last is not None:
            # CREATE INDEX não é permitido dentro de uma transação SNAPSHOT.
            # Prepare a temporária vazia antes; leia as mudanças só no snapshot.
            cur.execute('''CREATE TABLE #orders (SalesOrderID int NOT NULL);
                CREATE UNIQUE CLUSTERED INDEX ix_orders ON #orders(SalesOrderID);''')
        cur.execute('SET TRANSACTION ISOLATION LEVEL SNAPSHOT; BEGIN TRANSACTION;')
        minimums = []
        begins = []
        for table, _ in TABLES.values():
            cur.execute('''SELECT CHANGE_TRACKING_MIN_VALID_VERSION(OBJECT_ID(%s)) AS minimum,
                (SELECT begin_version FROM sys.change_tracking_tables WHERE object_id=OBJECT_ID(%s)) AS begin_version''', (table, table))
            info = cur.fetchone()
            minimums.append(info['minimum'])
            begins.append(str(info['begin_version']))
        cur.execute('SELECT CHANGE_TRACKING_CURRENT_VERSION() AS version')
        version = cur.fetchone()['version']
        checked_version(last, version, minimums)
        cur.execute("SELECT CONVERT(nvarchar(128),value) AS epoch FROM sys.extended_properties WHERE class=0 AND name=N'DWSourceEpoch'")
        epoch = cur.fetchone()
        if not epoch:
            raise RuntimeError('Execute prepare-source antes da carga')
        identity = epoch['epoch'] + '|' + '|'.join(begins)
        if expected_identity is not None and identity != expected_identity:
            raise RuntimeError('Identidade da origem mudou. Requer run --resync.')
        changes = {}
        if last is not None:
            for key, (table, columns) in TABLES.items():
                # Identificadores vêm exclusivamente das constantes deste módulo.
                cur.execute(f'''SELECT {columns},SYS_CHANGE_OPERATION AS operation
                    INTO #ct_{key} FROM CHANGETABLE(CHANGES {table}, %s) ct''', (last,))
                cur.execute(f'SELECT COUNT(*) AS n FROM #ct_{key}')
                changes[key] = cur.fetchone()['n']
        dims, affected = {}, {}
        for name, (query, key, impact) in DIMENSIONS.items():
            if last is None:
                cur.execute(query)
                dims[name] = list(cur.fetchall())
                affected[name] = [r[name+'_id'] for r in dims[name]]
            else:
                cur.execute(f'SELECT id INTO #imp_{name} FROM ({impact}) ids')
                cur.execute(f'SELECT id FROM #imp_{name}')
                affected[name] = [r['id'] for r in cur.fetchall()]
                cur.execute(query + f' WHERE {key} IN (SELECT id FROM #imp_{name})')
                dims[name] = list(cur.fetchall())
        if last is None:
            cur.execute(FACT_SELECT)
            facts = list(cur.fetchall())
            order_ids = sorted({r['pedido_id'] for r in facts})
        else:
            cur.execute('''INSERT INTO #orders (SalesOrderID)
                SELECT SalesOrderID FROM #ct_header
                UNION SELECT SalesOrderID FROM #ct_detail;''')
            cur.execute('SELECT SalesOrderID FROM #orders')
            order_ids = [r['SalesOrderID'] for r in cur.fetchall()]
            cur.execute(FACT_SELECT + ' WHERE h.SalesOrderID IN (SELECT SalesOrderID FROM #orders)')
            facts = list(cur.fetchall())
        cur.execute('COMMIT TRANSACTION')
        return Batch(version, identity, last is None, dims, affected, order_ids, facts, changes)
    except Exception:
        try:
            cur.execute('IF @@TRANCOUNT>0 ROLLBACK TRANSACTION')
        except Exception:
            pass
        raise
    finally:
        conn.close()

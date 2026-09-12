-- SOMENTE na cópia didática AdventureWorks2016 deste projeto.
-- Execute uma etapa por vez no DBeaver e faça COMMIT antes de rodar a ETL.
-- Objetos de apoio não participam do DW nem do Change Tracking.

-- ETAPA A: guardar um item e um nome de categoria para restauração posterior.
IF OBJECT_ID('dbo.DWDemoBackup') IS NOT NULL
    THROW 51000,'Demonstração já iniciada. Execute a restauração da etapa D.',1;
SELECT TOP(1) d.SalesOrderID,d.SalesOrderDetailID,d.OrderQty,d.ModifiedDate
INTO dbo.DWDemoBackup
FROM Sales.SalesOrderDetail d JOIN Sales.SalesOrderHeader h ON h.SalesOrderID=d.SalesOrderID
WHERE h.Status=5 AND d.OrderQty<100 ORDER BY d.SalesOrderDetailID;
SELECT TOP(1) ProductCategoryID,Name INTO dbo.DWDemoCategoryBackup
FROM Production.ProductCategory ORDER BY ProductCategoryID;
SELECT * FROM dbo.DWDemoBackup;

-- ETAPA B: alterar quantidade SEM atribuir ModifiedDate.
-- O CT registra o UPDATE; triggers nativas podem atualizar outras tabelas.
UPDATE d SET OrderQty=d.OrderQty+1
FROM Sales.SalesOrderDetail d JOIN dbo.DWDemoBackup b
ON b.SalesOrderID=d.SalesOrderID AND b.SalesOrderDetailID=d.SalesOrderDetailID;
-- COMMIT (se autocommit estiver desligado). Rodar a ETL e conferir receita/quantidade.

-- ETAPA C: mudança em tabela dependente, sem tocar Product.ModifiedDate.
UPDATE c SET Name=LEFT(c.Name,35)+N' DW demo'
FROM Production.ProductCategory c JOIN dbo.DWDemoCategoryBackup b ON b.ProductCategoryID=c.ProductCategoryID;
-- COMMIT. Rodar a ETL: categorias em dim_produto mudam, SKs são preservadas.

-- ETAPA D: reverter os valores demonstrados e remover SOMENTE o apoio da demonstração.
UPDATE d SET OrderQty=b.OrderQty,ModifiedDate=b.ModifiedDate
FROM Sales.SalesOrderDetail d JOIN dbo.DWDemoBackup b
ON b.SalesOrderID=d.SalesOrderID AND b.SalesOrderDetailID=d.SalesOrderDetailID;
UPDATE c SET Name=b.Name FROM Production.ProductCategory c
JOIN dbo.DWDemoCategoryBackup b ON b.ProductCategoryID=c.ProductCategoryID;
DROP TABLE dbo.DWDemoBackup;
DROP TABLE dbo.DWDemoCategoryBackup;
-- COMMIT. Rodar ETL e verify. Triggers de auditoria do OLTP podem manter eventos da demonstração.

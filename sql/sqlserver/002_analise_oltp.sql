-- DBeaver: conexão SQL Server, banco AdventureWorks2016.
-- Catálogo real do backup: a figura de 2008 é referência, não contrato de versão.
SELECT s.name AS esquema,t.name AS tabela,c.column_id,c.name AS coluna,
 ty.name AS tipo,c.max_length,c.precision,c.scale,c.is_nullable,
 CAST(ep.value AS nvarchar(4000)) AS descricao
FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.columns c ON c.object_id=t.object_id
JOIN sys.types ty ON ty.user_type_id=c.user_type_id
LEFT JOIN sys.extended_properties ep ON ep.major_id=c.object_id AND ep.minor_id=c.column_id
 AND ep.name='MS_Description'
WHERE s.name IN ('Sales','Production','Person')
ORDER BY s.name,t.name,c.column_id;

SELECT fk.name AS fk,OBJECT_SCHEMA_NAME(fk.parent_object_id) AS esquema_origem,
OBJECT_NAME(fk.parent_object_id) AS tabela_origem,pc.name AS coluna_origem,
OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS esquema_destino,
OBJECT_NAME(fk.referenced_object_id) AS tabela_destino,rc.name AS coluna_destino
FROM sys.foreign_keys fk JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id=fk.object_id
JOIN sys.columns pc ON pc.object_id=fkc.parent_object_id AND pc.column_id=fkc.parent_column_id
JOIN sys.columns rc ON rc.object_id=fkc.referenced_object_id AND rc.column_id=fkc.referenced_column_id
ORDER BY tabela_origem,fk.name;

SELECT Status,COUNT(*) AS pedidos,MIN(OrderDate) AS primeira_data,MAX(OrderDate) AS ultima_data,
SUM(CASE WHEN ShipDate IS NULL THEN 1 ELSE 0 END) AS sem_data_envio,
SUM(CASE WHEN CurrencyRateID IS NOT NULL THEN 1 ELSE 0 END) AS com_referencia_cambio
FROM Sales.SalesOrderHeader GROUP BY Status ORDER BY Status;

SELECT COUNT(*) AS itens,COUNT(DISTINCT SalesOrderID) AS pedidos_com_itens,
SUM(CAST(OrderQty AS bigint)) AS unidades,SUM(LineTotal) AS receita_itens_todos_status
FROM Sales.SalesOrderDetail;

SELECT TOP(20) h.SalesOrderID,h.SubTotal,SUM(d.LineTotal) AS soma_itens,
h.SubTotal-SUM(d.LineTotal) AS diferenca
FROM Sales.SalesOrderHeader h JOIN Sales.SalesOrderDetail d ON d.SalesOrderID=h.SalesOrderID
GROUP BY h.SalesOrderID,h.SubTotal
HAVING ABS(h.SubTotal-SUM(d.LineTotal))>0.01 ORDER BY ABS(h.SubTotal-SUM(d.LineTotal)) DESC;

-- Verificar indicadores básicos na fonte com a mesma população do DW.
SELECT SUM(CAST(d.OrderQty AS decimal(18,0))*d.UnitPrice) AS receita_bruta,
SUM(CAST(d.OrderQty AS decimal(18,0))*d.UnitPrice-d.LineTotal) AS descontos,
SUM(d.LineTotal) AS receita_liquida,SUM(CAST(d.OrderQty AS bigint)) AS unidades,
COUNT(DISTINCT h.SalesOrderID) AS pedidos,COUNT(DISTINCT h.CustomerID) AS clientes
FROM Sales.SalesOrderHeader h JOIN Sales.SalesOrderDetail d ON d.SalesOrderID=h.SalesOrderID
WHERE h.Status=5;

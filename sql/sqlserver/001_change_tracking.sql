-- Executar na base OLTP restaurada. Não usa ModifiedDate como detector.
-- O banco é parametrizado pelo código de preparação, não por texto do usuário.
IF NOT EXISTS (SELECT 1 FROM sys.change_tracking_databases WHERE database_id=DB_ID())
BEGIN
  DECLARE @ct nvarchar(max)=N'ALTER DATABASE '+QUOTENAME(DB_NAME())+
    N' SET CHANGE_TRACKING = ON (CHANGE_RETENTION = 7 DAYS, AUTO_CLEANUP = ON)';
  EXEC(@ct);
END;
DECLARE @snapshot nvarchar(max)=N'ALTER DATABASE '+QUOTENAME(DB_NAME())+N' SET ALLOW_SNAPSHOT_ISOLATION ON';
EXEC(@snapshot);
IF NOT EXISTS (SELECT 1 FROM sys.extended_properties WHERE class=0 AND name=N'DWSourceEpoch')
BEGIN
  DECLARE @epoch nvarchar(36)=CONVERT(nvarchar(36),NEWID());
  EXEC sys.sp_addextendedproperty @name=N'DWSourceEpoch',@value=@epoch;
END;
DECLARE @t nvarchar(128), @sql nvarchar(max);
DECLARE tabelas CURSOR LOCAL FAST_FORWARD FOR
SELECT nome FROM (VALUES
 (N'Sales.SalesOrderHeader'),(N'Sales.SalesOrderDetail'),
 (N'Production.Product'),(N'Production.ProductSubcategory'),
 (N'Production.ProductCategory'),(N'Sales.Customer'),
 (N'Person.Person'),(N'Sales.Store'),(N'Sales.SalesTerritory'),(N'Sales.SalesPerson')
) t(nome);
OPEN tabelas;
FETCH NEXT FROM tabelas INTO @t;
WHILE @@FETCH_STATUS=0
BEGIN
  IF NOT EXISTS (SELECT 1 FROM sys.change_tracking_tables WHERE object_id=OBJECT_ID(@t))
  BEGIN
    SET @sql=N'ALTER TABLE '+@t+N' ENABLE CHANGE_TRACKING WITH (TRACK_COLUMNS_UPDATED = OFF)';
    EXEC(@sql);
  END;
  FETCH NEXT FROM tabelas INTO @t;
END;
CLOSE tabelas;
DEALLOCATE tabelas;

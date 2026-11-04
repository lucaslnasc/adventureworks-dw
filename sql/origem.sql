-- Preparação explícita, executada no AdventureWorks já restaurado.
-- Este script modifica configurações da origem; só é chamado na preparação explícita.
SET NOCOUNT ON;
IF DB_NAME() IN (N'master',N'model',N'msdb',N'tempdb')
    THROW 50001, 'Selecione o banco AdventureWorks antes de preparar a origem.', 1;
IF OBJECT_ID(N'Sales.SalesOrderHeader') IS NULL
    THROW 50002, 'O banco selecionado não contém Sales.SalesOrderHeader.', 1;

-- CT registra chaves alteradas por sete dias; checkpoint expirado exige avaliar resync.
DECLARE @comando nvarchar(max);
IF NOT EXISTS (SELECT 1 FROM sys.change_tracking_databases WHERE database_id=DB_ID())
BEGIN
    SET @comando=N'ALTER DATABASE '+QUOTENAME(DB_NAME())+
        N' SET CHANGE_TRACKING = ON (CHANGE_RETENTION = 7 DAYS, AUTO_CLEANUP = ON)';
    EXEC sys.sp_executesql @comando;
END;
-- Snapshot permite extrair dados e versões dentro de uma leitura consistente.
SET @comando=N'ALTER DATABASE '+QUOTENAME(DB_NAME())+N' SET ALLOW_SNAPSHOT_ISOLATION ON';
EXEC sys.sp_executesql @comando;

-- A época identifica esta origem e participa da comparação com o checkpoint do DW.
IF NOT EXISTS (SELECT 1 FROM sys.extended_properties WHERE class=0 AND name=N'DWSourceEpoch')
BEGIN
    DECLARE @epoca nvarchar(36)=CONVERT(nvarchar(36),NEWID());
    EXEC sys.sp_addextendedproperty @name=N'DWSourceEpoch', @value=@epoca;
END;

-- Habilita CT nas dez tabelas: mudanças indiretas também podem afetar dimensões.
DECLARE @tabela nvarchar(128);
DECLARE tabelas CURSOR LOCAL FAST_FORWARD FOR
SELECT nome FROM (VALUES
    (N'Sales.SalesOrderHeader'), (N'Sales.SalesOrderDetail'),
    (N'Production.Product'), (N'Production.ProductSubcategory'),
    (N'Production.ProductCategory'), (N'Sales.Customer'), (N'Person.Person'),
    (N'Sales.Store'), (N'Sales.SalesTerritory'), (N'Sales.SalesPerson')
) AS origem(nome);
OPEN tabelas;
FETCH NEXT FROM tabelas INTO @tabela;
WHILE @@FETCH_STATUS=0
BEGIN
    IF OBJECT_ID(@tabela) IS NULL
        THROW 50003, 'Uma das dez tabelas obrigatórias não existe.', 1;
    IF NOT EXISTS (SELECT 1 FROM sys.change_tracking_tables WHERE object_id=OBJECT_ID(@tabela))
    BEGIN
        SET @comando=N'ALTER TABLE '+QUOTENAME(PARSENAME(@tabela,2))+N'.'+
            QUOTENAME(PARSENAME(@tabela,1))+N' ENABLE CHANGE_TRACKING WITH (TRACK_COLUMNS_UPDATED = OFF)';
        EXEC sys.sp_executesql @comando;
    END;
    FETCH NEXT FROM tabelas INTO @tabela;
END;
CLOSE tabelas;
DEALLOCATE tabelas;

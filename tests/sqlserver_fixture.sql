-- Fonte mínima sintética usada apenas pelo teste de integração do CT.
CREATE SCHEMA Sales;
GO
CREATE SCHEMA Production;
GO
CREATE SCHEMA Person;
GO
CREATE TABLE Production.ProductCategory(ProductCategoryID int PRIMARY KEY,Name nvarchar(50));
CREATE TABLE Production.ProductSubcategory(ProductSubcategoryID int PRIMARY KEY,ProductCategoryID int,Name nvarchar(50));
CREATE TABLE Production.Product(ProductID int PRIMARY KEY,ProductSubcategoryID int,Name nvarchar(50),ProductNumber nvarchar(25),Color nvarchar(15));
CREATE TABLE Person.Person(BusinessEntityID int PRIMARY KEY,FirstName nvarchar(50),MiddleName nvarchar(50),LastName nvarchar(50));
CREATE TABLE Sales.Store(BusinessEntityID int PRIMARY KEY,Name nvarchar(50));
CREATE TABLE Sales.Customer(CustomerID int PRIMARY KEY,PersonID int,StoreID int);
CREATE TABLE Sales.SalesTerritory(TerritoryID int PRIMARY KEY,Name nvarchar(50),CountryRegionCode nvarchar(3),[Group] nvarchar(50));
CREATE TABLE Sales.SalesPerson(BusinessEntityID int PRIMARY KEY);
CREATE TABLE Sales.SalesOrderHeader(SalesOrderID int PRIMARY KEY,OrderDate datetime,DueDate datetime,
ShipDate datetime,CustomerID int,TerritoryID int,SalesPersonID int,OnlineOrderFlag bit,Status tinyint,ModifiedDate datetime);
CREATE TABLE Sales.SalesOrderDetail(SalesOrderID int,SalesOrderDetailID int,ProductID int,OrderQty smallint,
UnitPrice money,UnitPriceDiscount money,LineTotal AS (UnitPrice*(1.0-UnitPriceDiscount)*OrderQty),ModifiedDate datetime,
PRIMARY KEY(SalesOrderID,SalesOrderDetailID));
INSERT INTO Production.ProductCategory VALUES(1,N'Bikes');
INSERT INTO Production.ProductSubcategory VALUES(1,1,N'Road');
INSERT INTO Production.Product VALUES(1,1,N'Bike',N'B1',NULL);
INSERT INTO Person.Person VALUES(1,N'Ana',NULL,N'Silva');
INSERT INTO Sales.Customer VALUES(1,1,NULL);
INSERT INTO Sales.SalesOrderHeader VALUES(1,'20240110','20240115','20240112',1,NULL,NULL,1,5,'20240110');
INSERT INTO Sales.SalesOrderDetail VALUES(1,1,1,2,100,0.1,'20240110');

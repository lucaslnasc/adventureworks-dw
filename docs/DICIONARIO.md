# Dicionário de dados do Data Warehouse

Extraído do DDL executado em PostgreSQL 17.5. Os tipos, nulabilidade e restrições abaixo correspondem à implementação. NK = chave de negócio da origem; SK = chave substituta. Todas as dimensões descritivas usam SCD1. Valores monetários usam UM da fonte.

## dw.dim_canal

| Campo | Tipo | Nulo | Origem, significado e regra |
|---|---|---|---|
| canal_sk | smallint | Não | PK estática 0 revendedor e 1 online, derivada de Header.OnlineOrderFlag. |
| nome | text | Não | Rótulo estático Revendedor ou Online. |

**Restrições implementadas:**

- `CHECK ((canal_sk = ANY (ARRAY[0, 1])))`
- `UNIQUE (nome)`
- `PRIMARY KEY (canal_sk)`

## dw.dim_cliente

| Campo | Tipo | Nulo | Origem, significado e regra |
|---|---|---|---|
| cliente_sk | bigint | Não | PK substituta; FK da fato, preservada no SCD1. |
| cliente_id | integer | Não | NK única Sales.Customer.CustomerID; distingue pessoa ou loja compradora. |
| nome | text | Não | Sales.Store.Name priorizado; senão nome completo de Person.Person ligado por Customer.PersonID. |
| tipo | text | Não | Loja se StoreID preenchido, Pessoa se PersonID preenchido; caso contrário Não informado. |
| ativo_origem | boolean | Não | Metadado SCD1: membro existe atualmente na origem. Não é KPI de atividade comercial. |
| atualizado_em | timestamp with time zone | Não | Instante UTC-equivalente armazenado como timestamptz da última gravação no DW; não é ModifiedDate da fonte. |

**Restrições implementadas:**

- `UNIQUE (cliente_id)`
- `PRIMARY KEY (cliente_sk)`
- `CHECK ((tipo = ANY (ARRAY['Loja'::text, 'Pessoa'::text, 'Não informado'::text])))`

## dw.dim_data

| Campo | Tipo | Nulo | Origem, significado e regra |
|---|---|---|---|
| data_sk | integer | Não | PK natural inteligente YYYYMMDD; gerada a partir da data, compartilhada pelos três papéis. |
| data | date | Não | Data calendário única; derivada de OrderDate, DueDate e ShipDate e preenchida de forma contínua. |
| ano | smallint | Não | Ano civil extraído da data. |
| trimestre | smallint | Não | Trimestre civil 1 a 4; agregação temporal. |
| mes | smallint | Não | Mês numérico 1 a 12. |
| dia | smallint | Não | Dia do mês 1 a 31. |
| dia_semana_iso | smallint | Não | Dia ISO: 1 segunda-feira a 7 domingo. |
| inicio_mes | date | Não | Primeiro dia do mês; chave de agrupamento mensal. |

**Restrições implementadas:**

- `UNIQUE (data)`
- `CHECK (((dia >= 1) AND (dia <= 31)))`
- `CHECK (((dia_semana_iso >= 1) AND (dia_semana_iso <= 7)))`
- `CHECK (((mes >= 1) AND (mes <= 12)))`
- `PRIMARY KEY (data_sk)`
- `CHECK (((trimestre >= 1) AND (trimestre <= 4)))`

## dw.dim_produto

| Campo | Tipo | Nulo | Origem, significado e regra |
|---|---|---|---|
| produto_sk | bigint | Não | PK substituta gerada no PostgreSQL; FK da fato. |
| produto_id | integer | Não | NK única Production.Product.ProductID; lookup e upsert da dimensão. |
| nome | text | Não | Production.Product.Name; descrição atual do produto. |
| numero_produto | text | Não | Production.Product.ProductNumber; código comercial. |
| cor | text | Sim | Production.Product.Color; NULL preserva ausência. |
| subcategoria | text | Não | Production.ProductSubcategory.Name; join por ProductSubcategoryID. Ausente vira Sem subcategoria. |
| categoria | text | Não | Production.ProductCategory.Name via subcategoria; ausente vira Sem categoria. |
| ativo_origem | boolean | Não | Metadado SCD1: membro existe atualmente na origem. Não é KPI de atividade comercial. |
| atualizado_em | timestamp with time zone | Não | Instante UTC-equivalente armazenado como timestamptz da última gravação no DW; não é ModifiedDate da fonte. |

**Restrições implementadas:**

- `PRIMARY KEY (produto_sk)`
- `UNIQUE (produto_id)`

## dw.dim_territorio

| Campo | Tipo | Nulo | Origem, significado e regra |
|---|---|---|---|
| territorio_sk | bigint | Não | PK substituta; membro 0 quando Header.TerritoryID é nulo. |
| territorio_id | integer | Não | NK Sales.SalesTerritory.TerritoryID; 0 é membro técnico. |
| nome | text | Não | Sales.SalesTerritory.Name; descrição atual do território do pedido. |
| pais_codigo | text | Não | Sales.SalesTerritory.CountryRegionCode; não indica moeda da medida. |
| grupo | text | Não | Sales.SalesTerritory.Group; agrupamento comercial. |
| ativo_origem | boolean | Não | Metadado SCD1: membro existe atualmente na origem. Não é KPI de atividade comercial. |
| atualizado_em | timestamp with time zone | Não | Instante UTC-equivalente armazenado como timestamptz da última gravação no DW; não é ModifiedDate da fonte. |

**Restrições implementadas:**

- `PRIMARY KEY (territorio_sk)`
- `UNIQUE (territorio_id)`

## dw.dim_vendedor

| Campo | Tipo | Nulo | Origem, significado e regra |
|---|---|---|---|
| vendedor_sk | bigint | Não | PK substituta; membro 0 quando Header.SalesPersonID é nulo. |
| vendedor_id | integer | Não | NK Sales.SalesPerson.BusinessEntityID; 0 é membro técnico. |
| nome | text | Não | Nome completo de Person.Person ligado a SalesPerson.BusinessEntityID. |
| ativo_origem | boolean | Não | Metadado SCD1: membro existe atualmente na origem. Não é KPI de atividade comercial. |
| atualizado_em | timestamp with time zone | Não | Instante UTC-equivalente armazenado como timestamptz da última gravação no DW; não é ModifiedDate da fonte. |

**Restrições implementadas:**

- `PRIMARY KEY (vendedor_sk)`
- `UNIQUE (vendedor_id)`

## dw.fato_venda

| Campo | Tipo | Nulo | Origem, significado e regra |
|---|---|---|---|
| pedido_id | integer | Não | SalesOrderHeader/Detail.SalesOrderID; parte da PK e dimensão degenerada do documento. |
| item_id | integer | Não | SalesOrderDetail.SalesOrderDetailID; parte da PK com pedido_id. |
| data_pedido_sk | integer | Não | FK para dim_data, derivada de Header.OrderDate; eixo temporal padrão dos KPIs. |
| data_vencimento_sk | integer | Não | FK para dim_data, derivada de Header.DueDate; marco de vencimento, não prova de entrega. |
| data_envio_sk | integer | Sim | FK opcional para dim_data, derivada de Header.ShipDate; NULL quando não informada. |
| produto_sk | bigint | Não | FK para dw.dim_produto. Lookup da NK proveniente do item/cabeçalho; relação N:1. |
| cliente_sk | bigint | Não | FK para dw.dim_cliente. Lookup da NK proveniente do item/cabeçalho; relação N:1. |
| territorio_sk | bigint | Não | FK para dw.dim_territorio. Lookup da NK proveniente do item/cabeçalho; relação N:1. |
| vendedor_sk | bigint | Não | FK para dw.dim_vendedor. Lookup da NK proveniente do item/cabeçalho; relação N:1. |
| canal_sk | smallint | Não | FK para dw.dim_canal. Lookup da NK proveniente do item/cabeçalho; relação N:1. |
| status | smallint | Não | Header.Status: 1 processo, 2 aprovado, 3 atraso, 4 rejeitado, 5 expedido, 6 cancelado. Somente 5 nos KPIs. |
| quantidade | integer | Não | Detail.OrderQty; inteiro positivo e aditivo. |
| preco_unitario | numeric(19,4) | Não | Detail.UnitPrice em UM; não aditivo. Decimal preserva precisão monetária. |
| taxa_desconto | numeric(9,4) | Não | Detail.UnitPriceDiscount como fração; intervalo de qualidade 0 a 1; não somável. |
| receita_liquida | numeric(28,8) | Não | Detail.LineTotal; preserva valor computado na fonte; soma comercial após desconto, sem frete/impostos. |
| receita_bruta | numeric(28,8) | Sim | Coluna gerada: quantidade × preco_unitario; medida aditiva em UM. |
| valor_desconto | numeric(28,8) | Sim | Coluna gerada: receita_bruta − receita_liquida; mantém reconciliação com a fonte. |
| versao_origem | bigint | Não | Versão CT do lote da última mudança material carregada no item; não é timestamp nem versão individual do evento. |
| carregado_em | timestamp with time zone | Não | Instante da inserção ou última atualização material do item no DW. |

**Restrições implementadas:**

- `FOREIGN KEY (canal_sk) REFERENCES dw.dim_canal(canal_sk)`
- `CHECK ((abs((receita_liquida - (((quantidade)::numeric * preco_unitario) * ((1)::numeric - taxa_desconto)))) <= 0.000001))`
- `FOREIGN KEY (cliente_sk) REFERENCES dw.dim_cliente(cliente_sk)`
- `FOREIGN KEY (data_envio_sk) REFERENCES dw.dim_data(data_sk)`
- `FOREIGN KEY (data_pedido_sk) REFERENCES dw.dim_data(data_sk)`
- `FOREIGN KEY (data_vencimento_sk) REFERENCES dw.dim_data(data_sk)`
- `PRIMARY KEY (pedido_id, item_id)`
- `CHECK ((preco_unitario >= (0)::numeric))`
- `FOREIGN KEY (produto_sk) REFERENCES dw.dim_produto(produto_sk)`
- `CHECK ((quantidade > 0))`
- `CHECK ((receita_liquida >= (0)::numeric))`
- `CHECK (((status >= 1) AND (status <= 6)))`
- `CHECK (((taxa_desconto >= (0)::numeric) AND (taxa_desconto <= (1)::numeric)))`
- `FOREIGN KEY (territorio_sk) REFERENCES dw.dim_territorio(territorio_sk)`
- `FOREIGN KEY (vendedor_sk) REFERENCES dw.dim_vendedor(vendedor_sk)`

## etl.controle

| Campo | Tipo | Nulo | Origem, significado e regra |
|---|---|---|---|
| pipeline | text | Não | PK lógica do processo; valor vendas nesta implementação. |
| versao | bigint | Não | Última versão CT confirmada junto aos dados, usada no próximo ciclo. |
| identidade_origem | text | Não | UUID da preparação e begin_version das tabelas CT; identifica a linhagem esperada. |
| atualizado_em | timestamp with time zone | Não | Instante UTC-equivalente armazenado como timestamptz da última gravação no DW; não é ModifiedDate da fonte. |

**Restrições implementadas:**

- `PRIMARY KEY (pipeline)`

## etl.execucao

| Campo | Tipo | Nulo | Origem, significado e regra |
|---|---|---|---|
| execucao_id | uuid | Não | UUID gerado em Python; PK para rastrear uma tentativa. |
| inicio | timestamp with time zone | Não | Instante de registro da tentativa. |
| fim | timestamp with time zone | Sim | Instante de conclusão/falha; nulo enquanto running. |
| status | text | Não | running, success ou failed; estado operacional da tentativa. |
| modo | text | Não | initial, incremental ou resync; explica se houve leitura inicial/completa explícita. |
| versao_anterior | bigint | Sim | Checkpoint antes da tentativa; nulo na primeira carga. |
| versao_nova | bigint | Sim | Versão do snapshot confirmada; nula se falhou antes de concluir. |
| estatisticas | jsonb | Sim | JSON com ct_keys, dimension_rows_extracted/written, orders_affected, facts_extracted/written/deleted. |
| erro | text | Sim | Descrição resumida da falha, sem credenciais; nula se não houver erro. |

**Restrições implementadas:**

- `PRIMARY KEY (execucao_id)`
- `CHECK ((status = ANY (ARRAY['running'::text, 'success'::text, 'failed'::text])))`

## Índices e relacionamentos

A PK da fato é (pedido_id, item_id). Existem oito FKs: três para datas e cinco para as demais dimensões. A data de envio é opcional; as outras FKs são obrigatórias. Nenhuma dimensão referencia outra dimensão. PKs e NKs UNIQUE já geram índices; índices adicionais da fato cobrem data do pedido, envio, vencimento, produto, cliente, território e vendedor. Canal e status têm baixa cardinalidade e não recebem índice isolado nesta versão.

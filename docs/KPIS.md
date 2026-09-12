# Dez indicadores com fórmulas, SQL e defesa

Todas as consultas são PostgreSQL e usam `dw.v_vendas`, que considera somente Status=5 (expedido), atribuído à data do pedido. O período padrão é todo o intervalo carregado. Para segmentação, aplique filtros iguais aos componentes da fórmula. As hierarquias Produto→Subcategoria→Categoria são atributos de uma mesma dimensão, não joins entre dimensões.

Os exemplos a seguir são **sintéticos**, usados nos testes: pedido 1 em janeiro, com linhas de 2 × 100 UM a 10% de desconto e 1 × 50 UM sem desconto; pedido 2 em março, com 3 × 20 UM sem desconto. São dois clientes e seis unidades. Um terceiro pedido cancelado de 30 UM líquidos é armazenado, mas excluído dos KPIs. O primeiro pedido é expedido antes do vencimento; o segundo, depois. Fevereiro não tem vendas. Nenhum desses números é apresentado como resultado do AdventureWorks real.

Sem meta, limiar ou responsável de negócio formalizado, alguns itens são métricas de desempenho; o termo KPI é usado no sentido amplo autorizado pelo enunciado. Não inventamos metas empresariais para a empresa fictícia.

As fórmulas estão implementadas em `sql/postgres/002_kpis.sql`; `003_comprovar_kpis.sql` executa as dez views. Depois da carga real, `python -m etl report` exporta os valores para `evidence/kpis.json`.

## 01 Receita bruta de vendas

**Objetivo:** Mensurar o valor comercial dos itens antes dos descontos.

**Relevância:** Permite separar variação do volume/preço da concessão de descontos.

**Tabelas e campos da origem:** Sales.SalesOrderDetail: OrderQty, UnitPrice, SalesOrderID; Sales.SalesOrderHeader: SalesOrderID, Status, OrderDate.

**Regra de cálculo:** Σ (OrderQty × UnitPrice), para pedidos expedidos.

**SQL que calcula o indicador:**

```sql
SELECT coalesce(sum(receita_bruta),0) AS receita_bruta_um FROM dw.v_vendas;
```

**Consulta da implementação:** `SELECT * FROM dw.kpi_01_receita_bruta;`

**Como interpretar o resultado no exemplo sintético:** 310 UM. Foram vendidos itens por 310 UM antes de 20 UM de descontos.

**Argumento para apresentação:** A medida está no grão item e pode ser somada. Não uso TotalDue: ele inclui parcelas de cabeçalho. Crescimento da receita bruta sozinho não demonstra maior lucro.

## 02 Valor dos descontos comerciais

**Objetivo:** Quantificar o valor monetário concedido em descontos.

**Relevância:** Mostra quanto do valor bruto foi reduzido na negociação e permite segmentar essa concessão.

**Tabelas e campos da origem:** Sales.SalesOrderDetail: OrderQty, UnitPrice, UnitPriceDiscount, LineTotal, SalesOrderID; Sales.SalesOrderHeader: SalesOrderID, Status, OrderDate.

**Regra de cálculo:** Σ (OrderQty × UnitPrice − LineTotal). É equivalente ao bruto × taxa, salvo arredondamento da origem.

**SQL que calcula o indicador:**

```sql
SELECT coalesce(sum(valor_desconto),0) AS descontos_um FROM dw.v_vendas;
```

**Consulta da implementação:** `SELECT * FROM dw.kpi_02_descontos;`

**Como interpretar o resultado no exemplo sintético:** 20 UM. O desconto ocorreu na linha de 200 UM, reduzida a 180 UM.

**Argumento para apresentação:** Somar UnitPriceDiscount seria incorreto porque é uma fração. Derivo o desconto monetário da diferença entre bruto e LineTotal para preservar a reconciliação com a fonte.

## 03 Receita líquida comercial

**Objetivo:** Mensurar o valor dos itens depois dos descontos.

**Relevância:** É a medida central para comparar as vendas comerciais por produto, cliente, território e período.

**Tabelas e campos da origem:** Sales.SalesOrderDetail: LineTotal, OrderQty, UnitPrice, UnitPriceDiscount, SalesOrderID; Sales.SalesOrderHeader: SalesOrderID, Status, OrderDate.

**Regra de cálculo:** Σ LineTotal; por item, OrderQty × UnitPrice × (1 − UnitPriceDiscount).

**SQL que calcula o indicador:**

```sql
SELECT coalesce(sum(receita_liquida),0) AS receita_liquida_um FROM dw.v_vendas;
```

**Consulta da implementação:** `SELECT * FROM dw.kpi_03_receita_liquida;`

**Como interpretar o resultado no exemplo sintético:** 290 UM. A receita bruta de 310 UM menos descontos de 20 UM resulta em 290 UM.

**Argumento para apresentação:** É líquida apenas dos descontos comerciais dos itens. Não é lucro nem total faturado com impostos/frete. O nome e o recorte evitam uma interpretação contábil que os campos não sustentam.

## 04 Quantidade de unidades vendidas

**Objetivo:** Medir o volume físico de produtos vendidos.

**Relevância:** Complementa a receita: uma alteração do mix ou dos preços pode elevar receita sem crescimento das unidades.

**Tabelas e campos da origem:** Sales.SalesOrderDetail: OrderQty, SalesOrderID; Sales.SalesOrderHeader: SalesOrderID, Status, OrderDate.

**Regra de cálculo:** Σ OrderQty.

**SQL que calcula o indicador:**

```sql
SELECT coalesce(sum(quantidade),0) AS unidades FROM dw.v_vendas;
```

**Consulta da implementação:** `SELECT * FROM dw.kpi_04_unidades;`

**Como interpretar o resultado no exemplo sintético:** 6 unidades. As três linhas expedidas contêm 2, 1 e 3 unidades.

**Argumento para apresentação:** COUNT de linhas mede itens do pedido, não unidades. As unidades combinam produtos diferentes e não são uma medida de peso ou capacidade produtiva; o recorte por categoria ajuda a interpretar o mix.

## 05 Quantidade de pedidos expedidos

**Objetivo:** Contar os documentos comerciais presentes nas vendas analisadas.

**Relevância:** Distingue intensidade de compras da quantidade de produtos e fornece o denominador do ticket médio.

**Tabelas e campos da origem:** Sales.SalesOrderHeader: SalesOrderID, Status, OrderDate; Sales.SalesOrderDetail: SalesOrderID (existência de itens).

**Regra de cálculo:** COUNT(DISTINCT pedido_id) nos itens dos pedidos expedidos.

**SQL que calcula o indicador:**

```sql
SELECT count(DISTINCT pedido_id) AS pedidos FROM dw.v_vendas;
```

**Consulta da implementação:** `SELECT * FROM dw.kpi_05_pedidos;`

**Como interpretar o resultado no exemplo sintético:** 2 pedidos. O pedido 1 tem dois itens e continua contando uma vez.

**Argumento para apresentação:** O grão é item, por isso a contagem deve ser distinta. Um pedido sem itens não está nesta fato. Contagens por categoria não são somáveis: um pedido pode conter várias categorias.

## 06 Ticket médio por pedido

**Objetivo:** Estimar o valor líquido médio dos pedidos do recorte.

**Relevância:** Ajuda a interpretar se a receita se deve a mais pedidos ou a maior valor por compra.

**Tabelas e campos da origem:** Sales.SalesOrderDetail: LineTotal, SalesOrderID; Sales.SalesOrderHeader: SalesOrderID, Status, OrderDate.

**Regra de cálculo:** Σ LineTotal ÷ COUNT(DISTINCT SalesOrderID). NULL se não houver pedidos.

**SQL que calcula o indicador:**

```sql
SELECT sum(receita_liquida)/nullif(count(DISTINCT pedido_id),0) AS ticket_medio_um
FROM dw.v_vendas;
```

**Consulta da implementação:** `SELECT * FROM dw.kpi_06_ticket_medio;`

**Como interpretar o resultado no exemplo sintético:** 145 UM por pedido: 290 ÷ 2.

**Argumento para apresentação:** AVG(LineTotal) mede o valor médio por linha. Eu calculo razão de totais e não média de tickets de subgrupos. Ao filtrar uma categoria, o resultado é a parcela daquela categoria por pedido que a contém.

## 07 Taxa ponderada de desconto

**Objetivo:** Expressar os descontos em relação ao valor bruto das vendas.

**Relevância:** Permite comparar concessões entre segmentos com escalas de receita diferentes.

**Tabelas e campos da origem:** Sales.SalesOrderDetail: OrderQty, UnitPrice, UnitPriceDiscount, LineTotal, SalesOrderID; Sales.SalesOrderHeader: SalesOrderID, Status, OrderDate.

**Regra de cálculo:** 100 × Σ valor_desconto ÷ Σ receita_bruta. NULL se a receita bruta for zero.

**SQL que calcula o indicador:**

```sql
SELECT 100.0*sum(valor_desconto)/nullif(sum(receita_bruta),0) AS desconto_ponderado_pct
FROM dw.v_vendas;
```

**Consulta da implementação:** `SELECT * FROM dw.kpi_07_taxa_desconto;`

**Como interpretar o resultado no exemplo sintético:** Aproximadamente 6,4516%: 100 × 20 ÷ 310.

**Argumento para apresentação:** É uma taxa ponderada pelo valor bruto. Uma média simples das taxas daria o mesmo peso a uma venda pequena e a uma grande. Não somo taxas mensais nem calculo média simples das taxas de categorias.

## 08 Clientes com compra no período

**Objetivo:** Contar clientes distintos com ao menos um pedido expedido no recorte.

**Relevância:** Mede a abrangência da base compradora e complementa o volume vendido.

**Tabelas e campos da origem:** Sales.Customer: CustomerID; Sales.SalesOrderHeader: CustomerID, SalesOrderID, Status, OrderDate; Sales.SalesOrderDetail: SalesOrderID.

**Regra de cálculo:** COUNT(DISTINCT cliente_sk) na população de vendas; a SK tem mapeamento 1:1 para CustomerID por SCD1.

**SQL que calcula o indicador:**

```sql
SELECT count(DISTINCT cliente_sk) AS clientes_com_compra FROM dw.v_vendas;
```

**Consulta da implementação:** `SELECT * FROM dw.kpi_08_clientes_ativos;`

**Como interpretar o resultado no exemplo sintético:** 2 clientes. O cliente 1 fez uma compra elegível e o cliente 2 outra.

**Argumento para apresentação:** Ativo aqui significa compra no período, não cadastro existente, adimplência ou retenção. Distintos não são somáveis entre meses e clientes pessoas/lojas são identificados pelo CustomerID.

## 09 Crescimento mensal da receita líquida

**Objetivo:** Comparar a receita de um mês com o mês calendário imediatamente anterior.

**Relevância:** Evidencia variações temporais e permite investigar quedas, sazonalidade ou mudança de mix.

**Tabelas e campos da origem:** Sales.SalesOrderHeader: OrderDate, SalesOrderID, Status; Sales.SalesOrderDetail: LineTotal, SalesOrderID; calendário gerado na ETL e na consulta.

**Regra de cálculo:** 100 × (receita_mês − receita_mês_anterior) ÷ receita_mês_anterior. Meses sem venda valem zero; primeiro mês e base anterior zero resultam em NULL.

**SQL que calcula o indicador:**

```sql
WITH limites AS (
 SELECT date_trunc('month',min(d.data)) AS primeiro,
        date_trunc('month',max(d.data)) AS ultimo
 FROM dw.fato_venda f JOIN dw.dim_data d ON d.data_sk=f.data_pedido_sk
), meses AS (
 SELECT m::date AS mes FROM limites,
 generate_series(primeiro,ultimo,interval '1 month') m
), totais AS (
 SELECT inicio_mes AS mes,sum(receita_liquida) AS receita FROM dw.v_vendas GROUP BY inicio_mes
), serie AS (
 SELECT m.mes,coalesce(t.receita,0) AS receita FROM meses m LEFT JOIN totais t USING(mes)
), anterior AS (
 SELECT mes,receita,lag(receita) OVER (ORDER BY mes) AS receita_anterior FROM serie
)
SELECT mes,receita,receita_anterior,
 100.0*(receita-receita_anterior)/nullif(receita_anterior,0) AS crescimento_pct
FROM anterior;
```

**Consulta da implementação:** `SELECT * FROM dw.kpi_09_crescimento_mensal;`

**Como interpretar o resultado no exemplo sintético:** Janeiro: 230 UM, sem comparação. Fevereiro: 0 UM, queda de 100%. Março: 60 UM, percentual indefinido porque fevereiro tem base zero.

**Argumento para apresentação:** Um LAG apenas sobre meses com venda compararia março diretamente com janeiro e esconderia fevereiro. A série é preenchida antes do LAG. Meses inicial/final podem estar incompletos e devem ser sinalizados; crescimento não demonstra causalidade nem deve ser somado.

## 10 Percentual de expedição até o vencimento do pedido

**Objetivo:** Medir a proporção de pedidos expedidos cuja ShipDate não ultrapassa DueDate.

**Relevância:** Fornece um sinal operacional de cumprimento do marco de vencimento disponível nos dados.

**Tabelas e campos da origem:** Sales.SalesOrderHeader: SalesOrderID, Status, OrderDate, ShipDate, DueDate; Sales.SalesOrderDetail: SalesOrderID para compor a população com itens.

**Regra de cálculo:** 100 × pedidos distintos com ShipDate ≤ DueDate ÷ pedidos distintos expedidos com ShipDate preenchida. Ausências são exibidas separadamente. NULL se o denominador for zero.

**SQL que calcula o indicador:**

```sql
WITH pedidos AS (
 SELECT DISTINCT pedido_id,data_envio,data_vencimento FROM dw.v_vendas
)
SELECT count(*) FILTER(WHERE data_envio IS NOT NULL) AS pedidos_com_data,
       count(*) FILTER(WHERE data_envio IS NULL) AS pedidos_sem_data,
       count(*) FILTER(WHERE data_envio<=data_vencimento) AS pedidos_no_prazo,
       100.0*count(*) FILTER(WHERE data_envio<=data_vencimento)
       /nullif(count(*) FILTER(WHERE data_envio IS NOT NULL),0) AS expedicao_no_prazo_pct
FROM pedidos;
```

**Consulta da implementação:** `SELECT * FROM dw.kpi_10_expedicao_no_prazo;`

**Como interpretar o resultado no exemplo sintético:** 50%: um dos dois pedidos foi expedido até o vencimento. O resultado também informa dois com data e zero sem data.

**Argumento para apresentação:** ShipDate não é a entrega ao cliente. O indicador é um proxy de expedição em relação a DueDate, não OTIF. Deduplico pedidos para não dar mais peso a pedidos com muitos itens e exponho os registros sem data para não ocultar problemas de qualidade.


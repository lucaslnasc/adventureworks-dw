-- KPIs 1 a 8 e 10: todo o período carregado; todos usam Status=5.
-- Para recortes, aplicar o MESMO filtro em numerador e denominador.
CREATE OR REPLACE VIEW dw.kpi_01_receita_bruta AS
SELECT coalesce(sum(receita_bruta),0) AS receita_bruta_um FROM dw.v_vendas;

CREATE OR REPLACE VIEW dw.kpi_02_descontos AS
SELECT coalesce(sum(valor_desconto),0) AS descontos_um FROM dw.v_vendas;

CREATE OR REPLACE VIEW dw.kpi_03_receita_liquida AS
SELECT coalesce(sum(receita_liquida),0) AS receita_liquida_um FROM dw.v_vendas;

CREATE OR REPLACE VIEW dw.kpi_04_unidades AS
SELECT coalesce(sum(quantidade),0) AS unidades FROM dw.v_vendas;

CREATE OR REPLACE VIEW dw.kpi_05_pedidos AS
SELECT count(DISTINCT pedido_id) AS pedidos FROM dw.v_vendas;

CREATE OR REPLACE VIEW dw.kpi_06_ticket_medio AS
SELECT sum(receita_liquida)/nullif(count(DISTINCT pedido_id),0) AS ticket_medio_um
FROM dw.v_vendas;

CREATE OR REPLACE VIEW dw.kpi_07_taxa_desconto AS
SELECT 100.0*sum(valor_desconto)/nullif(sum(receita_bruta),0) AS desconto_ponderado_pct
FROM dw.v_vendas;

CREATE OR REPLACE VIEW dw.kpi_08_clientes_ativos AS
SELECT count(DISTINCT cliente_sk) AS clientes_com_compra FROM dw.v_vendas;

-- Calendário contínuo impede LAG de comparar meses não consecutivos.
CREATE OR REPLACE VIEW dw.kpi_09_crescimento_mensal AS
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

-- Expedição até DueDate: não é entrega ao cliente nem OTIF.
-- DISTINCT remove a repetição de datas do cabeçalho no grão de item.
CREATE OR REPLACE VIEW dw.kpi_10_expedicao_no_prazo AS
WITH pedidos AS (
 SELECT DISTINCT pedido_id,data_envio,data_vencimento FROM dw.v_vendas
)
SELECT count(*) FILTER(WHERE data_envio IS NOT NULL) AS pedidos_com_data,
       count(*) FILTER(WHERE data_envio IS NULL) AS pedidos_sem_data,
       count(*) FILTER(WHERE data_envio<=data_vencimento) AS pedidos_no_prazo,
       100.0*count(*) FILTER(WHERE data_envio<=data_vencimento)
       /nullif(count(*) FILTER(WHERE data_envio IS NOT NULL),0) AS expedicao_no_prazo_pct
FROM pedidos;

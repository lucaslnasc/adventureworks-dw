-- Dez indicadores, sempre sobre pedidos expedidos (status=5).
-- Receita líquida significa após descontos comerciais, não lucro.
-- 1. Receita antes dos descontos: soma quantidade vezes preço, não apenas preço unitário.
CREATE OR REPLACE VIEW dw.kpi_01_receita_bruta AS
SELECT COALESCE(SUM(receita_bruta),0) receita_bruta_um FROM dw.v_vendas;

-- 2. Valor concedido em descontos: montante monetário, não soma de percentuais.
CREATE OR REPLACE VIEW dw.kpi_02_descontos AS
SELECT COALESCE(SUM(valor_desconto),0) descontos_um FROM dw.v_vendas;

-- 3. Receita após descontos: não subtrai custos e, portanto, não mede lucro.
CREATE OR REPLACE VIEW dw.kpi_03_receita_liquida AS
SELECT COALESCE(SUM(receita_liquida),0) receita_liquida_um FROM dw.v_vendas;

-- 4. Unidades vendidas: soma quantidades; contar linhas mediria itens distintos do pedido.
CREATE OR REPLACE VIEW dw.kpi_04_unidades AS
SELECT COALESCE(SUM(quantidade),0) unidades FROM dw.v_vendas;

-- 5. Pedidos expedidos: DISTINCT evita contar o mesmo pedido uma vez por item.
CREATE OR REPLACE VIEW dw.kpi_05_pedidos AS
SELECT COUNT(DISTINCT pedido_id) pedidos FROM dw.v_vendas;

-- 6. Valor médio por pedido: NULLIF evita divisão por zero quando não há pedidos.
CREATE OR REPLACE VIEW dw.kpi_06_ticket_medio AS
SELECT SUM(receita_liquida)/NULLIF(COUNT(DISTINCT pedido_id),0) ticket_medio_um
FROM dw.v_vendas;

-- 7. Desconto percentual ponderado pela receita bruta, diferente da média das taxas por item.
CREATE OR REPLACE VIEW dw.kpi_07_taxa_desconto AS
SELECT 100.0*SUM(valor_desconto)/NULLIF(SUM(receita_bruta),0) desconto_ponderado_pct
FROM dw.v_vendas;

-- 8. Clientes com compra expedida no conjunto analisado; não conta todo o cadastro.
CREATE OR REPLACE VIEW dw.kpi_08_clientes_ativos AS
SELECT COUNT(DISTINCT cliente_sk) clientes_com_compra FROM dw.v_vendas;

-- O período vem de toda a fato; meses sem vendas expedidas aparecem com zero.
-- 9. Crescimento da receita por mês do pedido; primeiro mês e base zero resultam em NULL.
CREATE OR REPLACE VIEW dw.kpi_09_crescimento_mensal AS
WITH intervalo AS (
    SELECT date_trunc('month',MIN(d.data)) inicio,
           date_trunc('month',MAX(d.data)) fim
    FROM dw.fato_venda f JOIN dw.dim_data d ON d.data_sk=f.data_pedido_sk
), calendario AS (
    SELECT m::date mes FROM intervalo,
        generate_series(inicio,fim,interval '1 month') m
), vendas AS (
    SELECT inicio_mes mes, SUM(receita_liquida) receita FROM dw.v_vendas GROUP BY inicio_mes
), mensal AS (
    SELECT c.mes, COALESCE(v.receita,0) receita
    FROM calendario c LEFT JOIN vendas v USING(mes)
), comparacao AS (
    SELECT mes, receita, LAG(receita) OVER (ORDER BY mes) receita_anterior FROM mensal
)
SELECT mes, receita, receita_anterior,
       100.0*(receita-receita_anterior)/NULLIF(receita_anterior,0) crescimento_pct
FROM comparacao;

-- Cada pedido tem peso um, independentemente da quantidade de itens.
-- 10. Percentual de pedidos enviados até o vencimento; sem data fica fora do denominador.
CREATE OR REPLACE VIEW dw.kpi_10_expedicao_no_prazo AS
WITH pedidos AS (
    SELECT DISTINCT pedido_id, data_envio, data_vencimento FROM dw.v_vendas
)
SELECT COUNT(*) FILTER (WHERE data_envio IS NOT NULL) pedidos_com_data,
       COUNT(*) FILTER (WHERE data_envio IS NULL) pedidos_sem_data,
       COUNT(*) FILTER (WHERE data_envio<=data_vencimento) pedidos_no_prazo,
       100.0*COUNT(*) FILTER (WHERE data_envio<=data_vencimento)
           /NULLIF(COUNT(*) FILTER (WHERE data_envio IS NOT NULL),0) expedicao_no_prazo_pct
FROM pedidos;

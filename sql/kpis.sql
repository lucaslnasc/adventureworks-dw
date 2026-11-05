-- Dez indicadores. Cada view é um SELECT direto sobre o modelo estrela
-- (dw.fato_venda e dimensões) e considera só pedidos expedidos: status = 5.
-- Receita líquida significa após descontos comerciais, não lucro.

-- 1. Receita bruta: soma de quantidade × preço (coluna gerada receita_bruta).
CREATE OR REPLACE VIEW dw.kpi_01_receita_bruta AS
SELECT COALESCE(SUM(f.receita_bruta), 0) AS receita_bruta_um
FROM dw.fato_venda f
WHERE f.status = 5;

-- 2. Descontos concedidos: valor monetário, não soma de percentuais.
CREATE OR REPLACE VIEW dw.kpi_02_descontos AS
SELECT COALESCE(SUM(f.valor_desconto), 0) AS descontos_um
FROM dw.fato_venda f
WHERE f.status = 5;

-- 3. Receita líquida: após descontos; não subtrai custos.
CREATE OR REPLACE VIEW dw.kpi_03_receita_liquida AS
SELECT COALESCE(SUM(f.receita_liquida), 0) AS receita_liquida_um
FROM dw.fato_venda f
WHERE f.status = 5;

-- 4. Unidades vendidas: soma das quantidades (contar linhas mediria itens).
CREATE OR REPLACE VIEW dw.kpi_04_unidades AS
SELECT COALESCE(SUM(f.quantidade), 0) AS unidades
FROM dw.fato_venda f
WHERE f.status = 5;

-- 5. Pedidos expedidos: DISTINCT evita contar o pedido uma vez por item.
CREATE OR REPLACE VIEW dw.kpi_05_pedidos AS
SELECT COUNT(DISTINCT f.pedido_id) AS pedidos
FROM dw.fato_venda f
WHERE f.status = 5;

-- 6. Ticket médio: receita líquida por pedido; NULLIF evita divisão por zero.
CREATE OR REPLACE VIEW dw.kpi_06_ticket_medio AS
SELECT SUM(f.receita_liquida) / NULLIF(COUNT(DISTINCT f.pedido_id), 0) AS ticket_medio_um
FROM dw.fato_venda f
WHERE f.status = 5;

-- 7. Taxa de desconto ponderada pela receita bruta (não é a média das taxas).
CREATE OR REPLACE VIEW dw.kpi_07_taxa_desconto AS
SELECT 100.0 * SUM(f.valor_desconto) / NULLIF(SUM(f.receita_bruta), 0) AS desconto_ponderado_pct
FROM dw.fato_venda f
WHERE f.status = 5;

-- 8. Clientes com compra expedida (não conta todo o cadastro).
CREATE OR REPLACE VIEW dw.kpi_08_clientes_ativos AS
SELECT COUNT(DISTINCT c.cliente_id) AS clientes_com_compra
FROM dw.fato_venda f
JOIN dw.dim_cliente c ON c.cliente_sk = f.cliente_sk
WHERE f.status = 5;

-- 9. Crescimento mensal da receita pelo mês do pedido. O calendário cobre todo o
--    período da fato, então meses sem venda aparecem com zero; o primeiro mês e
--    a base zero resultam em NULL.
CREATE OR REPLACE VIEW dw.kpi_09_crescimento_mensal AS
WITH limites AS (
    SELECT date_trunc('month', MIN(d.data)) AS inicio, date_trunc('month', MAX(d.data)) AS fim
    FROM dw.fato_venda f
    JOIN dw.dim_data d ON d.data_sk = f.data_pedido_sk
), calendario AS (
    SELECT generate_series(inicio, fim, interval '1 month')::date AS mes FROM limites
), vendas AS (
    SELECT d.inicio_mes AS mes, SUM(f.receita_liquida) AS receita
    FROM dw.fato_venda f
    JOIN dw.dim_data d ON d.data_sk = f.data_pedido_sk
    WHERE f.status = 5
    GROUP BY d.inicio_mes
), mensal AS (
    SELECT c.mes, COALESCE(v.receita, 0) AS receita
    FROM calendario c
    LEFT JOIN vendas v ON v.mes = c.mes
)
SELECT mes, receita,
       LAG(receita) OVER w AS receita_anterior,
       100.0 * (receita - LAG(receita) OVER w) / NULLIF(LAG(receita) OVER w, 0) AS crescimento_pct
FROM mensal
WINDOW w AS (ORDER BY mes);

-- 10. Expedição no prazo: pedidos enviados até o vencimento ÷ pedidos com envio.
--     Cada pedido conta uma vez; sem data de envio fica fora do denominador.
CREATE OR REPLACE VIEW dw.kpi_10_expedicao_no_prazo AS
WITH pedidos AS (
    SELECT DISTINCT f.pedido_id, e.data AS data_envio, v.data AS data_vencimento
    FROM dw.fato_venda f
    JOIN dw.dim_data v ON v.data_sk = f.data_vencimento_sk
    LEFT JOIN dw.dim_data e ON e.data_sk = f.data_envio_sk
    WHERE f.status = 5
)
SELECT COUNT(*) FILTER (WHERE data_envio IS NOT NULL) AS pedidos_com_data,
       COUNT(*) FILTER (WHERE data_envio IS NULL) AS pedidos_sem_data,
       COUNT(*) FILTER (WHERE data_envio <= data_vencimento) AS pedidos_no_prazo,
       100.0 * COUNT(*) FILTER (WHERE data_envio <= data_vencimento)
           / NULLIF(COUNT(*) FILTER (WHERE data_envio IS NOT NULL), 0) AS expedicao_no_prazo_pct
FROM pedidos;

-- Consultas de análise usadas na discussão dos resultados: cortam os
-- indicadores pelas dimensões do modelo estrela. Só pedidos expedidos (status = 5).

-- A1. Receita e unidades por categoria de produto.
SELECT p.categoria,
       SUM(f.receita_liquida) AS receita,
       ROUND(100 * SUM(f.receita_liquida) / SUM(SUM(f.receita_liquida)) OVER (), 1) AS pct_receita,
       SUM(f.quantidade) AS unidades
FROM dw.fato_venda f
JOIN dw.dim_produto p ON p.produto_sk = f.produto_sk
WHERE f.status = 5
GROUP BY p.categoria
ORDER BY receita DESC;

-- A2. Receita, pedidos e ticket médio por canal de venda.
SELECT c.nome AS canal,
       SUM(f.receita_liquida) AS receita,
       COUNT(DISTINCT f.pedido_id) AS pedidos,
       SUM(f.receita_liquida) / COUNT(DISTINCT f.pedido_id) AS ticket_medio
FROM dw.fato_venda f
JOIN dw.dim_canal c ON c.canal_sk = f.canal_sk
WHERE f.status = 5
GROUP BY c.nome
ORDER BY receita DESC;

-- A3. Pedidos e receita por ano e canal.
SELECT d.ano, c.nome AS canal,
       COUNT(DISTINCT f.pedido_id) AS pedidos,
       SUM(f.receita_liquida) AS receita
FROM dw.fato_venda f
JOIN dw.dim_data d ON d.data_sk = f.data_pedido_sk
JOIN dw.dim_canal c ON c.canal_sk = f.canal_sk
WHERE f.status = 5
GROUP BY d.ano, c.nome
ORDER BY d.ano, canal;

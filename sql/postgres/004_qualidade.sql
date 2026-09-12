-- Esperado: zero linhas nas três primeiras consultas.
SELECT pedido_id,item_id,count(*) FROM dw.fato_venda
GROUP BY pedido_id,item_id HAVING count(*)>1;
SELECT pedido_id FROM dw.fato_venda
GROUP BY pedido_id HAVING count(DISTINCT (cliente_sk,territorio_sk,vendedor_sk,canal_sk,
data_pedido_sk,data_vencimento_sk,data_envio_sk,status))>1;
SELECT pedido_id,item_id FROM dw.fato_venda
WHERE abs(receita_liquida-(receita_bruta-valor_desconto))>0.000001;

SELECT status,count(*) AS itens,count(DISTINCT pedido_id) AS pedidos
FROM dw.fato_venda GROUP BY status ORDER BY status;
SELECT * FROM etl.controle;
SELECT * FROM etl.execucao ORDER BY inicio DESC;

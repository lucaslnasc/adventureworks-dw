-- Itens do mesmo pedido devem compartilhar datas, cliente, território, vendedor, canal e status.
SELECT etl.exigir(NOT EXISTS (
    SELECT pedido_id FROM dw.fato_venda
    GROUP BY pedido_id
    HAVING count(DISTINCT (data_pedido_sk, data_vencimento_sk, data_envio_sk, cliente_sk,
                           territorio_sk, vendedor_sk, canal_sk, status)) > 1
), 'Validação falhou: itens do mesmo pedido com cabeçalhos diferentes.');

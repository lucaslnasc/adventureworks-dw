-- Vencimento e envio não podem ser anteriores à data do pedido.
SELECT etl.exigir(NOT EXISTS (
    SELECT 1 FROM dw.fato_venda f
    JOIN dw.dim_data p ON p.data_sk = f.data_pedido_sk
    JOIN dw.dim_data v ON v.data_sk = f.data_vencimento_sk
    LEFT JOIN dw.dim_data e ON e.data_sk = f.data_envio_sk
    WHERE v.data < p.data OR e.data < p.data
), 'Validação falhou: datas de vencimento ou envio anteriores ao pedido.');

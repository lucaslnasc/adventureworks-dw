-- Carga da fato_venda: stage.pedido + stage.item -> dw.fato_venda.
-- Roda depois das dimensões; todo o arquivo é uma transação e avança o checkpoint de vendas.
SELECT pg_advisory_xact_lock(hashtext('carga:vendas'));
SELECT etl.exigir(EXISTS (SELECT 1 FROM stage.lote WHERE grupo = 'vendas'),
                  'Lote de vendas ausente na stage.');
-- Todo item novo ou alterado precisa do cabeçalho do pedido na mesma stage.
SELECT etl.exigir(NOT EXISTS (
           SELECT 1 FROM stage.item i
           WHERE i.operacao <> 'D'
             AND NOT EXISTS (SELECT 1 FROM stage.pedido p
                             WHERE p.sales_order_id = i.sales_order_id AND p.operacao <> 'D')),
       'Item sem cabeçalho na stage de vendas.');

-- 1. Membros inferidos: chave que chegou na venda antes de chegar na dimensão
--    (extrações correm em paralelo). A próxima carga da dimensão completa a linha.
INSERT INTO dw.dim_produto (produto_id, nome, numero_produto, subcategoria, categoria, inferido)
SELECT DISTINCT product_id, 'Não informado', 'N/I', 'Não informado', 'Não informado', true
FROM stage.item WHERE operacao <> 'D'
ON CONFLICT (produto_id) DO NOTHING;
INSERT INTO dw.dim_cliente (cliente_id, nome, tipo, inferido)
SELECT DISTINCT customer_id, 'Não informado', 'Não informado', true
FROM stage.pedido WHERE operacao <> 'D'
ON CONFLICT (cliente_id) DO NOTHING;
INSERT INTO dw.dim_territorio (territorio_id, nome, pais_codigo, grupo, inferido)
SELECT DISTINCT territory_id, 'Não informado', 'N/I', 'Não informado', true
FROM stage.pedido WHERE operacao <> 'D' AND territory_id IS NOT NULL
ON CONFLICT (territorio_id) DO NOTHING;
INSERT INTO dw.dim_vendedor (vendedor_id, nome, inferido)
SELECT DISTINCT sales_person_id, 'Não informado', true
FROM stage.pedido WHERE operacao <> 'D' AND sales_person_id IS NOT NULL
ON CONFLICT (vendedor_id) DO NOTHING;

-- 2. Exclusões: pedido excluído remove todos os itens; item excluído remove só o item.
DELETE FROM dw.fato_venda f USING stage.pedido p
WHERE p.operacao = 'D' AND f.pedido_id = p.sales_order_id;
DELETE FROM dw.fato_venda f USING stage.item i
WHERE i.operacao = 'D' AND f.pedido_id = i.sales_order_id AND f.item_id = i.sales_order_detail_id;
-- Carga completa: remove o que não existe mais na origem.
DELETE FROM dw.fato_venda f
WHERE EXISTS (SELECT 1 FROM stage.lote WHERE grupo = 'vendas' AND versao_de IS NULL)
  AND NOT EXISTS (SELECT 1 FROM stage.item i
                  WHERE i.sales_order_id = f.pedido_id AND i.sales_order_detail_id = f.item_id
                    AND i.operacao <> 'D');

-- 3. Cabeçalhos já traduzidos para as chaves substitutas do DW.
CREATE TEMP TABLE pedido_dw ON COMMIT DROP AS
SELECT p.sales_order_id AS pedido_id,
       to_char(p.order_date, 'YYYYMMDD')::integer AS data_pedido_sk,
       to_char(p.due_date, 'YYYYMMDD')::integer AS data_vencimento_sk,
       to_char(p.ship_date, 'YYYYMMDD')::integer AS data_envio_sk,
       c.cliente_sk,
       COALESCE(t.territorio_sk, 0) AS territorio_sk,
       COALESCE(v.vendedor_sk, 0) AS vendedor_sk,
       CASE WHEN p.online_order_flag THEN 1 ELSE 0 END::smallint AS canal_sk,
       p.status
FROM stage.pedido p
JOIN dw.dim_cliente c ON c.cliente_id = p.customer_id
LEFT JOIN dw.dim_territorio t ON t.territorio_id = p.territory_id
LEFT JOIN dw.dim_vendedor v ON v.vendedor_id = p.sales_person_id
WHERE p.operacao <> 'D';

-- 4. Cabeçalho alterado: atualiza os itens do pedido que já estavam no DW.
UPDATE dw.fato_venda f
SET data_pedido_sk = p.data_pedido_sk, data_vencimento_sk = p.data_vencimento_sk,
    data_envio_sk = p.data_envio_sk, cliente_sk = p.cliente_sk, territorio_sk = p.territorio_sk,
    vendedor_sk = p.vendedor_sk, canal_sk = p.canal_sk, status = p.status, carregado_em = now()
FROM pedido_dw p
WHERE f.pedido_id = p.pedido_id
  AND (f.data_pedido_sk, f.data_vencimento_sk, f.data_envio_sk, f.cliente_sk,
       f.territorio_sk, f.vendedor_sk, f.canal_sk, f.status)
      IS DISTINCT FROM
      (p.data_pedido_sk, p.data_vencimento_sk, p.data_envio_sk, p.cliente_sk,
       p.territorio_sk, p.vendedor_sk, p.canal_sk, p.status);

-- 5. Itens novos ou alterados (upsert pela chave pedido/item).
WITH gravadas AS (
    INSERT INTO dw.fato_venda AS f
        (pedido_id, item_id, data_pedido_sk, data_vencimento_sk, data_envio_sk, produto_sk,
         cliente_sk, territorio_sk, vendedor_sk, canal_sk, status,
         quantidade, preco_unitario, taxa_desconto, receita_liquida, versao_origem)
    SELECT i.sales_order_id, i.sales_order_detail_id, p.data_pedido_sk, p.data_vencimento_sk,
           p.data_envio_sk, pr.produto_sk, p.cliente_sk, p.territorio_sk, p.vendedor_sk,
           p.canal_sk, p.status, i.order_qty, i.unit_price, i.unit_price_discount,
           i.line_total, l.versao_ate
    FROM stage.item i
    JOIN pedido_dw p ON p.pedido_id = i.sales_order_id
    JOIN dw.dim_produto pr ON pr.produto_id = i.product_id
    JOIN stage.lote l ON l.grupo = 'vendas'
    WHERE i.operacao <> 'D'
    ON CONFLICT (pedido_id, item_id) DO UPDATE
        SET produto_sk = EXCLUDED.produto_sk, quantidade = EXCLUDED.quantidade,
            preco_unitario = EXCLUDED.preco_unitario, taxa_desconto = EXCLUDED.taxa_desconto,
            receita_liquida = EXCLUDED.receita_liquida, versao_origem = EXCLUDED.versao_origem,
            carregado_em = now()
        WHERE (f.produto_sk, f.quantidade, f.preco_unitario, f.taxa_desconto, f.receita_liquida)
              IS DISTINCT FROM
              (EXCLUDED.produto_sk, EXCLUDED.quantidade, EXCLUDED.preco_unitario,
               EXCLUDED.taxa_desconto, EXCLUDED.receita_liquida)
    RETURNING 1
)
SELECT etl.registrar_carga('vendas', count(*)::integer) AS linhas_gravadas FROM gravadas;

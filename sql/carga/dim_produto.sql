-- Carga da dim_produto: stage.produto -> dw.dim_produto (SCD Tipo 1).
-- Todo o arquivo roda em uma transação; o checkpoint do grupo avança no final.
SELECT pg_advisory_xact_lock(hashtext('carga:produto'));
SELECT etl.exigir(EXISTS (SELECT 1 FROM stage.lote WHERE grupo = 'produto'),
                  'Lote de produto ausente na stage.');

-- Excluídos na origem: a linha fica inativa para preservar as FKs da fato.
UPDATE dw.dim_produto d SET ativo_origem = false, atualizado_em = now()
FROM stage.produto s
WHERE s.operacao = 'D' AND s.product_id = d.produto_id AND d.ativo_origem;

-- Carga completa: inativa o que não existe mais na origem.
UPDATE dw.dim_produto d SET ativo_origem = false, atualizado_em = now()
WHERE d.ativo_origem AND NOT d.inferido
  AND EXISTS (SELECT 1 FROM stage.lote WHERE grupo = 'produto' AND versao_de IS NULL)
  AND NOT EXISTS (SELECT 1 FROM stage.produto s WHERE s.product_id = d.produto_id);

-- Inclui ou sobrescreve; só grava quando algum atributo mudou.
WITH gravadas AS (
    INSERT INTO dw.dim_produto AS d (produto_id, nome, numero_produto, cor, subcategoria, categoria)
    SELECT product_id, name, product_number, color,
           COALESCE(subcategoria, 'Sem subcategoria'), COALESCE(categoria, 'Sem categoria')
    FROM stage.produto
    WHERE operacao <> 'D'
    ON CONFLICT (produto_id) DO UPDATE
        SET nome = EXCLUDED.nome, numero_produto = EXCLUDED.numero_produto, cor = EXCLUDED.cor,
            subcategoria = EXCLUDED.subcategoria, categoria = EXCLUDED.categoria,
            ativo_origem = true, inferido = false, atualizado_em = now()
        WHERE NOT d.ativo_origem OR d.inferido
           OR (d.nome, d.numero_produto, d.cor, d.subcategoria, d.categoria)
              IS DISTINCT FROM
              (EXCLUDED.nome, EXCLUDED.numero_produto, EXCLUDED.cor, EXCLUDED.subcategoria, EXCLUDED.categoria)
    RETURNING 1
)
SELECT etl.registrar_carga('produto', count(*)::integer) AS linhas_gravadas FROM gravadas;

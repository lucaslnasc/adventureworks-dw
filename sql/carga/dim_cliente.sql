-- Carga da dim_cliente: stage.cliente -> dw.dim_cliente (SCD Tipo 1).
-- O nome vem da loja ou da pessoa; o tipo é derivado das chaves da origem.
SELECT pg_advisory_xact_lock(hashtext('carga:cliente'));
SELECT etl.exigir(EXISTS (SELECT 1 FROM stage.lote WHERE grupo = 'cliente'),
                  'Lote de cliente ausente na stage.');

UPDATE dw.dim_cliente d SET ativo_origem = false, atualizado_em = now()
FROM stage.cliente s
WHERE s.operacao = 'D' AND s.customer_id = d.cliente_id AND d.ativo_origem;

UPDATE dw.dim_cliente d SET ativo_origem = false, atualizado_em = now()
WHERE d.ativo_origem AND NOT d.inferido
  AND EXISTS (SELECT 1 FROM stage.lote WHERE grupo = 'cliente' AND versao_de IS NULL)
  AND NOT EXISTS (SELECT 1 FROM stage.cliente s WHERE s.customer_id = d.cliente_id);

WITH gravadas AS (
    INSERT INTO dw.dim_cliente AS d (cliente_id, nome, tipo)
    SELECT customer_id,
           COALESCE(store_name,
                    NULLIF(btrim(concat_ws(' ', first_name, middle_name, last_name)), ''),
                    'Não informado'),
           CASE WHEN store_id IS NOT NULL THEN 'Loja'
                WHEN person_id IS NOT NULL THEN 'Pessoa'
                ELSE 'Não informado' END
    FROM stage.cliente
    WHERE operacao <> 'D'
    ON CONFLICT (cliente_id) DO UPDATE
        SET nome = EXCLUDED.nome, tipo = EXCLUDED.tipo,
            ativo_origem = true, inferido = false, atualizado_em = now()
        WHERE NOT d.ativo_origem OR d.inferido
           OR (d.nome, d.tipo) IS DISTINCT FROM (EXCLUDED.nome, EXCLUDED.tipo)
    RETURNING 1
)
SELECT etl.registrar_carga('cliente', count(*)::integer) AS linhas_gravadas FROM gravadas;

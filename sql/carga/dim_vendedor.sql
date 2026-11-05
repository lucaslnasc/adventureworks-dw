-- Carga da dim_vendedor: stage.vendedor -> dw.dim_vendedor (SCD Tipo 1).
SELECT pg_advisory_xact_lock(hashtext('carga:vendedor'));
SELECT etl.exigir(EXISTS (SELECT 1 FROM stage.lote WHERE grupo = 'vendedor'),
                  'Lote de vendedor ausente na stage.');

UPDATE dw.dim_vendedor d SET ativo_origem = false, atualizado_em = now()
FROM stage.vendedor s
WHERE s.operacao = 'D' AND s.business_entity_id = d.vendedor_id AND d.ativo_origem;

-- O membro 0 ("Sem vendedor associado") não vem da origem e nunca é inativado.
UPDATE dw.dim_vendedor d SET ativo_origem = false, atualizado_em = now()
WHERE d.vendedor_id <> 0 AND d.ativo_origem AND NOT d.inferido
  AND EXISTS (SELECT 1 FROM stage.lote WHERE grupo = 'vendedor' AND versao_de IS NULL)
  AND NOT EXISTS (SELECT 1 FROM stage.vendedor s WHERE s.business_entity_id = d.vendedor_id);

WITH gravadas AS (
    INSERT INTO dw.dim_vendedor AS d (vendedor_id, nome)
    SELECT business_entity_id,
           COALESCE(NULLIF(btrim(concat_ws(' ', first_name, middle_name, last_name)), ''), 'Não informado')
    FROM stage.vendedor
    WHERE operacao <> 'D'
    ON CONFLICT (vendedor_id) DO UPDATE
        SET nome = EXCLUDED.nome, ativo_origem = true, inferido = false, atualizado_em = now()
        WHERE NOT d.ativo_origem OR d.inferido OR d.nome IS DISTINCT FROM EXCLUDED.nome
    RETURNING 1
)
SELECT etl.registrar_carga('vendedor', count(*)::integer) AS linhas_gravadas FROM gravadas;

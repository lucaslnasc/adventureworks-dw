-- Carga da dim_territorio: stage.territorio -> dw.dim_territorio (SCD Tipo 1).
SELECT pg_advisory_xact_lock(hashtext('carga:territorio'));
SELECT etl.exigir(EXISTS (SELECT 1 FROM stage.lote WHERE grupo = 'territorio'),
                  'Lote de território ausente na stage.');

UPDATE dw.dim_territorio d SET ativo_origem = false, atualizado_em = now()
FROM stage.territorio s
WHERE s.operacao = 'D' AND s.territory_id = d.territorio_id AND d.ativo_origem;

-- O membro 0 ("Não informado") não vem da origem e nunca é inativado.
UPDATE dw.dim_territorio d SET ativo_origem = false, atualizado_em = now()
WHERE d.territorio_id <> 0 AND d.ativo_origem AND NOT d.inferido
  AND EXISTS (SELECT 1 FROM stage.lote WHERE grupo = 'territorio' AND versao_de IS NULL)
  AND NOT EXISTS (SELECT 1 FROM stage.territorio s WHERE s.territory_id = d.territorio_id);

WITH gravadas AS (
    INSERT INTO dw.dim_territorio AS d (territorio_id, nome, pais_codigo, grupo)
    SELECT territory_id, name, country_region_code, grupo
    FROM stage.territorio
    WHERE operacao <> 'D'
    ON CONFLICT (territorio_id) DO UPDATE
        SET nome = EXCLUDED.nome, pais_codigo = EXCLUDED.pais_codigo, grupo = EXCLUDED.grupo,
            ativo_origem = true, inferido = false, atualizado_em = now()
        WHERE NOT d.ativo_origem OR d.inferido
           OR (d.nome, d.pais_codigo, d.grupo)
              IS DISTINCT FROM (EXCLUDED.nome, EXCLUDED.pais_codigo, EXCLUDED.grupo)
    RETURNING 1
)
SELECT etl.registrar_carga('territorio', count(*)::integer) AS linhas_gravadas FROM gravadas;

-- Todo lote extraído nesta execução precisa ter sido aplicado ao DW:
-- o checkpoint de cada grupo deve estar na versão e na execução do lote.
SELECT etl.exigir(count(*) = 5, 'Validação falhou: a stage não tem os cinco grupos.')
FROM stage.lote;
SELECT etl.exigir(NOT EXISTS (
    SELECT 1 FROM stage.lote l
    LEFT JOIN etl.controle c ON c.grupo = l.grupo
    WHERE c.grupo IS NULL OR c.versao <> l.versao_ate OR c.execucao_id <> l.execucao_id
), 'Validação falhou: há lote na stage que não foi aplicado ao DW.');

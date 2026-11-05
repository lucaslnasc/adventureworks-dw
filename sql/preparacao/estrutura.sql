-- Confere, sem gravar nada, se stage, DW e controle foram criados pelo init.
SELECT etl.exigir(
    to_regclass('stage.lote') IS NOT NULL AND to_regclass('stage.item') IS NOT NULL
    AND to_regclass('dw.fato_venda') IS NOT NULL AND to_regclass('dw.dim_data') IS NOT NULL
    AND to_regclass('etl.controle') IS NOT NULL AND to_regclass('dw.kpi_10_expedicao_no_prazo') IS NOT NULL,
    'Estrutura incompleta. Execute init explicitamente.');

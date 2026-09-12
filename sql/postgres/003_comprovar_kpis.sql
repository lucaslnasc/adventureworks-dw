-- Executar como script no DBeaver (Alt+X). Cada SELECT é um resultado independente.
SELECT * FROM dw.kpi_01_receita_bruta;
SELECT * FROM dw.kpi_02_descontos;
SELECT * FROM dw.kpi_03_receita_liquida;
SELECT * FROM dw.kpi_04_unidades;
SELECT * FROM dw.kpi_05_pedidos;
SELECT * FROM dw.kpi_06_ticket_medio;
SELECT * FROM dw.kpi_07_taxa_desconto;
SELECT * FROM dw.kpi_08_clientes_ativos;
SELECT * FROM dw.kpi_09_crescimento_mensal ORDER BY mes;
SELECT * FROM dw.kpi_10_expedicao_no_prazo;

-- Slice/dice: as medidas continuam no mesmo grão, apenas o agrupamento muda.
SELECT v.inicio_mes,p.categoria,t.nome AS territorio,c.nome AS canal,
 sum(v.receita_liquida) AS receita_um,count(DISTINCT v.pedido_id) AS pedidos
FROM dw.v_vendas v JOIN dw.dim_produto p USING(produto_sk)
JOIN dw.dim_territorio t USING(territorio_sk)
JOIN dw.dim_canal c USING(canal_sk)
GROUP BY v.inicio_mes,p.categoria,t.nome,c.nome
ORDER BY v.inicio_mes,p.categoria,t.nome,c.nome;

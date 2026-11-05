-- Carga da dim_data: cria os dias usados pelos pedidos da stage (pedido, vencimento, envio).
-- Não tem checkpoint próprio: depende do lote de vendas e pode ser repetida sem efeito.
SELECT pg_advisory_xact_lock(hashtext('carga:data'));

INSERT INTO dw.dim_data (data_sk, data, ano, trimestre, mes, dia, dia_semana_iso, inicio_mes)
SELECT to_char(d, 'YYYYMMDD')::integer, d::date,
       extract(year FROM d), extract(quarter FROM d), extract(month FROM d),
       extract(day FROM d), extract(isodow FROM d), date_trunc('month', d)::date
FROM (
    SELECT min(x) AS inicio, max(x) AS fim
    FROM stage.pedido p, LATERAL (VALUES (p.order_date), (p.due_date), (p.ship_date)) v(x)
    WHERE p.operacao <> 'D'
) intervalo,
LATERAL generate_series(intervalo.inicio::timestamp, intervalo.fim::timestamp, interval '1 day') d
ON CONFLICT (data_sk) DO NOTHING;

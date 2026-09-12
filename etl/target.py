"""Upserts SCD1, staging temporário, validação e checkpoint atômico."""
from datetime import date
import os
import psycopg
from psycopg import sql
from .transform import date_key, validate_line

DIM_COLS = {
    'produto': ['produto_id','nome','numero_produto','cor','subcategoria','categoria'],
    'cliente': ['cliente_id','nome','tipo'],
    'territorio': ['territorio_id','nome','pais_codigo','grupo'],
    'vendedor': ['vendedor_id','nome'],
}
FACT_COLS = ['pedido_id','item_id','data_pedido_sk','data_vencimento_sk','data_envio_sk',
    'produto_sk','cliente_sk','territorio_sk','vendedor_sk','canal_sk','status','quantidade',
    'preco_unitario','taxa_desconto','receita_liquida','versao_origem']


def connect(autocommit=False):
    # libpq lê PGHOST, PGPORT, PGDATABASE, PGUSER e PGPASSWORD.
    return psycopg.connect(autocommit=autocommit)


def apply_batch(conn, batch, fail_before_checkpoint=False):
    """Chamador controla transação e trava exclusiva; nenhum commit interno."""
    cur = conn.cursor()
    stats = {'ct_keys': batch.changes, 'dimension_rows_extracted': {},
             'dimension_rows_written': {}, 'orders_affected': len(batch.order_ids),
             'facts_extracted': len(batch.facts)}
    for name, cols in DIM_COLS.items():
        if batch.full:
            cur.execute(sql.SQL('UPDATE dw.{} SET ativo_origem=false WHERE {}<>0').format(
                sql.Identifier('dim_'+name), sql.Identifier(name+'_id')))
        else:
            live = {r[name+'_id'] for r in batch.dimensions[name]}
            deleted = sorted(set(batch.affected_dimensions[name])-live)
            cur.execute(sql.SQL('UPDATE dw.{} SET ativo_origem=false,atualizado_em=now() WHERE {}=ANY(%s) AND ativo_origem').format(
                sql.Identifier('dim_'+name),sql.Identifier(name+'_id')), (deleted,))
        fields = sql.SQL(',').join(map(sql.Identifier,cols))
        updates = sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in cols[1:])
        # WHERE evita regravação quando a tabela de origem mudou apenas campo não selecionado.
        comparisons = sql.SQL(' OR ').join(sql.SQL('d.{} IS DISTINCT FROM EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in cols[1:])
        query = sql.SQL('''INSERT INTO dw.{} AS d ({}) VALUES ({})
            ON CONFLICT ({}) DO UPDATE SET {},ativo_origem=true,atualizado_em=now()
            WHERE {} OR NOT d.ativo_origem''').format(
                sql.Identifier('dim_'+name),fields,sql.SQL(',').join(sql.Placeholder() for _ in cols),
                sql.Identifier(cols[0]),updates,comparisons)
        rows = batch.dimensions[name]
        stats['dimension_rows_extracted'][name] = len(rows)
        written = 0
        for row in rows:
            cur.execute(query, [row[c] for c in cols])
            written += cur.rowcount
        stats['dimension_rows_written'][name] = written

    dates = [r[c] for r in batch.facts for c in ('data_pedido','data_vencimento','data_envio') if r[c] is not None]
    if dates:
        cur.execute('SELECT min(data),max(data) FROM dw.dim_data')
        lo, hi = cur.fetchone()
        lower = min([min(dates)] + ([lo] if lo else []))
        upper = max([max(dates)] + ([hi] if hi else []))
        cur.execute('''INSERT INTO dw.dim_data
          SELECT to_char(d,'YYYYMMDD')::integer,d::date,extract(year FROM d),
          extract(quarter FROM d),extract(month FROM d),extract(day FROM d),
          extract(isodow FROM d),date_trunc('month',d)::date
          FROM generate_series(%s::timestamp,%s::timestamp,'1 day') d
          ON CONFLICT DO NOTHING''',(lower,upper))
    # Dimensões pequenas: mapas NK->SK evitam uma consulta por item.
    maps = {}
    for name in DIM_COLS:
        cur.execute(sql.SQL('SELECT {},{} FROM dw.{}').format(sql.Identifier(name+'_id'),
                     sql.Identifier(name+'_sk'),sql.Identifier('dim_'+name)))
        maps[name] = dict(cur.fetchall())
    cur.execute('CREATE TEMP TABLE stg_venda (LIKE dw.fato_venda INCLUDING DEFAULTS INCLUDING GENERATED) ON COMMIT DROP')
    copy_sql = sql.SQL('COPY stg_venda ({}) FROM STDIN').format(sql.SQL(',').join(map(sql.Identifier,FACT_COLS)))
    with cur.copy(copy_sql) as copy:
        for row in batch.facts:
            validate_line(row)
            try:
                values = [row['pedido_id'],row['item_id'],date_key(row['data_pedido']),
                    date_key(row['data_vencimento']),date_key(row['data_envio'])]
                values += [maps[n][row[n+'_id']] for n in DIM_COLS]
            except KeyError as exc:
                raise ValueError(f"Chave dimensional não encontrada para item {row['item_id']}") from exc
            values += [row[c] for c in ('canal_sk','status','quantidade','preco_unitario','taxa_desconto','receita_liquida')]
            values += [batch.version]
            copy.write_row(values)
    cur.execute('ALTER TABLE stg_venda ADD PRIMARY KEY(pedido_id,item_id)')
    if batch.full:
        cur.execute('DELETE FROM dw.fato_venda f WHERE NOT EXISTS (SELECT 1 FROM stg_venda s WHERE (s.pedido_id,s.item_id)=(f.pedido_id,f.item_id))')
    else:
        cur.execute('''DELETE FROM dw.fato_venda f WHERE pedido_id=ANY(%s)
        AND NOT EXISTS (SELECT 1 FROM stg_venda s WHERE (s.pedido_id,s.item_id)=(f.pedido_id,f.item_id))''',(batch.order_ids,))
    stats['facts_deleted'] = cur.rowcount
    # Só altera fatos cujos atributos/medidas diferem. Versão é a última mudança material carregada.
    data_cols = FACT_COLS[2:-1]
    updates = sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in FACT_COLS[2:])
    differences = sql.SQL(' OR ').join(sql.SQL('f.{} IS DISTINCT FROM EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in data_cols)
    fields = sql.SQL(',').join(map(sql.Identifier,FACT_COLS))
    cur.execute(sql.SQL('''INSERT INTO dw.fato_venda AS f ({}) SELECT {} FROM stg_venda
        ON CONFLICT(pedido_id,item_id) DO UPDATE SET {},carregado_em=now() WHERE {}''').format(fields,fields,updates,differences))
    stats['facts_written'] = cur.rowcount
    # Conferência do lote após o upsert: quantidade e receita reconciliam em nível de item.
    cur.execute('''SELECT count(*) FROM stg_venda s LEFT JOIN dw.fato_venda f
      USING(pedido_id,item_id) WHERE f.item_id IS NULL OR
      (f.quantidade,f.receita_liquida) IS DISTINCT FROM (s.quantidade,s.receita_liquida)''')
    if cur.fetchone()[0]:
        raise RuntimeError('Reconciliação do lote falhou')
    if fail_before_checkpoint:
        raise RuntimeError('Falha injetada antes do checkpoint para testar rollback')
    cur.execute('''INSERT INTO etl.controle(pipeline,versao,identidade_origem)
        VALUES('vendas',%s,%s) ON CONFLICT(pipeline) DO UPDATE
        SET versao=excluded.versao,identidade_origem=excluded.identidade_origem,atualizado_em=now()''',
        (batch.version,batch.identity))
    return stats

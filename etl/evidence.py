"""Auditoria explícita lê toda a fonte; não faz parte da carga incremental regular."""
import json
from pathlib import Path
from datetime import datetime, timezone
from . import source, target
from .pipeline import LOCK_KEY
from .transform import json_value


def save(name, payload):
    folder = Path('evidence')
    folder.mkdir(exist_ok=True)
    (folder/name).write_text(json.dumps(payload,default=json_value,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(payload,default=json_value,indent=2,ensure_ascii=False))


def report():
    with target.connect() as conn:
        # Dez consultas e checkpoint precisam representar a mesma carga confirmada.
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        views = conn.execute("SELECT table_name FROM information_schema.views WHERE table_schema='dw' AND table_name LIKE 'kpi_%%' ORDER BY table_name").fetchall()
        result = {}
        for (view,) in views:
            cur = conn.execute('SELECT * FROM dw.'+view + (' ORDER BY mes' if view.startswith('kpi_09') else ''))
            cols = [c.name for c in cur.description]
            result[view] = [dict(zip(cols,r)) for r in cur.fetchall()]
        checkpoint = conn.execute('SELECT versao FROM etl.controle').fetchone()
    save('kpis.json',{'gerado_em':datetime.now(timezone.utc),'versao':checkpoint[0] if checkpoint else None,'indicadores':result})


def verify():
    conn = target.connect(autocommit=True)
    try:
        if not conn.execute('SELECT pg_try_advisory_lock(%s)',(LOCK_KEY,)).fetchone()[0]:
            raise RuntimeError('ETL em execução; tente novamente')
        state = conn.execute("SELECT versao,identidade_origem FROM etl.controle WHERE pipeline='vendas'").fetchone()
        if not state:
            raise RuntimeError('Execute a carga antes de verificar')
        batch = source.extract(None,state[1])
        if batch.version != state[0]:
            raise RuntimeError('Origem mudou desde a carga. Execute run e verify em janela sem escritas.')
        cur = conn.execute('''SELECT f.pedido_id,f.item_id,d.data AS data_pedido,v.data AS data_vencimento,
          e.data AS data_envio,p.produto_id,c.cliente_id,t.territorio_id,s.vendedor_id,
          f.canal_sk,f.status,f.quantidade,f.preco_unitario,f.taxa_desconto,f.receita_liquida
          FROM dw.fato_venda f JOIN dw.dim_data d ON d.data_sk=f.data_pedido_sk
          JOIN dw.dim_data v ON v.data_sk=f.data_vencimento_sk
          LEFT JOIN dw.dim_data e ON e.data_sk=f.data_envio_sk
          JOIN dw.dim_produto p USING(produto_sk) JOIN dw.dim_cliente c USING(cliente_sk)
          JOIN dw.dim_territorio t USING(territorio_sk) JOIN dw.dim_vendedor s USING(vendedor_sk)''')
        cols = [c.name for c in cur.description]
        actual = {(r[0],r[1]):dict(zip(cols,r)) for r in cur.fetchall()}
        expected = {(r['pedido_id'],r['item_id']):r for r in batch.facts}
        mismatches = [k for k in expected.keys()|actual.keys() if expected.get(k)!=actual.get(k)]
        result = {'gerado_em':datetime.now(timezone.utc),'versao':batch.version,
          'itens_origem':len(expected),'itens_dw':len(actual),'itens_divergentes':len(mismatches),
          'amostra_chaves_divergentes':mismatches[:20],
          'receita_origem_todos_status':sum(r['receita_liquida'] for r in expected.values()),
          'receita_dw_todos_status':sum(r['receita_liquida'] for r in actual.values()),
          'resultado':'PASS' if not mismatches else 'FAIL'}
        save('reconciliation.json',result)
        if mismatches:
            raise RuntimeError('Reconciliação encontrou divergências')
    finally:
        conn.close()

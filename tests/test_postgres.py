"""Integração real com PostgreSQL; lotes sintéticos, sem simular Change Tracking."""
import os
from copy import deepcopy
from decimal import Decimal as D
import pytest
from etl import target, setup, pipeline
from .fixtures import sample_batch, delta

pytestmark = pytest.mark.skipif(not os.getenv('DW_TEST_DATABASE'),reason='Defina DW_TEST_DATABASE=test_aw_dw para integração')


@pytest.fixture
def db(monkeypatch):
    name=os.environ['DW_TEST_DATABASE']
    if not name.startswith('test_'):
        raise RuntimeError('Testes só podem usar banco exclusivo com prefixo test_')
    monkeypatch.setenv('PGDATABASE',name)
    with target.connect() as conn:
        conn.execute('DROP SCHEMA IF EXISTS dw CASCADE; DROP SCHEMA IF EXISTS etl CASCADE')
    setup.init_dw()
    conn=target.connect(autocommit=True)
    yield conn
    conn.close()


def apply(db,batch,fail=False):
    with db.transaction():
        return target.apply_batch(db,batch,fail)


def scalar(db,query):
    return db.execute(query).fetchone()[0]


def test_all_ten_kpis_and_missing_month(db):
    apply(db,sample_batch())
    expected={1:D(310),2:D(20),3:D(290),4:6,5:2,6:D(145),8:2}
    views=db.execute("SELECT table_name FROM information_schema.views WHERE table_schema='dw' AND table_name LIKE 'kpi_%' ORDER BY table_name").fetchall()
    assert len(views)==10
    for (view,) in views:
        number=int(view.split('_')[1])
        if number in expected:
            assert scalar(db,'SELECT * FROM dw.'+view)==expected[number]
    pct=scalar(db,'SELECT * FROM dw.kpi_07_taxa_desconto')
    assert abs(pct-D(100)*D(20)/D(310))<D('.000000001')
    months=db.execute('SELECT receita,crescimento_pct FROM dw.kpi_09_crescimento_mensal ORDER BY mes').fetchall()
    assert months==[(D(230),None),(D(0),D(-100)),(D(60),None)]
    assert db.execute('SELECT * FROM dw.kpi_10_expedicao_no_prazo').fetchone()==(2,0,1,D(50))


def test_idempotence_and_noop(db):
    apply(db,sample_batch())
    before=db.execute('SELECT pedido_id,item_id,carregado_em FROM dw.fato_venda ORDER BY 1,2').fetchall()
    stats=apply(db,delta(11))
    assert stats['facts_extracted']==stats['facts_written']==stats['facts_deleted']==0
    assert before==db.execute('SELECT pedido_id,item_id,carregado_em FROM dw.fato_venda ORDER BY 1,2').fetchall()
    replay=delta(12,sample_batch().facts,[1,2,3])
    assert apply(db,replay)['facts_written']==0


def test_insert_update_and_delete(db):
    batch=sample_batch()
    apply(db,batch)
    new=deepcopy(batch.facts[2]); new.update(pedido_id=4,item_id=5)
    assert apply(db,delta(11,[new],[4]))['facts_written']==1
    changed=deepcopy(batch.facts[:2])
    changed[0].update(quantidade=3,receita_liquida=D(270))
    assert apply(db,delta(12,changed,[1]))['facts_written']==1
    assert scalar(db,'SELECT receita_liquida FROM dw.fato_venda WHERE item_id=1')==270
    assert apply(db,delta(13,changed[:1],[1]))['facts_deleted']==1
    assert apply(db,delta(14,[],[4]))['facts_deleted']==1


def test_header_change_updates_all_order_items(db):
    batch=sample_batch(); apply(db,batch)
    rows=deepcopy(batch.facts[:2])
    for row in rows:
        row['status']=6
    assert apply(db,delta(11,rows,[1]))['facts_written']==2
    assert scalar(db,'SELECT * FROM dw.kpi_03_receita_liquida')==60


def test_scd1_preserves_surrogate_keys(db):
    batch=sample_batch(); apply(db,batch)
    sk=scalar(db,'SELECT produto_sk FROM dw.dim_produto WHERE produto_id=1')
    update=delta(11)
    update.dimensions['produto']=[dict(batch.dimensions['produto'][0],categoria='Nova categoria')]
    update.affected_dimensions['produto']=[1]
    stats=apply(db,update)
    assert stats['facts_written']==0
    assert scalar(db,'SELECT produto_sk FROM dw.dim_produto WHERE produto_id=1')==sk
    assert scalar(db,'SELECT categoria FROM dw.dim_produto WHERE produto_id=1')=='Nova categoria'


def test_atomic_rollback_and_recovery(db):
    batch=sample_batch(); apply(db,batch)
    row=deepcopy(batch.facts[2]); row.update(quantidade=4,receita_liquida=D(80))
    update=delta(11,[row],[2])
    with pytest.raises(RuntimeError,match='Falha injetada'):
        apply(db,update,True)
    assert scalar(db,'SELECT versao FROM etl.controle')==10
    assert scalar(db,'SELECT receita_liquida FROM dw.fato_venda WHERE item_id=3')==60
    apply(db,update)
    assert scalar(db,'SELECT versao FROM etl.controle')==11


def test_invalid_dimension_rolls_back(db):
    apply(db,sample_batch())
    row=sample_batch().facts[0]; row['produto_id']=999
    with pytest.raises(ValueError,match='Chave dimensional'):
        apply(db,delta(11,[row],[1]))
    assert scalar(db,'SELECT count(*) FROM dw.fato_venda')==4
    assert scalar(db,'SELECT versao FROM etl.controle')==10


def test_full_resync_removes_stale_facts_keeps_keys(db):
    batch=sample_batch(); apply(db,batch)
    sk=scalar(db,'SELECT produto_sk FROM dw.dim_produto WHERE produto_id=1')
    batch.version=12; batch.facts=batch.facts[:2]; batch.order_ids=[1]
    stats=apply(db,batch)
    assert stats['facts_deleted']==2
    assert scalar(db,'SELECT produto_sk FROM dw.dim_produto WHERE produto_id=1')==sk


def test_audit_failure_and_retry(db,monkeypatch):
    monkeypatch.setattr(pipeline.source,'extract',lambda last,identity: sample_batch())
    with pytest.raises(RuntimeError,match='Falha injetada'):
        pipeline.run(fail_before_checkpoint=True)
    assert scalar(db,"SELECT count(*) FROM etl.execucao WHERE status='failed'")==1
    assert scalar(db,'SELECT count(*) FROM etl.controle')==0
    pipeline.run()
    assert scalar(db,"SELECT count(*) FROM etl.execucao WHERE status='success'")==1


def test_concurrent_run_refused(db,monkeypatch):
    db.execute('SELECT pg_advisory_lock(%s)',(pipeline.LOCK_KEY,))
    try:
        with pytest.raises(RuntimeError,match='Já existe'):
            pipeline.run()
    finally:
        db.execute('SELECT pg_advisory_unlock(%s)',(pipeline.LOCK_KEY,))


def test_empty_denominators(db):
    assert scalar(db,'SELECT * FROM dw.kpi_01_receita_bruta')==0
    assert scalar(db,'SELECT * FROM dw.kpi_06_ticket_medio') is None
    assert scalar(db,'SELECT * FROM dw.kpi_07_taxa_desconto') is None
    assert scalar(db,'SELECT expedicao_no_prazo_pct FROM dw.kpi_10_expedicao_no_prazo') is None


def test_missing_shipping_date_is_visible(db):
    batch=sample_batch()
    for row in batch.facts[:2]:
        row['data_envio']=None
    apply(db,batch)
    assert db.execute('SELECT * FROM dw.kpi_10_expedicao_no_prazo').fetchone()==(1,1,0,D(0))

"""Teste opcional real de Change Tracking + PostgreSQL. Nunca usa a base AdventureWorks."""
import os
import re
import uuid
from pathlib import Path
from decimal import Decimal
import pytest
from etl import source, setup, pipeline
from .test_postgres import db, scalar

pytestmark=pytest.mark.skipif(os.getenv('RUN_SQLSERVER_TESTS')!='1',reason='Requer SQL Server; defina RUN_SQLSERVER_TESTS=1')


@pytest.fixture
def oltp(monkeypatch):
    # Nome aleatório criado pelo próprio teste; nunca remove um banco preexistente.
    name='test_aw_'+uuid.uuid4().hex
    master=source.connect('master',autocommit=True)
    master.cursor().execute(f'CREATE DATABASE [{name}]')
    monkeypatch.setenv('SOURCE_DB',name)
    conn=source.connect(autocommit=True)
    try:
        text=(Path(__file__).parent/'sqlserver_fixture.sql').read_text(encoding='utf-8')
        for batch in re.split(r'^GO\s*$',text,flags=re.MULTILINE):
            if batch.strip():
                cur=conn.cursor();cur.execute(batch)
                while cur.nextset():
                    pass
        setup.prepare_source()
        yield conn
    finally:
        conn.close()
        cur=master.cursor()
        cur.execute(f'ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{name}]')
        master.close()


def test_incremental_snapshot_empty_changed_and_deleted_orders(oltp):
    """Regressão do erro 3964, sem tocar no DW nem no AdventureWorks real."""
    first = source.extract(None)
    empty = source.extract(first.version, first.identity)
    assert empty.full is False
    assert empty.order_ids == []
    assert empty.facts == []

    cur = oltp.cursor()
    # A mesma chave aparece no CT do cabeçalho e do item: deve ser deduplicada.
    cur.execute('UPDATE Sales.SalesOrderHeader SET Status=6 WHERE SalesOrderID=1')
    cur.execute('UPDATE Sales.SalesOrderDetail SET OrderQty=3 WHERE SalesOrderID=1')
    changed = source.extract(empty.version, empty.identity)
    assert changed.order_ids == [1]
    assert len(changed.facts) == 1
    assert changed.facts[0]['quantidade'] == 3
    assert changed.facts[0]['status'] == 6

    cur.execute('DELETE FROM Sales.SalesOrderDetail WHERE SalesOrderID=1')
    deleted = source.extract(changed.version, changed.identity)
    assert deleted.order_ids == [1]
    assert deleted.facts == []


def test_actual_change_tracking_end_to_end(db,oltp):
    first=pipeline.run()
    assert first['facts_written']==1
    assert pipeline.run()['facts_extracted']==0
    cur=oltp.cursor()
    # UPDATE sem ModifiedDate.
    cur.execute('UPDATE Sales.SalesOrderDetail SET OrderQty=3 WHERE SalesOrderID=1')
    update=pipeline.run()
    assert update['ct_keys']['detail']==1
    assert scalar(db,'SELECT receita_liquida FROM dw.fato_venda')==Decimal(270)
    cur.execute("UPDATE Production.ProductCategory SET Name=N'Nova categoria' WHERE ProductCategoryID=1")
    dimension=pipeline.run()
    assert dimension['dimension_rows_written']['produto']==1
    assert dimension['facts_extracted']==0
    assert scalar(db,'SELECT categoria FROM dw.dim_produto')=='Nova categoria'
    cur.execute("UPDATE Person.Person SET FirstName=N'Beatriz' WHERE BusinessEntityID=1")
    pipeline.run()
    assert scalar(db,'SELECT nome FROM dw.dim_cliente')=='Beatriz  Silva'
    cur.execute("INSERT INTO Sales.SalesOrderDetail VALUES(1,2,1,1,50,0,'20240110')")
    assert pipeline.run()['facts_written']==1
    cur.execute('UPDATE Sales.SalesOrderHeader SET Status=6 WHERE SalesOrderID=1')
    assert pipeline.run()['facts_written']==2
    assert scalar(db,'SELECT * FROM dw.kpi_03_receita_liquida')==0
    cur.execute('DELETE FROM Sales.SalesOrderDetail WHERE SalesOrderDetailID=2')
    assert pipeline.run()['facts_deleted']==1
    cur.execute('UPDATE Sales.SalesOrderDetail SET OrderQty=4 WHERE SalesOrderDetailID=1')
    checkpoint=scalar(db,'SELECT versao FROM etl.controle')
    with pytest.raises(RuntimeError,match='Falha injetada'):
        pipeline.run(fail_before_checkpoint=True)
    assert scalar(db,'SELECT versao FROM etl.controle')==checkpoint
    pipeline.run()
    assert scalar(db,'SELECT receita_liquida FROM dw.fato_venda')==360
    assert pipeline.run()['facts_extracted']==0


def test_commit_during_snapshot_is_loaded_next_time(db,oltp,monkeypatch):
    pipeline.run()
    original_connect=source.connect
    fired=False
    class CursorProxy:
        def __init__(self,cur): self.cur=cur
        def execute(self,query,*args):
            nonlocal fired
            result=self.cur.execute(query,*args)
            if 'CHANGE_TRACKING_CURRENT_VERSION() AS version' in query and not fired:
                fired=True
                oltp.cursor().execute('UPDATE Sales.SalesOrderDetail SET OrderQty=5 WHERE SalesOrderID=1')
            return result
        def __getattr__(self,name): return getattr(self.cur,name)
    class ConnectionProxy:
        def __init__(self,conn): self.conn=conn
        def cursor(self,*a,**kw): return CursorProxy(self.conn.cursor(*a,**kw))
        def __getattr__(self,name): return getattr(self.conn,name)
    monkeypatch.setattr(source,'connect',lambda *a,**kw:ConnectionProxy(original_connect(*a,**kw)))
    assert pipeline.run()['facts_extracted']==0
    assert pipeline.run()['facts_written']==1
    assert scalar(db,'SELECT receita_liquida FROM dw.fato_venda')==450

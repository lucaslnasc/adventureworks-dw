"""Coordena extração e confirmação; a origem nunca é modificada pela carga."""
import uuid
from psycopg.types.json import Jsonb
from . import source, target

LOCK_KEY = 601602603


def run(resync=False, fail_before_checkpoint=False):
    conn = target.connect(autocommit=True)
    run_id = uuid.uuid4()
    registered = False
    try:
        if not conn.execute('SELECT pg_try_advisory_lock(%s)',(LOCK_KEY,)).fetchone()[0]:
            raise RuntimeError('Já existe uma carga ou reconciliação em execução')
        # Com a trava adquirida, registros running anteriores pertencem a processos interrompidos.
        conn.execute("UPDATE etl.execucao SET status='failed',fim=now(),erro='Processo anterior interrompido; checkpoint preservado' WHERE status='running'")
        state = conn.execute("SELECT versao,identidade_origem FROM etl.controle WHERE pipeline='vendas'").fetchone()
        last = None if resync or state is None else state[0]
        expected_identity = None if last is None else state[1]
        mode = 'resync' if resync else ('initial' if state is None else 'incremental')
        conn.execute('''INSERT INTO etl.execucao(execucao_id,status,modo,versao_anterior)
            VALUES(%s,'running',%s,%s)''',(run_id,mode,state[0] if state else None))
        registered = True
        batch = source.extract(last,expected_identity)
        with conn.transaction():
            stats = target.apply_batch(conn,batch,fail_before_checkpoint)
            conn.execute('''UPDATE etl.execucao SET status='success',fim=now(),
                versao_nova=%s,estatisticas=%s WHERE execucao_id=%s''',
                (batch.version,Jsonb(stats),run_id))
        return {'execucao_id':str(run_id),'modo':mode,'versao':batch.version,**stats}
    except Exception as exc:
        if registered:
            # Classe e mensagem de regras locais; não registra credenciais/DSN.
            message = str(exc)[:800] if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__
            conn.execute("UPDATE etl.execucao SET status='failed',fim=now(),erro=%s WHERE execucao_id=%s",(message,run_id))
        raise
    finally:
        # Fechar a sessão libera a advisory lock mesmo após erro.
        conn.close()

"""Restauração sem REPLACE: uma base existente nunca é sobrescrita."""
from pathlib import Path
import re
import os
from .source import connect
from . import target

ROOT = Path(__file__).resolve().parents[1]


def init_dw():
    with target.connect() as conn:
        for name in ('001_schema.sql','002_kpis.sql'):
            conn.execute((ROOT/'sql'/'postgres'/name).read_text(encoding='utf-8'))


def restore():
    db = os.getenv('SOURCE_DB','AdventureWorks2016')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,60}',db):
        raise ValueError('Nome de banco inválido')
    conn = connect('master',autocommit=True)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute('SELECT DB_ID(%s) AS id',(db,))
        if cur.fetchone()['id'] is not None:
            print('Base já existe; restauração ignorada para preservar os dados.')
            return
        backup = '/var/opt/mssql/backup/AdventureWorks2016.bak'
        cur.execute('RESTORE FILELISTONLY FROM DISK=%s',(backup,))
        files = list(cur.fetchall())
        if len(files)!=2 or {f['Type'] for f in files}!={'D','L'}:
            raise RuntimeError('Backup inesperado. Inspecione RESTORE FILELISTONLY manualmente.')
        moves, params = [], [backup]
        for f in files:
            moves.append('MOVE %s TO %s')
            params += [f['LogicalName'],f"/var/opt/mssql/data/{db}{'.mdf' if f['Type']=='D' else '_log.ldf'}"]
        cur.execute(f"RESTORE DATABASE [{db}] FROM DISK=%s WITH "+', '.join(moves),tuple(params))
        while cur.nextset():
            pass
        print(f'Banco {db} restaurado.')
    finally:
        conn.close()


def prepare_source():
    conn = connect(autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute((ROOT/'sql'/'sqlserver'/'001_change_tracking.sql').read_text(encoding='utf-8'))
        while cur.nextset():
            pass
    finally:
        conn.close()

"""Merge two stopped, consistent backup folders into a new installation only."""
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from contextlib import closing
from dotenv import dotenv_values
from .app import Config
from .display import Display
from .store import Store

TABLES = ('bots','admins','targets','links','users','jobs','content','incidents','payment_accounts',
          'payment_packages','payment_orders','payment_events','payment_started','payment_qr_messages','display_screens','userbots','telegram_profiles')
ENCRYPTED = {'bots':('credentials',),'payment_accounts':('secret',),'payment_orders':('qr','invite','accesses'),'userbots':('credentials',)}


def quote(name):
    return '"'+name.replace('"','""')+'"'


def merge(force_folder, payment_folder, output):
    folders = [Path(force_folder).resolve(),Path(payment_folder).resolve()]
    output = Path(output).resolve()
    configs = [Config.read(dotenv_values(folder/'config.env')) for folder in folders]
    if configs[0].token != configs[1].token or configs[0].owner != configs[1].owner:
        raise ValueError('Kedua cadangan harus memakai bot induk dan pemilik yang sama.')
    fingerprints=[]
    for folder in folders:
        if (folder/'subgate.sqlite-wal').exists():
            raise ValueError('Gunakan cadangan SQLite mandiri, bukan database aktif dengan WAL.')
        fingerprints.append(hashlib.sha256((folder/'subgate.sqlite').read_bytes()).hexdigest())
    receipt=output/'migration.json'
    if receipt.exists():
        previous=json.loads(receipt.read_text())
        if previous['sources']!=fingerprints: raise ValueError('Tujuan sudah berisi migrasi lain.')
        return previous
    if output.exists(): raise ValueError('Tujuan harus berupa folder baru yang belum ada.')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.'+output.name+'-migration-',dir=output.parent)).resolve()
    pending=stage/'ready'
    pending.mkdir()
    target_path=pending/'data/subgate.sqlite'
    stores=[]
    try:
        (pending/'.gitignore').write_text('*'+chr(10),encoding='utf-8')
        for index,folder in enumerate(folders):
            shutil.copyfile(folder/'subgate.sqlite',stage/(str(index)+'.sqlite'))
        for index,config in enumerate(configs):
            stores.append(Store(stage/(str(index)+'.sqlite'),config.key,config.owner))
        target,source=stores
        for db in stores: Display(db.conn,None)
        if any(row['kind']!='forcesubs' for row in target.bots()) or any(row['kind']!='payment' for row in source.bots()):
            raise ValueError('Cadangan pertama harus ForceSubs dan cadangan kedua harus Payment.')
        overlap={r['id'] for r in target.bots()} & {r['id'] for r in source.bots()}
        if any(target.bot(bot)['owner']!=source.bot(bot)['owner'] for bot in overlap):
            raise ValueError('Bot bertabrakan dengan pemilik berbeda; migrasi dibatalkan.')
        known=set(TABLES)|{'creators','creator_permissions','sqlite_sequence'}
        unknown=[r['name'] for r in source.rows("SELECT name FROM sqlite_master WHERE type='table'") if r['name'] not in known]
        if unknown: raise ValueError('Ada tabel yang belum didukung migrasi; data tidak diubah.')
        legacy_admins={bot:target.admins(bot) for bot in overlap}
        with target.conn:
            for bot in overlap:target.conn.execute('DELETE FROM admins WHERE bot=?',(bot,))
            for row in source.rows('SELECT * FROM creators'):
                target.conn.execute('INSERT INTO creators VALUES (?,?) ON CONFLICT(id) DO UPDATE SET allowed=MAX(creators.allowed,excluded.allowed)',(row['id'],row['allowed']))
            for row in source.rows('SELECT * FROM creator_permissions'):
                target.conn.execute('INSERT INTO creator_permissions VALUES (?,?,?) ON CONFLICT(user,kind) DO UPDATE SET allowed=MAX(creator_permissions.allowed,excluded.allowed)',(row['user'],row['kind'],row['allowed']))
            for table in TABLES:
                info=source.rows('PRAGMA table_info('+quote(table)+')')
                primary=[r['name'] for r in sorted(info,key=lambda r:r['pk']) if r['pk']]
                for original in source.rows('SELECT * FROM '+quote(table)):
                    row=dict(original)
                    if table=='bots' and row['id'] in overlap:
                        old=json.loads(target.bot(row['id'])['settings'])
                        settings=json.loads(row['settings'])
                        settings.update({key:value for key,value in old.items() if not key.startswith('payment_')})
                        settings['legacy_forcesubs']=True
                        settings['legacy_force_admins']=legacy_admins[row['id']]
                        row['settings']=json.dumps(settings)
                    for column in ENCRYPTED.get(table,()):
                        if row[column] is not None: row[column]=target.cipher.encrypt(source.cipher.decrypt(row[column]))
                    if table=='jobs':row.pop('id',None)
                    elif primary:
                        where=' AND '.join(quote(k)+'=?' for k in primary)
                        existing=target.rows('SELECT * FROM '+quote(table)+' WHERE '+where,tuple(row[k] for k in primary))
                        if existing:
                            if table=='telegram_profiles': continue
                            if table=='bots' and row['id'] in overlap:
                                columns=[key for key in row if key!='id']
                                target.conn.execute('UPDATE bots SET '+','.join(quote(c)+'=?' for c in columns)+' WHERE id=?',tuple(row[c] for c in columns)+(row['id'],))
                                continue
                            if existing[0]!=row: raise ValueError('Ada baris data yang bertabrakan; migrasi dibatalkan.')
                            continue
                    columns=list(row)
                    target.conn.execute('INSERT INTO '+quote(table)+' ('+','.join(quote(c) for c in columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(row[c] for c in columns))
        if target.rows('PRAGMA foreign_key_check') or target.conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('Pemeriksaan database gabungan gagal.')
        for row in target.bots(): target.credentials(row['id'])
        for table,columns in ENCRYPTED.items():
            for row in target.rows('SELECT * FROM '+quote(table)):
                for column in columns:
                    if row[column] is not None:target.cipher.decrypt(row[column])
        target_path.parent.mkdir(exist_ok=True)
        with closing(sqlite3.connect(target_path)) as destination:target.conn.backup(destination)
        config=(folders[0]/'config.env').read_text(encoding='utf-8-sig')
        (pending/'config.env').write_text(config+'\nDATA_DIR=./data\nCREATION_ENABLE=0\n',encoding='utf-8')
        result={'sources':fingerprints,'bots':len(target.bots()),'payment_orders':len(target.rows('SELECT id FROM payment_orders')),'integrity':'ok'}
        (pending/'migration.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        pending.rename(output)
        return result
    finally:
        for db in stores: db.close()
        # Only the generated sibling staging directory belongs to this operation.
        if stage.parent==output.parent and stage.name.startswith('.'+output.name+'-migration-'):
            shutil.rmtree(stage)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forcesubs',required=True)
    parser.add_argument('--payment',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:
        print(json.dumps(merge(args.forcesubs,args.payment,args.output)))
    except Exception:
        raise SystemExit('Migrasi belum selesai. Tujuan tidak diaktifkan; cadangan sumber tetap dipertahankan.') from None


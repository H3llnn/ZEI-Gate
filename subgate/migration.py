"""Checkpointed owner transfers. Payloads travel in bounded authenticated chunks."""
import asyncio
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import time

VERSION = 1
CHUNK = 4500
MAX_BYTES = 64 * 1024 * 1024
CRYPT = {'bots': ('credentials',), 'userbots': ('credentials',),
         'payment_accounts': ('secret',), 'payment_orders': ('qr', 'invite', 'accesses')}
log = logging.getLogger(__name__)


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def encoded(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode()


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def bot_tables(db):
    return [r['name'] for r in db.rows("SELECT name FROM sqlite_master WHERE type='table'")
            if r['name'] != 'worker_versions' and not r['name'].endswith('_receipt')
            and any(c['name'] == 'bot' for c in db.rows('PRAGMA table_info('+quoted(r['name'])+')'))]


class MigrationNode:
    def __init__(self, db, manager, directory):
        self.db, self.manager, self.directory = db, manager, Path(directory)
        from .display import Display
        Display(db.conn, None)
        self.db.conn.executescript('''
            CREATE TABLE IF NOT EXISTS migration_cache (
                job TEXT PRIMARY KEY, payload BLOB NOT NULL, digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS migration_receipts (
                job TEXT PRIMARY KEY, digest TEXT NOT NULL, receipt TEXT NOT NULL);
        ''')

    def backup(self, job):
        folder = self.directory/'migration-backups'/job
        if (folder/'ready').exists():
            return
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = sqlite3.connect(folder/'subgate.sqlite')
        try:
            self.db.conn.backup(target)
        finally:
            target.close()
        for source in (self.directory/'worker-identity.json', Path('config.env')):
            if source.exists():
                shutil.copyfile(source, folder/source.name)
        # Userbot settings are copied after its process has stopped.
        owner = self.db.rows('SELECT owner FROM migration_holds WHERE job=?', (job,))[0]['owner']
        state = self.manager.userbots.directory/str(owner)/'settings.sqlite'
        if state.exists():
            source = sqlite3.connect(state)
            target = sqlite3.connect(folder/'settings.sqlite')
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
        (folder/'ready').write_text('1', encoding='utf-8')
        for path in folder.iterdir():
            os.chmod(path, 0o600)

    async def freeze(self, job, owner, role):
        with self.db.conn:
            self.db.conn.execute('INSERT INTO migration_holds VALUES (?,?,?) ON CONFLICT(owner) DO UPDATE SET job=excluded.job,role=excluded.role',
                                 (owner, job, role))
        async with self.manager.lock:
            # Maintenance may already be inside a Telegram request when the hold is set.
            task = self.manager.maintenance_task
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                self.manager.maintenance_task = None
            try:
                for bot in self.db.bots(owner):
                    runner = self.manager.running.pop(bot['id'], None)
                    if runner:
                        await runner.stop()
                runner = self.manager.userbots.running.pop(owner, None)
                if runner:
                    await runner.stop()
                self.backup(job)
            finally:
                if task:
                    self.manager.maintenance_task = asyncio.create_task(self.manager.maintenance())

    def collect(self, owner):
        db = self.db
        data = {'bots': db.bots(owner)}
        for table in bot_tables(db):
            data[table] = db.rows('SELECT * FROM '+quoted(table)+' WHERE bot IN (SELECT id FROM bots WHERE owner=?)', (owner,))
        for table in ('userbots', 'payment_accounts', 'payment_events'):
            data[table] = db.rows('SELECT * FROM '+table+' WHERE owner=?', (owner,))
        data['creators'] = db.rows('SELECT * FROM creators WHERE id=?', (owner,))
        data['creator_permissions'] = db.rows('SELECT * FROM creator_permissions WHERE user=?', (owner,))
        ids = {owner}
        for table in ('users', 'admins', 'payment_started'):
            ids.update(r['user'] for r in data.get(table, []))
        ids.update(r['buyer'] for r in data.get('payment_orders', []))
        data['telegram_profiles'] = [r for r in db.rows('SELECT * FROM telegram_profiles') if r['id'] in ids]
        columns = {t: [r['name'] for r in db.rows('PRAGMA table_info('+quoted(t)+')')] for t in data}
        for table, records in data.items():
            for row in records:
                for column in CRYPT.get(table, ()):
                    if row[column] is not None:
                        row[column] = db.cipher.decrypt(row[column])
                for key, value in row.items():
                    if isinstance(value, bytes):
                        row[key] = {'blob': base64.b64encode(value).decode()}
        state = self.manager.userbots.directory/str(owner)/'settings.sqlite'
        account = {}
        if data['userbots'] and state.exists():
            conn = sqlite3.connect(state)
            try:
                account = {t: conn.execute('SELECT * FROM '+t).fetchall() for t in ('settings', 'notes')}
            finally:
                conn.close()
        return {'version': VERSION, 'owner': owner, 'columns': columns, 'tables': data, 'account': account}

    async def export(self, command):
        job, owner = command['id'], command['owner']
        await self.freeze(job, owner, 'source')
        cached = self.db.rows('SELECT payload FROM migration_cache WHERE job=?', (job,))
        if cached:
            return self.db.cipher.decrypt(cached[0]['payload'])
        payload = encoded(self.collect(owner))
        if len(payload) > MAX_BYTES:
            raise ValueError('Data migrasi melebihi batas 64 MiB.')
        with self.db.conn:
            self.db.conn.execute('INSERT INTO migration_cache VALUES (?,?,?)',
                                 (job, self.db.cipher.encrypt(payload), checksum(payload)))
        return payload

    def validate(self, payload, command):
        data = json.loads(payload)
        tables, spec = data['tables'], command['spec']
        if data['version'] != VERSION or data['owner'] != command['owner']:
            raise ValueError('Identitas snapshot berubah.')
        allowed = set(bot_tables(self.db)) | {'bots', 'userbots', 'payment_accounts', 'payment_events',
                                              'creators', 'creator_permissions', 'telegram_profiles'}
        if set(tables) != allowed or set(data['columns']) != allowed:
            raise ValueError('Versi skema server belum cocok. Perbarui kedua server.')
        for table in tables:
            columns = [r['name'] for r in self.db.rows('PRAGMA table_info('+quoted(table)+')')]
            if data['columns'][table] != columns or any(set(r) != set(columns) for r in tables[table]):
                raise ValueError('Versi kolom server belum cocok.')
        ids = {r['id'] for r in spec['bots']}
        if {r['id'] for r in tables['bots']} != ids:
            raise ValueError('Daftar bot sumber berubah.')
        kinds = {r['id']:r['kind'] for r in spec['bots']}
        if any(kinds[r['id']] != r['kind'] for r in tables['bots']):
            raise ValueError('Jenis bot sumber berubah.')
        owner = command['owner']
        for table, records in tables.items():
            for row in records:
                if ('bot' in row and row['bot'] not in ids) or ('owner' in row and row['owner'] != owner):
                    raise ValueError('Snapshot berisi data pengguna lain.')
                if table == 'creators' and row['id'] != owner or table == 'creator_permissions' and row['user'] != owner:
                    raise ValueError('Izin snapshot tidak sesuai.')
        accounts = tables['userbots']
        if bool(accounts) != bool(spec['account']) or len(accounts) > 1:
            raise ValueError('Daftar Userbot berubah.')
        return data

    async def install(self, command, payload):
        job, owner = command['id'], command['owner']
        digest = checksum(payload)
        if digest != command['digest']:
            raise ValueError('Checksum migrasi tidak cocok.')
        previous = self.db.rows('SELECT * FROM migration_receipts WHERE job=?', (job,))
        if previous:
            if previous[0]['digest'] != digest:
                raise ValueError('Snapshot migrasi berubah.')
            return json.loads(previous[0]['receipt'])
        data = self.validate(payload, command)
        await self.freeze(job, owner, 'target')
        tables, db = data['tables'], self.db
        spec = command['spec']
        if {r['id'] for r in db.bots(owner)} - {r['id'] for r in tables['bots']}:
            raise ValueError('Tujuan memiliki layanan lain untuk pengguna ini.')
        # A destination can contain a dormant copy from a previous migration.
        for row in tables['bots']:
            existing = db.rows('SELECT owner,kind FROM bots WHERE id=?', (row['id'],))
            if existing and (existing[0]['owner'] != owner or existing[0]['kind'] != row['kind']):
                raise ValueError('Identitas bot tujuan berbeda.')
        for row in tables['payment_events']:
            existing = db.rows('SELECT owner FROM payment_events WHERE transaction_id=?', (row['transaction_id'],))
            if existing and existing[0]['owner'] != owner:
                raise ValueError('Transaksi tujuan memiliki pemilik berbeda.')
        for table, records in tables.items():
            for row in records:
                for key, value in list(row.items()):
                    if isinstance(value, dict):
                        row[key] = base64.b64decode(value['blob'], validate=True)
                for column in CRYPT.get(table, ()):
                    if row[column] is not None:
                        row[column] = db.cipher.encrypt(row[column])
        counts = {t: len(r) for t, r in tables.items()}
        receipt = {'digest': digest, 'counts': counts, 'integrity': 'ok'}
        with db.conn:
            self.purge(owner, registry=False)
            for table in ('creators', 'creator_permissions', 'telegram_profiles', 'bots', 'userbots',
                          'payment_accounts', 'payment_events'):
                for row in tables[table]:
                    if table == 'telegram_profiles':
                        db.conn.execute('INSERT OR IGNORE INTO telegram_profiles VALUES (?,?,?)', tuple(row[c] for c in data['columns'][table]))
                    elif table in ('bots', 'userbots'):
                        row['active'] = 0
                        self.upsert(table, row, 'id' if table == 'bots' else 'owner')
                    else:
                        self.upsert(table, row, {'creators':'id','creator_permissions':'user,kind',
                                    'payment_accounts':'owner','payment_events':'transaction_id'}[table])
            # Package IDs are global SQLite integers. Remap collisions, including order references.
            remap = {}
            next_id = max([r['id'] for r in tables['payment_packages']] +
                          [r['id'] for r in db.rows('SELECT id FROM payment_packages')] + [0]) + 1
            for row in tables['payment_packages']:
                if db.rows('SELECT id FROM payment_packages WHERE id=?', (row['id'],)):
                    remap[row['id']] = next_id
                    row['id'] = next_id
                    next_id += 1
            for row in tables['payment_orders']:
                row['package'] = remap.get(row['package'], row['package'])
            for table in bot_tables(db):
                for row in tables[table]:
                    if table == 'jobs':
                        row.pop('id', None)
                    self.insert(table, row)
                actual = db.rows('SELECT count(*) n FROM '+quoted(table)+' WHERE bot IN (SELECT id FROM bots WHERE owner=?)', (owner,))[0]['n']
                if actual != counts[table]:
                    raise ValueError('Jumlah data tujuan tidak sesuai.')
            if db.rows('PRAGMA foreign_key_check') or db.conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Integritas tujuan tidak sesuai.')
            worker = bool(db.rows("SELECT name FROM sqlite_master WHERE name='worker_versions'"))
            for record in spec['bots']:
                if worker:
                    db.conn.execute('INSERT INTO worker_versions VALUES (?,?) ON CONFLICT(bot) DO UPDATE SET revision=excluded.revision', (record['id'], record['revision']))
            if worker and spec['account']:
                account = spec['account']
                db.conn.execute('INSERT INTO worker_accounts VALUES (?,?,?) ON CONFLICT(owner) DO UPDATE SET revision=excluded.revision,prefix_version=excluded.prefix_version',
                                (owner, account['revision'], account['prefix_version']))
            if tables['userbots']:
                from zei_userbot.state import State
                path = self.manager.userbots.directory/str(owner)/'settings.sqlite'
                temp = path.with_name('migration-'+job+'.sqlite')
                state = State(temp)
                try:
                    with state.conn:
                        for table in ('settings', 'notes'):
                            state.conn.execute('DELETE FROM '+table)
                            state.conn.executemany('INSERT INTO '+table+' VALUES (?,?)', data['account'].get(table, []))
                    # Validate a migrated prefix before a process can start.
                    from zei_userbot.state import validate_prefix
                    validate_prefix(state.prefix)
                finally:
                    state.close()
                temp.replace(path)
            db.conn.execute('INSERT INTO migration_receipts VALUES (?,?,?)', (job, digest, json.dumps(receipt)))
        return receipt

    def insert(self, table, row):
        self.db.conn.execute('INSERT INTO '+quoted(table)+' ('+','.join(quoted(k) for k in row)+') VALUES ('+','.join('?' for _ in row)+')', tuple(row.values()))

    def upsert(self, table, row, keys):
        columns = keys.split(',')
        updates = ','.join(quoted(k)+'=excluded.'+quoted(k) for k in row if k not in columns)
        self.db.conn.execute('INSERT INTO '+quoted(table)+' ('+','.join(quoted(k) for k in row)+') VALUES ('+','.join('?' for _ in row)+') ON CONFLICT('+keys+') DO UPDATE SET '+updates, tuple(row.values()))

    def purge(self, owner, registry):
        for table in bot_tables(self.db):
            self.db.conn.execute('DELETE FROM '+quoted(table)+' WHERE bot IN (SELECT id FROM bots WHERE owner=?)', (owner,))
        for table in ('payment_accounts', 'payment_events'):
            self.db.conn.execute('DELETE FROM '+table+' WHERE owner=?', (owner,))
        if registry:
            self.db.conn.execute('DELETE FROM worker_versions WHERE bot IN (SELECT id FROM bots WHERE owner=?)', (owner,))
            self.db.conn.execute('DELETE FROM worker_accounts WHERE owner=?', (owner,))
            self.db.conn.execute('DELETE FROM bots WHERE owner=?', (owner,))
            self.db.conn.execute('DELETE FROM userbots WHERE owner=?', (owner,))

    def activate(self, command):
        owner = command['owner']
        if not self.db.rows('SELECT job FROM migration_receipts WHERE job=?', (command['id'],)):
            raise ValueError('Tujuan belum memiliki receipt migrasi.')
        with self.db.conn:
            self.db.conn.execute('DELETE FROM migration_holds WHERE owner=? AND job=?', (owner, command['id']))
            if self.db.rows("SELECT name FROM sqlite_master WHERE name='migration_downloads'"):
                self.db.conn.execute('DELETE FROM migration_downloads WHERE job=?', (command['id'],))
            for bot in command['spec']['bots']:
                self.db.conn.execute('UPDATE bots SET active=?,redeploy_required=? WHERE id=?', (bot['active'], bot['redeploy_required'], bot['id']))
            account = command['spec']['account']
            if account:
                self.db.conn.execute('UPDATE userbots SET active=?,redeploy_required=? WHERE owner=?', (account['active'], account['redeploy_required'], owner))

    def finish(self, command, worker):
        with self.db.conn:
            self.purge(command['owner'], registry=worker)
            # Retired owners remain held on the old worker, including scheduled cleanup.
            self.db.conn.execute("UPDATE migration_holds SET role='retired' WHERE owner=? AND job=?", (command['owner'], command['id']))
            self.db.conn.execute('DELETE FROM migration_cache WHERE job=?', (command['id'],))


class Migrations:
    def __init__(self, db, manager, directory):
        self.db, self.manager, self.servers = db, manager, manager.servers
        self.node = MigrationNode(db, manager, directory)
        self.task = None
        self.lock = asyncio.Lock()
        db.conn.executescript('''
            CREATE TABLE IF NOT EXISTS migrations (
                id TEXT PRIMARY KEY, owner INTEGER NOT NULL, source INTEGER NOT NULL,
                target INTEGER NOT NULL, phase TEXT NOT NULL, spec TEXT NOT NULL,
                size INTEGER NOT NULL DEFAULT 0, digest TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS migration_owner_busy ON migrations(owner) WHERE phase != 'done';
            CREATE TABLE IF NOT EXISTS migration_chunks (
                job TEXT NOT NULL REFERENCES migrations(id), part INTEGER NOT NULL,
                data BLOB NOT NULL, PRIMARY KEY(job,part));
        ''')

    def get(self, ident):
        rows = self.db.rows('SELECT * FROM migrations WHERE id=?', (ident,))
        if not rows:
            raise ValueError('Migrasi tidak ditemukan.')
        row = rows[0]
        row['spec'] = json.loads(row['spec'])
        return row

    def latest(self, owner):
        rows = self.db.rows('SELECT id FROM migrations WHERE owner=? ORDER BY created DESC LIMIT 1', (owner,))
        return self.get(rows[0]['id']) if rows else None

    def begin(self, actor, owner, target):
        self.db.master(actor)
        if type(owner) is not int or owner <= 0 or target is not None and (type(target) is not int or target <= 0):
            raise ValueError('Pengguna atau server tidak valid.')
        source = self.servers.assigned(owner) or 0
        target = target or 0
        if source == target:
            raise ValueError('Pengguna sudah berada di server ini.')
        for server in (source, target):
            if server:
                row = self.servers.get(server)
                if not self.servers.online(row) or row['migration_version'] != VERSION:
                    raise ValueError('Server harus terhubung dan memakai Worker dengan fitur migrasi terbaru.')
        previous = self.latest(owner)
        if previous and previous['phase'] != 'done':
            raise ValueError('Migrasi pengguna masih berjalan. Buka Status Migrasi.')
        bots = [{k:r[k] for k in ('id','owner','kind','active','redeploy_required')} |
                {'revision':self.servers.revision(r)} for r in self.db.bots(owner)]
        accounts = self.db.rows('SELECT * FROM userbots WHERE owner=?', (owner,))
        account = None
        if accounts:
            row = accounts[0]
            controls = self.db.rows('SELECT version FROM server_prefixes WHERE owner=?', (owner,))
            account = {k:row[k] for k in ('active','redeploy_required')} | {'revision':self.servers.revision(row), 'prefix_version':controls[0]['version'] if controls else 0}
        if not bots and not account:
            raise ValueError('Pengguna belum memiliki layanan untuk dipindahkan.')
        ident = secrets.token_hex(12)
        with self.db.conn:
            self.db.conn.execute('INSERT INTO migrations(id,owner,source,target,phase,spec,created) VALUES (?,?,?,?,?,?,?)',
                (ident,owner,source,target,'export',json.dumps({'bots':bots,'account':account}),time.time()))
        return ident

    def commands(self, server):
        result = []
        for r in self.db.rows("SELECT id FROM migrations WHERE phase != 'done'"):
            job = self.get(r['id'])
            if job['source'] == server and job['phase'] in ('export','cleanup') or job['target'] == server and job['phase'] in ('import','verify'):
                result.append({k:job[k] for k in ('id','owner','phase','spec','size','digest')})
                result[-1]['next_part'] = self.db.rows('SELECT count(*) n FROM migration_chunks WHERE job=?', (job['id'],))[0]['n']
        return result

    def authorize(self, token, ident, role):
        server = self.servers.authenticate(token)['id']
        job = self.get(ident)
        if job[role] != server:
            raise PermissionError('Migrasi bukan milik server ini.')
        return job

    def put(self, job, part, value):
        if job['phase'] != 'export' or type(part) is not int or not 0 <= part < (MAX_BYTES+CHUNK-1)//CHUNK:
            raise ValueError('Tahap upload tidak sesuai.')
        chunk = base64.b64decode(value, validate=True)
        if not 0 < len(chunk) <= CHUNK:
            raise ValueError('Potongan migrasi tidak valid.')
        with self.db.conn:
            previous = self.db.rows('SELECT data FROM migration_chunks WHERE job=? AND part=?', (job['id'],part))
            if previous and self.db.cipher.decrypt(previous[0]['data']) != chunk:
                raise ValueError('Snapshot berubah pada percobaan ulang.')
            self.db.conn.execute('INSERT OR IGNORE INTO migration_chunks VALUES (?,?,?)', (job['id'],part,self.db.cipher.encrypt(chunk)))

    def payload(self, job):
        return b''.join(self.db.cipher.decrypt(r['data']) for r in self.db.rows('SELECT data FROM migration_chunks WHERE job=? ORDER BY part', (job['id'],)))

    def exported(self, job, size, digest):
        if job['phase'] != 'export':
            if job['size'] == size and job['digest'] == digest:
                return
            raise ValueError('Tahap snapshot berubah.')
        if type(size) is not int or not 0 < size <= MAX_BYTES:
            raise ValueError('Ukuran snapshot tidak valid.')
        data = self.payload(job)
        if len(data) != size or checksum(data) != digest:
            raise ValueError('Snapshot belum lengkap.')
        self.node.validate(data, job)
        with self.db.conn:
            self.db.conn.execute("UPDATE migrations SET size=?,digest=?,phase='import',error='' WHERE id=?", (size,digest,job['id']))

    def installed(self, job, receipt):
        if job['phase'] not in ('import','verify') or receipt.get('digest') != job['digest'] or receipt.get('integrity') != 'ok':
            raise ValueError('Receipt tujuan tidak valid.')
        payload = json.loads(self.payload(job))
        counts = {t:len(r) for t,r in payload['tables'].items()}
        if receipt.get('counts') != counts:
            raise ValueError('Jumlah data receipt berbeda.')
        with self.db.conn:
            if job['spec']['account']:
                from zei_userbot.state import validate_prefix
                settings = dict(payload['account'].get('settings', []))
                prefix = validate_prefix(json.loads(settings.get('prefix','"."')))
                self.db.conn.execute('INSERT INTO server_prefixes VALUES (?,?,1) ON CONFLICT(owner) DO UPDATE SET prefix=excluded.prefix,version=version+1', (job['owner'],prefix))
            self.db.conn.execute('DELETE FROM server_owners WHERE owner=?', (job['owner'],))
            if job['target']:
                self.db.conn.execute('INSERT INTO server_owners VALUES (?,?)', (job['owner'],job['target']))
            self.db.conn.execute("UPDATE migrations SET phase='verify',error='' WHERE id=?", (job['id'],))

    def cleaned(self, job):
        if job['phase'] not in ('cleanup','done'):
            raise ValueError('Tujuan belum dikonfirmasi aktif.')
        with self.db.conn:
            self.db.conn.execute("UPDATE migrations SET phase='done',error='' WHERE id=?", (job['id'],))
            self.db.conn.execute('DELETE FROM migration_chunks WHERE job=?', (job['id'],))

    async def tick(self):
        async with self.lock:
            for row in self.db.rows("SELECT id FROM migrations WHERE phase != 'done'"):
                job = self.get(row['id'])
                try:
                    if job['phase'] == 'export' and job['source'] == 0:
                        data = await self.node.export(job)
                        for part,start in enumerate(range(0,len(data),CHUNK)):
                            self.put(job,part,base64.b64encode(data[start:start+CHUNK]))
                        self.exported(job,len(data),checksum(data))
                    elif job['phase'] == 'import' and job['target'] == 0:
                        self.installed(job,await self.node.install(job,self.payload(job)))
                    elif job['phase'] == 'verify':
                        if job['target'] == 0:
                            self.node.activate(job)
                            await self.manager.restore()
                        expected = [b for b in job['spec']['bots'] if b['active'] and not b['redeploy_required'] and self.db.allowed(job['owner'],b['kind'])]
                        account = job['spec']['account']
                        ready = all(self.manager.is_running(b['id']) for b in expected)
                        if account and account['active'] and not account['redeploy_required'] and self.db.allowed(job['owner'],'userbot'):
                            ready = ready and self.manager.userbots.is_running(job['owner'])
                        # Even a stopped owner's destination must acknowledge activation.
                        if job['target']:
                            server = self.servers.get(job['target'])
                            ready = ready and self.servers.online(server) and json.loads(server['migration_acks']).get(job['id']) == 'active'
                        if ready:
                            with self.db.conn:
                                self.db.conn.execute("UPDATE migrations SET phase='cleanup',error='' WHERE id=?", (job['id'],))
                    elif job['phase'] == 'cleanup' and job['source'] == 0:
                        self.node.finish(job,worker=False)
                        self.cleaned(job)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # Never expose request payloads or credentials in Telegram or logs.
                    with self.db.conn:
                        self.db.conn.execute('UPDATE migrations SET error=? WHERE id=?', (type(exc).__name__,job['id']))

    async def run(self):
        while True:
            await self.tick()
            await asyncio.sleep(3)

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)

"""Durable server enrollment and owner placement for child bot runtimes."""
import hashlib
import json
import secrets
import time

LEASE_SECONDS = 120


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Servers:
    def __init__(self, db):
        self.db = db
        db.conn.executescript('''
            CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                code_hash TEXT UNIQUE, code_until REAL NOT NULL DEFAULT 0,
                token_hash TEXT UNIQUE, enabled INTEGER NOT NULL DEFAULT 1,
                last_seen REAL NOT NULL DEFAULT 0, report TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS server_owners (
                owner INTEGER PRIMARY KEY, server INTEGER NOT NULL REFERENCES servers(id));
            CREATE TABLE IF NOT EXISTS server_prefixes (
                owner INTEGER PRIMARY KEY, prefix TEXT NOT NULL, version INTEGER NOT NULL);
        ''')
        self.helper = ''

    def all(self):
        return self.db.rows('SELECT id,name,enabled,last_seen FROM servers ORDER BY id')

    def get(self, server):
        rows = self.db.rows('SELECT * FROM servers WHERE id=?', (server,))
        if not rows:
            raise ValueError('Server tidak ditemukan.')
        return rows[0]

    def add(self, actor, name):
        self.db.master(actor)
        name = name.strip()
        if not 1 <= len(name) <= 60:
            raise ValueError('Nama server harus 1–60 karakter.')
        code = secrets.token_urlsafe(24)
        with self.db.conn:
            cursor = self.db.conn.execute(
                'INSERT INTO servers(name,code_hash,code_until) VALUES (?,?,?)',
                (name, digest(code), time.time()+600))
        return cursor.lastrowid, code

    def renew(self, actor, server):
        self.db.master(actor)
        row = self.get(server)
        if row['token_hash']:
            raise ValueError('Server sudah dipasangkan. Gunakan identitas server baru untuk pemasangan baru.')
        code = secrets.token_urlsafe(24)
        with self.db.conn:
            self.db.conn.execute('UPDATE servers SET code_hash=?,code_until=? WHERE id=?',
                                 (digest(code), time.time()+600, server))
        return code

    def enroll(self, code, token):
        if not isinstance(code, str) or not isinstance(token, str) or len(token) != 64:
            raise PermissionError('Kode pemasangan tidak valid.')
        # The worker persists its chosen token before enrollment, so a lost reply is retryable.
        with self.db.conn:
            rows = self.db.rows('SELECT * FROM servers WHERE code_hash=?', (digest(code),))
            if not rows or not rows[0]['enabled'] or rows[0]['code_until'] < time.time():
                raise PermissionError('Kode pemasangan berakhir atau sudah digunakan.')
            row = rows[0]
            if row['token_hash'] and row['token_hash'] != digest(token):
                raise PermissionError('Kode pemasangan sudah digunakan.')
            self.db.conn.execute('UPDATE servers SET token_hash=? WHERE id=?', (digest(token), row['id']))
        return row['id']

    def authenticate(self, token):
        if not isinstance(token, str) or len(token) != 64:
            raise PermissionError('Identitas server tidak valid.')
        rows = self.db.rows('SELECT * FROM servers WHERE token_hash=?', (digest(token),))
        if not rows or not rows[0]['enabled']:
            raise PermissionError('Server tidak diizinkan.')
        return rows[0]

    def assigned(self, owner):
        rows = self.db.rows('SELECT server FROM server_owners WHERE owner=?', (owner,))
        return rows[0]['server'] if rows else None

    def place(self, actor, owner, server):
        self.db.master(actor)
        if type(owner) is not int or owner <= 0:
            raise ValueError('Pengguna tidak valid.')
        if self.assigned(owner) == server:
            return
        if self.db.bots(owner) or self.db.rows('SELECT owner FROM userbots WHERE owner=?',(owner,)):
            raise ValueError('Pengguna sudah memiliki bot atau Userbot. Pemindahan server memerlukan migrasi data terlebih dahulu.')
        if server is not None:
            row = self.get(server)
            if not row['enabled'] or not row['token_hash'] or not self.online(row):
                raise ValueError('Pilih server yang sudah terhubung.')
        with self.db.conn:
            if server is None:
                self.db.conn.execute('DELETE FROM server_owners WHERE owner=?', (owner,))
            else:
                self.db.conn.execute('INSERT INTO server_owners VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET server=excluded.server', (owner, server))

    def online(self, row):
        return bool(row['enabled'] and row['last_seen'] > time.time()-20)

    def revision(self, record):
        return hashlib.sha256(record['credentials']).hexdigest()

    def heartbeat(self, token, report):
        row = self.authenticate(token)
        desired = []
        for record in self.db.bots():
            if self.assigned(record['owner']) != row['id']:
                continue
            desired.append(dict(id=record['id'], owner=record['owner'], username=record['username'],
                name=record['name'], kind=record['kind'], revision=self.revision(record),
                active=bool(record['active'] and self.db.allowed(record['owner'], record['kind'])),
                allowed=self.db.allowed(record['owner'], record['kind']),
                redeploy_required=bool(record['redeploy_required']), credentials=self.db.credentials(record['id'])))
        valid = {}
        if not isinstance(report, dict) or len(report) > 10000:
            raise ValueError('Laporan server tidak valid.')
        for item in desired:
            actual = report.get(str(item['id']), {})
            if isinstance(actual, dict) and actual.get('revision') == item['revision']:
                valid[str(item['id'])] = {'revision': item['revision'], 'running': actual.get('running') is True}
        accounts = []
        for record in self.db.rows('SELECT * FROM userbots'):
            owner = record['owner']
            if self.assigned(owner) != row['id']:
                continue
            control = self.db.rows('SELECT prefix,version FROM server_prefixes WHERE owner=?',(owner,))
            item = dict(owner=owner,name=record['name'],revision=self.revision(record),
                active=bool(record['active'] and not record['redeploy_required'] and self.db.allowed(owner,'userbot')),
                allowed=self.db.allowed(owner,'userbot'),redeploy_required=bool(record['redeploy_required']),
                credentials=json.loads(self.db.cipher.decrypt(record['credentials'])),
                control=control[0] if control else None)
            accounts.append(item)
            actual = report.get('u:'+str(owner),{})
            if isinstance(actual,dict) and actual.get('revision') == item['revision']:
                from zei_userbot.state import validate_prefix
                try:
                    prefix = validate_prefix(actual.get('prefix'))
                except ValueError:
                    continue
                version = actual.get('prefix_version',0)
                if type(version) is not int or version < 0:
                    continue
                valid['u:'+str(owner)] = dict(revision=item['revision'],running=actual.get('running') is True,
                                             prefix=prefix,prefix_version=version)
        with self.db.conn:
            self.db.conn.execute("UPDATE servers SET last_seen=?,report=?,code_hash=NULL WHERE id=?",
                                 (time.time(), json.dumps(valid), row['id']))
        return {'master_owner': self.db.master_owner, 'lease_seconds': LEASE_SECONDS, 'bots': desired,
                'userbots': accounts, 'helper': self.helper}

    def account_report(self, owner):
        server = self.assigned(owner)
        if server is None:
            return {}
        row = self.get(server)
        if not self.online(row):
            return {}
        accounts = self.db.rows('SELECT * FROM userbots WHERE owner=?',(owner,))
        report = json.loads(row['report']).get('u:'+str(owner),{})
        if not accounts or report.get('revision') != self.revision(accounts[0]):
            return {}
        return report

    def account_running(self, owner):
        rows = self.db.rows('SELECT active,redeploy_required FROM userbots WHERE owner=?',(owner,))
        return bool(rows and rows[0]['active'] and not rows[0]['redeploy_required']
                    and self.db.allowed(owner,'userbot') and self.account_report(owner).get('running'))

    def set_prefix(self, owner, prefix):
        from zei_userbot.state import validate_prefix
        validate_prefix(prefix)
        if not self.account_running(owner):
            raise ValueError('Userbot belum aktif di server klien.')
        with self.db.conn:
            self.db.conn.execute('INSERT INTO server_prefixes VALUES (?,?,1) ON CONFLICT(owner) DO UPDATE SET prefix=excluded.prefix,version=version+1',(owner,prefix))
        return self.db.rows('SELECT version FROM server_prefixes WHERE owner=?',(owner,))[0]['version']

    def running(self, bot):
        record = self.db.bot(bot)
        server = self.assigned(record['owner'])
        if server is None or not record['active'] or not self.db.allowed(record['owner'],record['kind']):
            return False
        row = self.get(server)
        report = json.loads(row['report']).get(str(bot), {})
        return bool(self.online(row) and report.get('running') and report.get('revision') == self.revision(record))

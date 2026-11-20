"""Client-server process. Enroll once, then reconcile desired child bots over HTTPS."""
import asyncio
import json
import logging
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit

import aiohttp
from cryptography.fernet import Fernet

from .app import instance_lock
from .runtime import Manager
from .servers import LEASE_SECONDS
from .store import Store
from .userbots import Userbots

log = logging.getLogger(__name__)


def validate_origin(value):
    url = urlsplit(value)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.path not in ('', '/') or url.query or url.fragment):
        raise ValueError('WORKER_GATE_URL harus origin HTTPS bot induk tanpa path.')
    return value.rstrip('/')


def save_identity(path, data):
    temp = path.with_suffix('.new')
    temp.write_text(json.dumps(data), encoding='utf-8')
    os.chmod(temp, 0o600)
    temp.replace(path)


class Worker:
    def __init__(self, db, manager=None, directory=None):
        self.db = db
        self.manager = manager or Manager(db, 0)
        self.deadline = 0
        self.lock = asyncio.Lock()
        self.manager.call_allowed = lambda: time.monotonic() < self.deadline
        db.conn.execute('CREATE TABLE IF NOT EXISTS worker_versions (bot INTEGER PRIMARY KEY, revision TEXT NOT NULL)')
        db.conn.execute('CREATE TABLE IF NOT EXISTS worker_accounts (owner INTEGER PRIMARY KEY, revision TEXT NOT NULL, prefix_version INTEGER NOT NULL DEFAULT 0)')
        db.conn.commit()
        if self.manager.userbots is None:
            self.manager.userbots = Userbots(db, directory or Path(db.conn.execute('PRAGMA database_list').fetchone()[2]).parent/'userbots')
        original = self.manager.runner_factory

        def factory(record, credentials):
            runner = original(record, credentials)
            if hasattr(runner,'api'):
                runner.api.lease_check = lambda: time.monotonic() < self.deadline
            if hasattr(runner, 'is_enabled'):
                enabled = runner.is_enabled
                runner.is_enabled = lambda: time.monotonic() < self.deadline and enabled()
            return runner
        self.manager.runner_factory = factory
        # Never restore from the worker's previous lease after a process restart.
        with db.conn:
            db.conn.execute('UPDATE bots SET active=0')
            db.conn.execute('UPDATE userbots SET active=0')

    def report(self):
        report = {str(row['bot']): {'revision': row['revision'], 'running': row['bot'] in self.manager.running}
                  for row in self.db.rows('SELECT * FROM worker_versions')}
        service = self.manager.userbots
        for row in self.db.rows('SELECT * FROM worker_accounts'):
            runner = service.running.get(row['owner'])
            running = runner is not None and (not hasattr(runner,'process') or runner.process.returncode is None)
            report['u:'+str(row['owner'])] = dict(revision=row['revision'],running=running,
                prefix=service.prefix(row['owner']),prefix_version=row['prefix_version'])
        return report

    async def apply_accounts(self, snapshot):
        service = self.manager.userbots
        service.helper = snapshot.get('helper','')
        wanted = {item['owner']:item for item in snapshot.get('userbots',[])}
        for record in self.db.rows('SELECT * FROM userbots'):
            if record['owner'] not in wanted:
                with self.db.conn:
                    self.db.conn.execute('UPDATE userbots SET active=0 WHERE owner=?',(record['owner'],))
                runner = service.running.pop(record['owner'],None)
                if runner:
                    await runner.stop()
        for owner,item in wanted.items():
            if type(owner) is not int or owner <= 0:
                raise ValueError('Identitas Userbot tidak valid.')
            allowed = bool(item['allowed'])
            active = bool(allowed and item['active'] and not item['redeploy_required'])
            with self.db.conn:
                self.db.conn.execute('INSERT INTO creators VALUES (?,1) ON CONFLICT(id) DO NOTHING',(owner,))
                self.db.conn.execute("INSERT INTO creator_permissions VALUES (?,'userbot',?) ON CONFLICT(user,kind) DO UPDATE SET allowed=excluded.allowed",(owner,allowed))
            versions = self.db.rows('SELECT * FROM worker_accounts WHERE owner=?',(owner,))
            changed = not versions or versions[0]['revision'] != item['revision']
            if changed and active:
                try:
                    await service.deploy(owner,item['credentials'],{'id':owner,'name':item['name']})
                except Exception as exc:
                    log.warning('Userbot %s belum aktif: %s',owner,type(exc).__name__)
                    continue
                with self.db.conn:
                    self.db.conn.execute('INSERT INTO worker_accounts(owner,revision) VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET revision=excluded.revision',(owner,item['revision']))
            elif service.record(owner):
                with self.db.conn:
                    self.db.conn.execute('UPDATE userbots SET active=?,redeploy_required=? WHERE owner=?',(active,bool(item['redeploy_required']),owner))
            if not active:
                runner = service.running.pop(owner,None)
                if runner:
                    await runner.stop()
            control = item.get('control')
            version = versions[0]['prefix_version'] if versions else 0
            if control and active and control['version'] > version and service.record(owner):
                await service.set_prefix(owner,control['prefix'])
                with self.db.conn:
                    self.db.conn.execute('UPDATE worker_accounts SET prefix_version=? WHERE owner=?',(control['version'],owner))
        await service.reconcile()

    async def apply(self, snapshot, started):
        if (snapshot.get('master_owner') != self.db.master_owner or snapshot.get('lease_seconds') != LEASE_SECONDS
                or not isinstance(snapshot.get('bots'), list)):
            raise ValueError('Snapshot Gate tidak valid.')
        deadline = started + LEASE_SECONDS
        async with self.lock, self.manager.lock:
            self.deadline = deadline
            async with asyncio.timeout_at(deadline):
                wanted = {item['id']: item for item in snapshot['bots']}
                for record in self.db.bots():
                    if record['id'] not in wanted:
                        self.db.set_active(self.db.master_owner, record['id'], False)
                        runner = self.manager.running.pop(record['id'], None)
                        if runner:
                            await runner.stop()
                for item in wanted.values():
                    if (type(item['id']) is not int or type(item['owner']) is not int
                            or item['id'] <= 0 or item['owner'] <= 0 or item['kind'] not in ('forcesubs', 'payment')):
                        raise ValueError('Bot pada snapshot tidak valid.')
                    rows = self.db.rows('SELECT * FROM bots WHERE id=?', (item['id'],))
                    record = rows[0] if rows else None
                    if record and (record['owner'] != item['owner'] or record['kind'] != item['kind']):
                        raise ValueError('Identitas bot berubah.')
                    with self.db.conn:
                        self.db.conn.execute('INSERT INTO creators VALUES (?,1) ON CONFLICT(id) DO NOTHING', (item['owner'],))
                        self.db.conn.execute('INSERT INTO creator_permissions VALUES (?,?,?) ON CONFLICT(user,kind) DO UPDATE SET allowed=excluded.allowed',
                                             (item['owner'],item['kind'],bool(item['allowed'])))
                    versions = self.db.rows('SELECT revision FROM worker_versions WHERE bot=?', (item['id'],))
                    changed = not versions or versions[0]['revision'] != item['revision']
                    if changed:
                        runner = self.manager.running.pop(item['id'], None)
                        if runner:
                            await runner.stop()
                        if item['allowed']:
                            creds = item['credentials']
                            with self.db.conn:
                                self.db.deploy(item['owner'],item['id'],item['username'],creds['api_id'],
                                               creds['api_hash'],creds['token'],creds['session'],name=item['name'],kind=item['kind'])
                                self.db.conn.execute('INSERT INTO worker_versions VALUES (?,?) ON CONFLICT(bot) DO UPDATE SET revision=excluded.revision',
                                                     (item['id'],item['revision']))
                    if not self.db.rows('SELECT id FROM bots WHERE id=?', (item['id'],)):
                        continue
                    active = bool(item['active'] and item['allowed'])
                    with self.db.conn:
                        self.db.conn.execute('UPDATE bots SET active=?,redeploy_required=? WHERE id=?',
                                             (active,bool(item['redeploy_required']),item['id']))
                        if not active:
                            self.db.conn.execute("UPDATE payment_orders SET state='cancelled' WHERE bot=? AND state='pending' AND payment='pending'", (item['id'],))
                    runner = self.manager.running.get(item['id'])
                    if not active and runner:
                        await self.manager.running.pop(item['id']).stop()
                    elif active and runner is None:
                        try:
                            await self.manager._start(item['id'])
                        except Exception as exc:
                            log.warning('Bot %s belum aktif: %s',item['id'],type(exc).__name__)
                await self.apply_accounts(snapshot)

    async def expire(self):
        async with self.lock, self.manager.lock:
            if time.monotonic() < self.deadline:
                return
            with self.db.conn:
                self.db.conn.execute('UPDATE bots SET active=0')
                self.db.conn.execute('UPDATE userbots SET active=0')
            for bot in list(self.manager.running):
                await self.manager.running.pop(bot).stop()
            await self.manager.userbots.close()

    async def watch(self):
        while True:
            await asyncio.sleep(1)
            await self.expire()


async def main():
    from dotenv import load_dotenv
    load_dotenv('config.env')
    origin = validate_origin(os.environ.get('WORKER_GATE_URL',''))
    directory = Path(os.environ.get('DATA_DIR') or './data').resolve()
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(name)s: %(message)s')
    with instance_lock(directory):
        path = directory/'worker-identity.json'
        if path.exists():
            identity = json.loads(path.read_text(encoding='utf-8'))
            if identity['gate'] != origin:
                raise ValueError('DATA_DIR sudah terikat ke Gate lain.')
            new_code = os.environ.get('WORKER_ENROLL_CODE','').strip()
            if identity.get('code') and new_code and new_code != identity['code']:
                identity['code'] = new_code
                save_identity(path,identity)
        else:
            code = os.environ.get('WORKER_ENROLL_CODE','').strip()
            if not code:
                raise ValueError('Masukkan kode pemasangan dari Kelola Server pada bot induk.')
            identity = {'gate': origin,'token': secrets.token_hex(32),'code': code,'key': Fernet.generate_key().decode()}
            save_identity(path,identity)
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout,raise_for_status=True) as http:
            db = worker = watch = None
            try:
                while True:
                    started = time.monotonic()
                    try:
                        if identity.get('code'):
                            try:
                                async with http.post(origin+'/servers/sync',headers={'Authorization': 'Bearer '+identity['token']},json={'report': {}}) as response:
                                    await response.json()
                            except aiohttp.ClientResponseError as exc:
                                if exc.status != 403:
                                    raise
                                async with http.post(origin+'/servers/enroll',json={'code': identity['code'],'token': identity['token']}) as response:
                                    identity['server'] = (await response.json())['server']
                        report = worker.report() if worker else {}
                        async with http.post(origin+'/servers/sync',headers={'Authorization': 'Bearer '+identity['token']},json={'report':report}) as response:
                            snapshot = await response.json()
                        if worker is None:
                            owner = snapshot['master_owner']
                            if type(owner) is not int or owner <= 0:
                                raise ValueError('Owner Gate tidak valid.')
                            db = Store(directory/'subgate.sqlite',identity['key'].encode(),owner)
                            worker = Worker(db)
                            worker.manager.maintenance_task = asyncio.create_task(worker.manager.maintenance())
                            watch = asyncio.create_task(worker.watch())
                        identity.pop('code',None)
                        save_identity(path,identity)
                        await worker.apply(snapshot, started)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        if worker:
                            await worker.expire()
                        log.warning('Sinkronisasi Gate belum berhasil: %s',type(exc).__name__)
                    await asyncio.sleep(5)
            finally:
                if watch:
                    watch.cancel()
                    await asyncio.gather(watch,return_exceptions=True)
                if worker:
                    await worker.manager.close()
                if db:
                    db.close()

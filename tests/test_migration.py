import asyncio
import base64
import json
from pathlib import Path
import tempfile
import time
import unittest

from cryptography.fernet import Fernet
from subgate.store import Store
from subgate.runtime import Manager
from subgate.servers import Servers
from subgate.worker import Worker
from subgate.userbots import Userbots
from subgate.migration import Migrations, checksum, CHUNK
from subgate.payment_store import PaymentStore
from zei_userbot.state import State
from test_service import FakeAPI
from test_runtime import FakeRunner


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.nodes = []
        for name in ('gate','a','b'):
            folder = self.root/name
            db = Store(folder/'subgate.sqlite',Fernet.generate_key(),1)
            manager = Manager(db,500,runner_factory=lambda *args:FakeRunner(FakeAPI()))
            async def factory(*args): return FakeRunner(FakeAPI())
            manager.userbots = Userbots(db,folder/'userbots',factory=factory)
            self.nodes.append((db,manager))
        self.db,self.manager = self.nodes[0]
        self.servers = Servers(self.db)
        self.manager.servers = self.servers
        self.manager.userbots.servers = self.servers
        self.migrations = Migrations(self.db,self.manager,self.root/'gate')
        self.servers.migrations = self.migrations
        self.workers = []
        for index in (1,2):
            server,code = self.servers.add(1,str(index))
            token = str(index)*64
            self.servers.enroll(code,token)
            self.servers.heartbeat(token,{},1,{})
            db,manager = self.nodes[index]
            self.workers.append((server,token,Worker(db,manager)))
        self.db.grant(1,2,'all')
        self.db.deploy(2,99,'TestBot',123,'a'*32,'99:'+'x'*30,'session')
        self.db.setting(99,2,'database',-1001)
        self.link = self.db.link(99,2,[(-1001,7)])
        self.db.add_user(99,8)
        self.db.admin(99,2,8,True)
        self.db.schedule(99,8,700,time.time()+3600)
        self.db.deploy(2,100,'PayBot',123,'a'*32,'100:'+'x'*30,'session',kind='payment')
        pay = PaymentStore(self.db)
        pay.account(2,'seller','recipient',key='key',enabled=True)
        self.package = pay.save_package(100,2,name='VIP',description='Hello',price=1000,target=-1001)
        order = pay.new_order(100,8,self.package)
        pay.attach(order['id'],'tx-id','QR',1000)
        self.order = order['id']
        with self.db.conn:
            self.db.conn.execute('INSERT INTO userbots(owner,name,credentials) VALUES (?,?,?)',
                (2,'Account',self.db.cipher.encrypt(json.dumps({'session':'user-session'}).encode())))
        state = State(self.manager.userbots.directory/'2/settings.sqlite')
        state.set('prefix','!')
        with state.conn: state.conn.execute('INSERT INTO notes VALUES (?,?)',('note','saved'))
        state.close()
        await self.manager.restore()

    async def asyncTearDown(self):
        for db,manager in self.nodes:
            await manager.close()
            db.close()
        self.temp.cleanup()

    async def sync(self,index):
        server,token,worker = self.workers[index]
        snapshot = self.servers.heartbeat(token,worker.report(),1,worker.migration_acks)
        async def request(body):
            action = body['action']
            role = 'source' if action in ('put','exported','cleaned','error_source') else 'target'
            job = self.migrations.authorize(token,body['id'],role)
            if action == 'put': self.migrations.put(job,body['part'],body['data'])
            elif action == 'exported': self.migrations.exported(job,body['size'],body['digest'])
            elif action == 'get':
                data = self.migrations.payload(job)
                return {'data':base64.b64encode(data[body['part']*CHUNK:(body['part']+1)*CHUNK]).decode()}
            elif action == 'installed': self.migrations.installed(job,body['receipt'])
            elif action == 'cleaned': self.migrations.cleaned(job)
            else: raise AssertionError('Worker migration failed: '+action)
            return {'ok':True}
        await worker.transfer(snapshot['migrations'],request)
        await worker.apply(snapshot,time.monotonic())
        self.servers.heartbeat(token,worker.report(),1,worker.migration_acks)

    async def complete(self,ident):
        for _ in range(30):
            await self.migrations.tick()
            await self.sync(0)
            await self.sync(1)
            if self.migrations.get(ident)['phase'] == 'done': return
        self.fail(str(self.migrations.get(ident)))

    async def test_roundtrip_all_services_then_worker_to_worker_preserves_data(self):
        ident = self.migrations.begin(1,2,1)
        await self.complete(ident)
        self.assertEqual(self.servers.assigned(2),1)
        self.assertNotIn(99,self.manager.running)
        target = self.nodes[1][0]
        self.assertEqual(target.sources(99,self.link),[(-1001,7)])
        self.assertEqual(target.credentials(99)['session'],'session')
        self.assertEqual(PaymentStore(target).order(100,self.order)['payment'],'pending')
        self.assertEqual(len(target.rows('SELECT * FROM jobs')),1)
        self.assertNotEqual(self.db.bot(99)['credentials'],target.bot(99)['credentials'])
        # Real edits on a worker must win over the dormant central copy.
        target.setting(99,2,'welcome','Edited on worker')
        ident = self.migrations.begin(1,2,2)
        await self.complete(ident)
        self.assertEqual(self.nodes[2][0].settings(99)['welcome'],'Edited on worker')
        self.assertFalse(self.nodes[1][0].bots(2))
        ident = self.migrations.begin(1,2,None)
        await self.complete(ident)
        self.assertIsNone(self.servers.assigned(2))
        self.assertEqual(self.db.settings(99)['welcome'],'Edited on worker')
        self.assertEqual(PaymentStore(self.db).order(100,self.order)['qr'],'QR')
        self.assertEqual(self.manager.userbots.prefix(2),'!')
        state = State(self.manager.userbots.directory/'2/settings.sqlite')
        self.assertEqual(state.conn.execute('SELECT text FROM notes').fetchone()[0],'saved')
        state.close()
        self.assertTrue(self.root.joinpath('gate/migration-backups',ident,'ready').exists())

    async def test_retry_restart_receipt_and_foreign_server_guards(self):
        ident = self.migrations.begin(1,2,1)
        await self.migrations.tick()
        job = self.migrations.get(ident)
        self.assertEqual(job['phase'],'import')
        payload = self.migrations.payload(job)
        worker = self.workers[0][2]
        receipt = await worker.migration_node.install(job,payload)
        again = await worker.migration_node.install(job,payload)
        self.assertEqual(receipt,again)
        with self.assertRaises(PermissionError): self.migrations.authorize('2'*64,ident,'target')
        with self.assertRaises(ValueError): self.db.revoke(1,2,'all')
        self.migrations = Migrations(self.db,self.manager,self.root/'gate')
        self.servers.migrations = self.migrations
        self.migrations.installed(self.migrations.get(ident),receipt)
        self.migrations.installed(self.migrations.get(ident),receipt)
        await self.complete(ident)
        self.assertEqual(self.migrations.get(ident)['phase'],'done')

    async def test_bad_checksum_old_worker_and_owner_only_are_rejected(self):
        with self.assertRaises(PermissionError): self.migrations.begin(3,2,1)
        self.servers.heartbeat('1'*64,{})
        with self.assertRaises(ValueError): self.migrations.begin(1,2,1)
        self.assertFalse(self.db.frozen(2))
        self.servers.heartbeat('1'*64,{},1,{})
        ident = self.migrations.begin(1,2,1)
        await self.migrations.tick()
        job = self.migrations.get(ident)
        with self.assertRaises(ValueError): await self.workers[0][2].migration_node.install(job,b'corrupt')
        self.assertEqual(self.servers.assigned(2),None)
        self.assertTrue(self.db.sources(99,self.link))

    async def test_package_collision_remaps_only_imported_order_reference(self):
        other = self.nodes[1][0]
        other.grant(1,3,'payment')
        other.deploy(3,200,'OtherBot',123,'a'*32,'200:'+'x'*30,'session',kind='payment')
        payment = PaymentStore(other)
        collision = payment.save_package(200,3,name='Other',description='Other',price=1000,target=-1002)
        self.assertEqual(collision,self.package)
        ident = self.migrations.begin(1,2,1)
        await self.complete(ident)
        self.assertEqual(payment.package(200,collision)['name'],'Other')
        order = payment.order(100,self.order)
        self.assertNotEqual(order['package'],collision)
        self.assertEqual(payment.package(100,order['package'])['name'],'VIP')

    async def test_chunked_transfer_survives_worker_restart_mid_download(self):
        state = State(self.manager.userbots.directory/'2/settings.sqlite')
        with state.conn: state.conn.execute('INSERT INTO notes VALUES (?,?)',('large','x'*65000))
        state.close()
        ident = self.migrations.begin(1,2,1)
        await self.migrations.tick()
        await self.sync(0)
        self.assertEqual(self.migrations.get(ident)['phase'],'import')
        self.assertEqual(self.nodes[1][0].rows('SELECT count(*) n FROM migration_downloads')[0]['n'],8)
        server,token,_ = self.workers[0]
        db,manager = self.nodes[1]
        await manager.close()
        self.workers[0] = (server,token,Worker(db,manager))
        await self.complete(ident)
        state = State(manager.userbots.directory/'2/settings.sqlite')
        self.assertEqual(len(state.conn.execute("SELECT text FROM notes WHERE name='large'").fetchone()[0]),65000)
        state.close()

    async def test_http_chunks_and_ui_confirmation_are_owner_scoped(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from subgate.server_api import routes
        from subgate.master_ui import MasterUI
        self.manager.migrations = self.migrations
        ui = MasterUI(self.db,FakeAPI(),self.manager)
        try:
            with self.assertRaises(PermissionError): await ui.server_callback(3,'srv:place:2:1')
            await ui.server_callback(1,'srv:place:2:1')
            self.assertIsNone(self.migrations.latest(2))
            self.assertEqual(ui.state(1)['kind'],'migration_confirm')
            await ui.server_callback(1,'srv:migrate:2:1')
            ident = self.migrations.latest(2)['id']
            with self.assertRaises(ValueError): await ui.server_callback(1,'srv:migrate:2:1')
            await self.migrations.tick()
            app = web.Application(client_max_size=16000)
            routes(app,self.servers)
            client = TestClient(TestServer(app))
            await client.start_server()
            try:
                body = {'action':'get','id':ident,'part':0}
                r = await client.post('/servers/migration',json=body)
                self.assertEqual(r.status,403)
                r = await client.post('/servers/migration',headers={'Authorization':'Bearer '+'2'*64},json=body)
                self.assertEqual(r.status,403)
                r = await client.post('/servers/migration',headers={'Authorization':'Bearer '+'1'*64},json=body)
                self.assertEqual(r.status,200)
                self.assertLessEqual(len(base64.b64decode((await r.json())['data'])),CHUNK)
                body['part'] = -1
                r = await client.post('/servers/migration',headers={'Authorization':'Bearer '+'1'*64},json=body)
                self.assertEqual(r.status,400)
            finally:
                await client.close()
        finally:
            await ui.close()

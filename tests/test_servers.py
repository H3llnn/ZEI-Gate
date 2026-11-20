import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet

from subgate.master_ui import MasterUI
from subgate.runtime import Manager
from subgate.server_api import routes
from subgate.servers import Servers, LEASE_SECONDS
from subgate.store import Store
from subgate.worker import Worker, validate_origin
from subgate.telegram import API
from subgate.service import TelegramFailure
from test_runtime import FakeRunner
from test_service import FakeAPI


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.key = Fernet.generate_key()
        self.db = Store(self.root/'gate.sqlite', self.key, 1)
        self.db.grant(1, 2, 'both')
        self.servers = Servers(self.db)
        self.server, self.code = self.servers.add(1,'Klien 1')
        self.token = 'x'*64
        self.api = FakeAPI()
        self.manager = Manager(self.db,500,authenticate=self.auth,runner_factory=lambda *args: FakeRunner(self.api))
        self.manager.servers = self.servers
        self.worker_db = Store(self.root/'worker.sqlite',Fernet.generate_key(),1)
        self.worker_manager = Manager(self.worker_db,0,runner_factory=lambda *args: FakeRunner(self.api))
        self.worker = Worker(self.worker_db,self.worker_manager)

    async def auth(self,*args):
        return {'id':99,'username':'ClientBot','name':'Klien'}, 'session'

    async def asyncTearDown(self):
        await self.worker_manager.close()
        await self.manager.close()
        self.worker_db.close()
        self.db.close()
        self.temp.cleanup()

    def connect(self):
        self.servers.enroll(self.code,self.token)
        self.servers.heartbeat(self.token,{})
        self.servers.place(1,2,self.server)

    async def sync(self):
        snapshot = self.servers.heartbeat(self.token,self.worker.report())
        await self.worker.apply(snapshot,time.monotonic())
        self.servers.heartbeat(self.token,self.worker.report())

    def deploy_record(self,kind='forcesubs'):
        self.db.deploy(2,99,'ClientBot',123,'a'*32,'99:'+'x'*30,'session',kind=kind)

    async def test_enrollment_single_use_expiry_and_owner_guard(self):
        with self.assertRaises(PermissionError):
            self.servers.add(2,'Forbidden')
        self.assertEqual(self.servers.enroll(self.code,self.token),self.server)
        self.assertEqual(self.servers.enroll(self.code,self.token),self.server)
        with self.assertRaises(PermissionError):
            self.servers.enroll(self.code,'y'*64)
        self.servers.heartbeat(self.token,{})
        with self.assertRaises(PermissionError):
            self.servers.enroll(self.code,self.token)
        server,code=self.servers.add(1,'Expired')
        with self.db.conn:
            self.db.conn.execute('UPDATE servers SET code_until=0 WHERE id=?',(server,))
        with self.assertRaises(PermissionError):
            self.servers.enroll(code,'z'*64)
        with self.assertRaises(PermissionError):
            self.servers.authenticate('z'*64)

    async def test_assignment_requires_online_and_does_not_move_existing_bots(self):
        with self.assertRaises(ValueError):
            self.servers.place(1,2,self.server)
        self.connect()
        self.deploy_record()
        with self.assertRaises(ValueError):
            self.servers.place(1,2,None)
        with self.assertRaises(PermissionError):
            self.servers.place(2,2,None)
        self.assertEqual(self.servers.assigned(2),self.server)

    async def test_remote_deploy_waits_for_worker_and_never_runs_on_gate(self):
        self.connect()
        task=asyncio.create_task(self.manager.deploy(2,123,'a'*32,'99:'+'x'*30))
        await asyncio.sleep(0)
        await self.sync()
        result=await asyncio.wait_for(task,2)
        self.assertEqual(result['id'],99)
        self.assertNotIn(99,self.manager.running)
        self.assertIn(99,self.worker_manager.running)
        self.assertTrue(self.manager.is_running(99))
        await self.manager.restore()
        self.assertEqual(self.manager.running,{})

    async def test_revoke_and_regrant_preserve_worker_data_and_require_redeploy(self):
        self.connect()
        self.deploy_record('payment')
        await self.sync()
        self.worker_db.setting(99,2,'payment_welcome','Custom')
        await self.manager.revoke(1,2,'payment')
        await self.sync()
        self.assertNotIn(99,self.worker_manager.running)
        await self.manager.grant(1,2,'payment',preserve=True)
        await self.sync()
        self.assertNotIn(99,self.worker_manager.running)
        self.deploy_record('payment')
        await self.sync()
        self.assertIn(99,self.worker_manager.running)
        self.assertEqual(self.worker_db.settings(99)['payment_welcome'],'Custom')

    async def test_repeated_sync_preserves_settings_jobs_links_and_credentials(self):
        self.connect()
        self.deploy_record()
        await self.sync()
        before=self.worker_db.bot(99)['credentials']
        self.worker_db.setting(99,2,'welcome','Custom welcome')
        runner=self.worker_manager.running[99]
        await self.sync()
        self.assertIs(self.worker_manager.running[99],runner)
        self.assertEqual(self.worker_db.bot(99)['credentials'],before)
        self.assertEqual(self.worker_db.settings(99)['welcome'],'Custom welcome')

    async def test_lease_expiry_stops_and_restart_needs_new_snapshot(self):
        self.connect()
        self.deploy_record()
        await self.sync()
        self.worker.deadline=0
        await self.worker.expire()
        self.assertNotIn(99,self.worker_manager.running)
        await self.worker_manager.restore()
        self.assertEqual(self.worker_manager.running,{})
        await self.sync()
        self.assertIn(99,self.worker_manager.running)

    async def test_isolation_and_status_reject_foreign_bot_report(self):
        self.connect()
        self.deploy_record()
        other,code=self.servers.add(1,'Other')
        token='y'*64
        self.servers.enroll(code,token)
        payload=self.servers.heartbeat(token,{'99':{'running':True,'revision':self.servers.revision(self.db.bot(99))}})
        self.assertEqual(payload['bots'],[])
        self.assertFalse(self.servers.running(99))
        self.assertNotIn('token',self.servers.get(self.server)['report'])

    async def test_offline_remote_does_not_fall_back_to_gate(self):
        self.connect()
        self.deploy_record()
        with self.db.conn:
            self.db.conn.execute('UPDATE servers SET last_seen=0')
        with self.assertRaises(ValueError):
            await self.manager._start(99)
        await self.manager.restore()
        self.assertEqual(self.manager.running,{})

    async def test_http_enrollment_auth_and_roundtrip(self):
        app=web.Application()
        routes(app,self.servers)
        client=TestClient(TestServer(app))
        await client.start_server()
        try:
            response=await client.post('/servers/enroll',json={'code':self.code,'token':self.token})
            self.assertEqual(response.status,200)
            response=await client.post('/servers/sync',json={'report':{}})
            self.assertEqual(response.status,403)
            response=await client.post('/servers/sync',headers={'Authorization':'Bearer '+self.token},json={'report':{}})
            self.assertEqual(response.status,200)
            self.assertEqual((await response.json())['lease_seconds'],LEASE_SECONDS)
        finally:
            await client.close()

    async def test_menu_and_assignment_are_owner_only(self):
        ui=MasterUI(self.db,self.api,self.manager)
        self.manager.creation=SimpleNamespace(public_base='https://gate.example')
        try:
            await ui.menu(1)
            self.assertIn('srv:list:0',str(self.api.calls))
            with self.assertRaises(PermissionError):
                await ui.callback(2,'srv:add',{})
            self.connect()
            await ui.callback(1,'srv:place:2:'+str(self.server),{})
            self.assertIn('Klien 1',str(self.api.calls))
        finally:
            await ui.close()

    async def test_public_origin_requires_https_without_credentials(self):
        self.assertEqual(validate_origin('https://gate.example/'),'https://gate.example')
        for value in ['http://gate.example','https://user:secret@gate.example','https://gate.example/path','https://gate.example?key=secret']:
            with self.assertRaises(ValueError):
                validate_origin(value)

    async def test_expired_lease_blocks_telegram_calls_before_network(self):
        api=API('99:'+'x'*30)
        api.lease_check=lambda: False
        try:
            with self.assertRaises(TelegramFailure):
                await api.call('sendMessage',chat_id=1,text='must not send')
            with self.assertRaises(TelegramFailure):
                await api.send_photo_bytes(1,b'','',{})
        finally:
            await api.close()

    async def test_gate_restart_preserves_pairing_and_placement(self):
        self.connect()
        again=Servers(self.db)
        self.assertEqual(again.authenticate(self.token)['id'],self.server)
        self.assertEqual(again.assigned(2),self.server)

    async def test_stopped_bot_remains_stopped_after_worker_restart(self):
        self.connect()
        self.deploy_record()
        await self.sync()
        await self.manager.toggle(1,99,False)
        await self.sync()
        self.assertNotIn(99,self.worker_manager.running)
        await self.worker_manager.close()
        self.worker_manager=Manager(self.worker_db,0,runner_factory=lambda *args: FakeRunner(self.api))
        self.worker=Worker(self.worker_db,self.worker_manager)
        await self.sync()
        self.assertNotIn(99,self.worker_manager.running)

    async def test_failed_bot_does_not_block_other_bot(self):
        self.connect()
        self.deploy_record()
        self.db.deploy(2,100,'SecondBot',123,'a'*32,'100:'+'x'*30,'session')
        original=self.worker_manager._start
        async def start(bot):
            if bot==99:
                raise ValueError('unavailable')
            return await original(bot)
        self.worker_manager._start=start
        await self.sync()
        self.assertNotIn(99,self.worker_manager.running)
        self.assertIn(100,self.worker_manager.running)

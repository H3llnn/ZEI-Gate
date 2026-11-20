import asyncio
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from subgate.creation import Creation
from subgate.userbot_help import handle
from subgate.userbots import Userbots
from zei_userbot.state import State
import test_servers as fixtures


class RemoteUserbotTests(unittest.IsolatedAsyncioTestCase):
    auth = fixtures.ServerTests.auth
    connect = fixtures.ServerTests.connect
    sync = fixtures.ServerTests.sync
    asyncTearDown = fixtures.ServerTests.asyncTearDown

    async def asyncSetUp(self):
        await fixtures.ServerTests.asyncSetUp(self)
        self.db.grant(1,2,'all')
        self.manager.userbots=Userbots(self.db,self.root/'gate-accounts','MasterBot')
        self.manager.userbots.servers=self.servers
        self.servers.helper='MasterBot'
        async def factory(owner,credentials):
            return SimpleNamespace(stop=self.stop)
        self.worker_manager.userbots.factory=factory

    async def stop(self):
        pass

    def account(self):
        import json
        creds={'api_id':123,'api_hash':'a'*32,'session':'private-session'}
        with self.db.conn:
            self.db.conn.execute('INSERT INTO userbots(owner,name,credentials) VALUES (?,?,?) ON CONFLICT(owner) DO UPDATE SET credentials=excluded.credentials,active=1,redeploy_required=0',
                                 (2,'Budi',self.db.cipher.encrypt(json.dumps(creds).encode())))
        return creds

    async def test_remote_account_runs_only_on_assigned_worker(self):
        self.connect()
        self.account()
        await self.sync()
        await self.manager.userbots.reconcile()
        self.assertNotIn(2,self.manager.userbots.running)
        self.assertIn(2,self.worker_manager.userbots.running)
        self.assertTrue(self.manager.userbots.is_running(2))
        self.assertEqual(self.worker_manager.userbots.helper,'MasterBot')

    async def test_account_cannot_move_without_its_data(self):
        self.connect()
        self.account()
        with self.assertRaises(ValueError):
            self.servers.place(1,2,None)

    async def test_remote_deploy_waits_for_actual_report(self):
        self.connect()
        task=asyncio.create_task(self.manager.userbots.deploy(2,{'api_id':123,'api_hash':'a'*32,'session':'private'}, {'id':2,'name':'Budi'}))
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        await self.sync()
        await asyncio.wait_for(task,2)
        self.assertTrue(self.manager.userbots.is_running(2))

    async def test_prefix_roundtrip_does_not_override_account_changes(self):
        self.connect()
        self.account()
        await self.sync()
        task=asyncio.create_task(self.manager.userbots.set_prefix(2,'!'))
        await asyncio.sleep(0)
        await self.sync()
        await asyncio.wait_for(task,2)
        self.assertEqual(self.manager.userbots.prefix(2),'!')
        await self.worker_manager.userbots.set_prefix(2,'#')
        await self.sync()
        self.assertEqual(self.manager.userbots.prefix(2),'#')
        await self.sync()
        self.assertEqual(self.worker_manager.userbots.prefix(2),'#')

    async def test_revoke_stops_account_and_regrant_needs_login(self):
        self.connect()
        self.account()
        await self.sync()
        await self.manager.revoke(1,2,'userbot')
        await self.sync()
        self.assertNotIn(2,self.worker_manager.userbots.running)
        await self.manager.grant(1,2,'userbot',preserve=True)
        await self.sync()
        self.assertNotIn(2,self.worker_manager.userbots.running)
        self.account()
        await self.sync()
        self.assertIn(2,self.worker_manager.userbots.running)

    async def test_lease_expiry_stops_account_and_fresh_sync_restores(self):
        self.connect()
        self.account()
        await self.sync()
        self.worker.deadline=0
        await self.worker.expire()
        self.assertNotIn(2,self.worker_manager.userbots.running)
        await self.worker_manager.userbots.reconcile()
        self.assertNotIn(2,self.worker_manager.userbots.running)
        await self.sync()
        self.assertIn(2,self.worker_manager.userbots.running)

    async def test_inline_help_reads_remote_prefix(self):
        self.connect()
        self.account()
        await self.sync()
        await self.worker_manager.userbots.set_prefix(2,'!')
        await self.sync()
        ui=SimpleNamespace(manager=self.manager,db=self.db,api=self.api)
        await handle(ui,{'callback_query':{'id':'cb','from':{'id':2},'data':'uh:2:dasar:ping','inline_message_id':'msg'}})
        self.assertEqual(self.api.calls[-1][0],'editMessageText')
        self.assertIn('!ping',self.api.calls[-1][1]['text'])
        self.assertFalse((self.root/'gate-accounts'/'2').exists())

    async def test_other_server_cannot_receive_account_session(self):
        self.connect()
        self.account()
        other,code=self.servers.add(1,'Other')
        token='y'*64
        self.servers.enroll(code,token)
        snapshot=self.servers.heartbeat(token,{})
        self.assertEqual(snapshot['userbots'],[])
        self.assertNotIn('private-session',str(snapshot))

import asyncio
import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode
from types import SimpleNamespace
from cryptography.fernet import Fernet
from subgate.creation import telegram_identity, Creation
from subgate.store import Store
from subgate.runtime import Manager
from subgate.userbots import Userbots
from zei_userbot.state import State
from zei_userbot.runtime import Runtime
from zei_userbot.login import Login

TOKEN = "500:"+"x"*30


def signed(owner=2, stamp=None):
    data={"auth_date":str(int(time.time()) if stamp is None else stamp),"user":json.dumps({"id":owner,"first_name":"Budi"}),"query_id":"test"}
    key=hmac.new(b"WebAppData",TOKEN.encode(),hashlib.sha256).digest()
    data["hash"]=hmac.new(key,"\n".join(f"{k}={v}" for k,v in sorted(data.items())).encode(),hashlib.sha256).hexdigest()
    return urlencode(data)


class Request:
    def __init__(self, payload, token=""):
        self.payload=payload
        self.headers={"Authorization":"Bearer "+token}
    async def json(self): return self.payload


class FakeLogin:
    closes=[]
    def __init__(self, owner, api_id, api_hash): self.owner=owner
    async def begin(self, phone): return "otp"
    async def code(self, code): return {"step":"summary","id":self.owner,"name":"Budi","username":"budi"}
    async def password(self, password): return await self.code("")
    def credentials(self): return {"api_id":123,"api_hash":"a"*32,"session":"private-session"}
    async def close(self, discard=False): self.closes.append(discard)


class FakeRunner:
    def __init__(self): self.stopped=False
    async def stop(self): self.stopped=True


class CreationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Store(Path(self.tmp.name)/"gate.sqlite",Fernet.generate_key(),1)
        self.db.grant(1,2,"all")
        self.created=[]
        async def factory(owner, credentials):
            runner=FakeRunner();self.created.append(runner);return runner
        async def authenticate(*args): return {"id":99,"username":"ChildBot","name":"Child"},"session"
        self.manager=Manager(self.db,500,authenticate=authenticate,runner_factory=lambda *args:FakeRunner())
        self.manager.userbots=Userbots(self.db,Path(self.tmp.name)/"accounts","MasterBot",factory)
        self.creation=Creation(self.db,self.manager,TOKEN,"https://zei.example","MasterBot",login_factory=FakeLogin)
        response=await self.creation.auth(Request({"initData":signed()}))
        self.token=json.loads(response.text)["token"]

    async def asyncTearDown(self):
        await self.creation.close();await self.manager.close();self.db.close();self.tmp.cleanup()

    async def action(self, action, **args):
        response=await self.creation.action(Request({"action":action,**args},self.token))
        return json.loads(response.text)

    async def login(self, kind="userbot"):
        await self.action("choose",kind=kind)
        await self.action("api",api_id=123,api_hash="a"*32)
        if kind=="userbot":
            await self.action("phone",phone="+628123456789")
            return await self.action("otp",code="12345")
        return await self.action("token",token="99:"+"y"*30)

    async def test_http_auth_origin_and_security_headers(self):
        from aiohttp.test_utils import TestClient, TestServer
        client=TestClient(TestServer(self.creation.app))
        await client.start_server()
        try:
            response=await client.post('/api/auth',json={'initData':signed()},headers={'Origin':'https://attacker.example'})
            self.assertEqual(response.status,403)
            response=await client.post('/api/auth',json={'initData':signed()})
            self.assertEqual(response.status,200)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIn("default-src 'self'",response.headers['Content-Security-Policy'])
            response=await client.post('/api/action',json={'action':'create'},headers={'Authorization':'Bearer invalid'})
            self.assertEqual(response.status,403)
            response=await client.get('/')
            self.assertEqual(response.status,200)
            self.assertNotIn('private-session',await response.text())
        finally: await client.close()

    async def test_signed_identity_rejects_tamper_stale_future_duplicate(self):
        self.assertEqual(telegram_identity(signed(),TOKEN)["id"],2)
        for raw in (signed().replace("Budi","Other"),signed(stamp=1),signed(stamp=int(time.time())+120),signed()+"&auth_date=1"):
            with self.assertRaises((PermissionError,ValueError)): telegram_identity(raw,TOKEN)

    async def test_session_owner_and_secret_redaction(self):
        with self.assertRaises(PermissionError): await self.creation.action(Request({"action":"status"},"bad"))
        data=await self.login()
        self.assertEqual(data["step"],"summary")
        self.assertNotIn("api_hash",data)
        self.assertNotIn("private-session",json.dumps(data))
        self.assertNotIn("12345",json.dumps(data))

    async def test_create_double_click_starts_once_and_encrypts(self):
        await self.login()
        results=await asyncio.gather(self.action("create"),self.action("create"))
        self.assertTrue(all(r["step"]=="done" for r in results))
        self.assertEqual(len(self.created),1)
        record=self.manager.userbots.record(2)
        self.assertNotIn(b"private-session",record["credentials"])
        self.assertIn(2,self.manager.userbots.running)

    async def test_revoke_stops_and_regrant_requires_redeploy(self):
        await self.login();await self.action("create")
        runner=self.created[0]
        await self.manager.revoke(1,2,"userbot")
        self.assertTrue(runner.stopped)
        self.assertTrue(self.db.allowed(2,"forcesubs"))
        await self.manager.grant(1,2,"all");await self.manager.restore()
        self.assertNotIn(2,self.manager.userbots.running)
        self.assertEqual(self.manager.userbots.record(2)["redeploy_required"],1)

    async def test_permission_rechecked_before_create(self):
        await self.login();await self.manager.revoke(1,2,"userbot")
        with self.assertRaises(PermissionError): await self.action("create")
        self.assertFalse(self.created)

    async def test_expiry_and_cancel_do_not_deploy(self):
        await self.login()
        self.creation.sessions[self.token].touched-=601
        with self.assertRaises(PermissionError): await self.action("create")
        self.assertFalse(self.created)
        self.assertNotIn(self.token,self.creation.sessions)

    async def test_bot_create_preserves_old_flows(self):
        await self.login("forcesubs")
        data=await self.action("create")
        self.assertEqual(data["result"]["username"],"ChildBot")
        self.assertTrue(self.db.bot(99)["active"])

    async def test_failed_reconnect_keeps_old_record_and_process(self):
        await self.login();await self.action("create")
        old=self.created[0];encrypted=self.manager.userbots.record(2)["credentials"]
        async def fail(*args): raise ValueError("network")
        self.manager.userbots.factory=fail
        with self.assertRaises(ValueError): await self.manager.userbots.deploy(2,{"session":"new"},{"id":2,"name":"Budi"})
        self.assertFalse(old.stopped)
        self.assertIs(self.manager.userbots.running[2],old)
        self.assertEqual(self.manager.userbots.record(2)["credentials"],encrypted)

    async def test_service_combinations_and_data_preservation(self):
        await self.login();await self.action("create")
        await self.manager.grant(1,2,"payment+userbot")
        self.assertFalse(self.db.allowed(2,"forcesubs"))
        self.assertTrue(self.db.allowed(2,"payment"));self.assertTrue(self.db.allowed(2,"userbot"))
        self.assertIn(2,self.manager.userbots.running)
        await self.manager.revoke(1,2,"all")
        self.assertFalse(self.db.allowed(2))
        self.assertIsNotNone(self.manager.userbots.record(2))

    async def test_back_discards_pending_authorization(self):
        await self.login()
        session=self.creation.sessions[self.token]
        result=await self.action('back')
        self.assertEqual(result['step'],'phone')
        self.assertIsNone(session.login)
        self.assertEqual(session.identity,{})
        self.assertTrue(FakeLogin.closes[-1])
        self.assertFalse(self.created)

    async def test_inline_help_rejects_other_account_and_revoked_owner(self):
        from subgate.userbot_help import handle
        from unittest.mock import AsyncMock
        await self.login();await self.action('create')
        ui=SimpleNamespace(manager=self.manager,db=self.db,api=SimpleNamespace(call=AsyncMock()))
        await handle(ui,{'callback_query':{'id':'q1','from':{'id':3},'data':'uh:2:admin','inline_message_id':'m1'}})
        self.assertEqual(ui.api.call.await_args.args[0],'answerCallbackQuery')
        self.assertTrue(ui.api.call.await_args.kwargs['show_alert'])
        ui.api.call.reset_mock()
        await self.manager.revoke(1,2,'userbot')
        await handle(ui,{'inline_query':{'id':'q2','from':{'id':2},'query':'zei-help'}})
        self.assertEqual(ui.api.call.await_args.kwargs['results'],[])

    async def test_parent_eof_stops_supervised_process(self):
        import sys
        from subgate.userbots import Process
        child=await asyncio.create_subprocess_exec(sys.executable,'-c','import sys;sys.stdin.read()',stdin=asyncio.subprocess.PIPE)
        runner=Process(child)
        await runner.stop()
        self.assertEqual(child.returncode,0)

    async def test_new_creation_after_success_clears_secrets_and_keeps_service(self):
        await self.login();await self.action('create')
        result=await self.action('new')
        self.assertEqual(result['step'],'choose')
        self.assertTrue(result['existing'])
        self.assertIn(2,self.manager.userbots.running)
        session=self.creation.sessions[self.token]
        self.assertEqual((session.api_hash,session.bot_token,session.identity),('', '', {}))
        with self.assertRaises(ValueError):
            self.db.deploy(2,99,'ChildBot',123,'a'*32,'token','session',kind='userbot')

    async def test_bad_identity_does_not_spawn(self):
        with self.assertRaises(PermissionError): await self.manager.userbots.deploy(2,{}, {"id":3,"name":"Other"})
        self.assertFalse(self.created)


class PrefixTests(unittest.TestCase):
    def test_dynamic_prefix_and_owner_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=State(Path(tmp)/"settings.sqlite")
            runtime=object.__new__(Runtime);runtime.owner=2;runtime.state=state
            self.assertEqual(runtime.parse(".help",2),("help",""))
            self.assertIsNone(runtime.parse(".help",3))
            self.assertIsNone(runtime.parse(".help",2,False))
            state.set("prefix","!")
            self.assertIsNone(runtime.parse(".help",2))
            self.assertEqual(runtime.parse("!prefix #",2),("prefix","#"))
            for bad in ("", "abc", " ", "....", "! "):
                with self.assertRaises(ValueError): state.set("prefix",bad)
            state.close()
            state=State(Path(tmp)/"settings.sqlite");self.assertEqual(state.prefix,"!");state.close()


class LoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_account_logout_and_disconnect(self):
        class Client:
            def __init__(self,*args,**kwargs): self.logged_out=False;self.disconnected=False
            async def get_me(self): return SimpleNamespace(id=3,bot=False)
            async def log_out(self): self.logged_out=True
            async def disconnect(self): self.disconnected=True
        login=Login(2,123,"a"*32,Client)
        with self.assertRaises(PermissionError): await login.identity()
        self.assertTrue(login.client.logged_out);self.assertTrue(login.client.disconnected)

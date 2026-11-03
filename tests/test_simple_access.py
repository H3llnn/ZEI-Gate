import tempfile
import unittest
from pathlib import Path
from cryptography.fernet import Fernet
from subgate.store import Store
from subgate.runtime import Manager
from subgate.master_ui import MasterUI
from test_service import FakeAPI


class SimpleAccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Store(Path(self.tmp.name)/'db',Fernet.generate_key(),1)
        self.manager=Manager(self.db,500)
        self.ui=MasterUI(self.db,FakeAPI(),self.manager)

    async def asyncTearDown(self):
        await self.ui.close()
        await self.manager.close()
        self.db.close()
        self.tmp.cleanup()

    async def test_grants_are_independent_and_no_combinations_are_offered(self):
        await self.ui.grant(1,2)
        sent=self.ui.api.calls[-1][1]
        buttons=sent['reply_markup']['inline_keyboard']
        actions=[b['callback_data'] for row in buttons for b in row if b.get('callback_data','').startswith('m:grant_kind:')]
        self.assertEqual(set(actions),{'m:grant_kind:2:'+k for k in ('userbot','payment','forcesubs')})
        await self.ui.callback(1,'m:grant_kind:2:userbot',{})
        await self.ui.grant(1,2)
        await self.ui.callback(1,'m:grant_kind:2:payment',{})
        self.assertTrue(self.db.allowed(2,'userbot'))
        self.assertTrue(self.db.allowed(2,'payment'))
        self.assertFalse(self.db.allowed(2,'forcesubs'))

    async def test_home_has_no_userbot_mine_button(self):
        self.manager.userbots=object()
        await self.ui.menu(1)
        buttons=self.ui.api.calls[-1][1]['reply_markup']['inline_keyboard']
        self.manager.userbots=None
        self.assertNotIn('u:mine',[b.get('callback_data') for row in buttons for b in row])

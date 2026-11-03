import asyncio
import tempfile
import unittest
from pathlib import Path
from cryptography.fernet import Fernet
from subgate.store import Store
from subgate.runtime import Manager
from subgate.master_ui import MasterUI
from test_service import FakeAPI


class UserPermissionUITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.key = Fernet.generate_key()
        self.path = Path(self.tmp.name) / 'db'
        self.db = Store(self.path, self.key, 1)
        self.manager = Manager(self.db, 500)
        self.api = FakeAPI()
        self.ui = MasterUI(self.db, self.api, self.manager)
        self.message = {'message_id': 77, 'chat': {'id': 1}}

    async def asyncTearDown(self):
        await self.ui.close()
        await self.manager.close()
        self.db.close()
        self.tmp.cleanup()

    async def test_nonowner_cannot_toggle(self):
        with self.assertRaises(PermissionError):
            await self.ui.callback(3, 'm:permission_toggle:2:payment', self.message)
        self.assertFalse(self.db.allowed(2, 'payment'))

    async def test_names_survive_restart_and_buttons_hide_identifiers(self):
        self.db.grant(1, 2)
        await self.ui.handle({'message': {'message_id': 1, 'chat': {'id': 2},
            'from': {'id': 2, 'first_name': 'Nama', 'last_name': 'Telegram', 'username': 'handle'}, 'text': '/start'}})
        self.db.close()
        self.db = Store(self.path, self.key, 1)
        self.ui = MasterUI(self.db, self.api, self.manager)
        await self.ui.users_menu(1)
        label = self.api.calls[-1][1]['reply_markup']['inline_keyboard'][0][0]['text']
        self.assertEqual(label, 'Nama Telegram')

    async def test_toggle_rechecks_preserves_and_edits_same_message(self):
        self.db.grant(1, 2, 'userbot')
        await self.ui.callback(1, 'm:permissions:2', self.message)
        self.db.grant(1, 2, 'forcesubs', preserve=True)
        await self.ui.callback(1, 'm:permission_toggle:2:payment', self.message)
        self.assertTrue(all(self.db.allowed(2, k) for k in ('payment', 'forcesubs', 'userbot')))
        await asyncio.gather(*(self.ui.callback(1, 'm:permission_toggle:2:payment', self.message) for _ in range(2)))
        self.assertTrue(self.db.allowed(2, 'payment'))
        await self.ui.callback(1, 'm:permission_toggle:2:payment', self.message)
        self.assertFalse(self.db.allowed(2, 'payment'))
        self.assertTrue(self.db.allowed(2, 'userbot'))
        self.assertTrue(self.db.allowed(2, 'forcesubs'))
        method, args = self.api.calls[-1]
        self.assertEqual(method, 'editMessageText')
        self.assertEqual(args['message_id'], 77)
        labels = [b['text'] for row in args['reply_markup']['inline_keyboard'] for b in row]
        self.assertEqual(labels[:3], ['✅ Userbot', '❌ Payment', '✅ ForceSubs'])
        self.assertIn('Userbot, ForceSubs', args['text'])

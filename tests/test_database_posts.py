import tempfile
import unittest
from pathlib import Path
from cryptography.fernet import Fernet
from subgate.store import Store
from zei_forcesubs.child_ui import ChildUI


class DatabasePosts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.folder.name)/'test.sqlite', Fernet.generate_key(), 1)
        self.db.deploy(1, 99, 'test_bot', 1, 'hash', 'token', 'session')
        self.db.setting(99, 1, 'database', -1001)
        self.calls = []
        test = self
        class API:
            async def call(self, method, **args):
                test.calls.append((method, args))
                return {'message_id': 100}
        self.ui = ChildUI(self.db, 99, API())

    async def asyncTearDown(self):
        await self.ui.close()
        self.db.close()
        self.folder.cleanup()

    async def test_direct_text_link_and_duplicate_edit(self):
        message = dict(chat={'id': -1001, 'type': 'channel'}, message_id=7, text='Hello')
        await self.ui.handle({'channel_post': message})
        await self.ui.handle({'channel_post': message})
        await self.ui.handle({'edited_channel_post': dict(message, text='Updated')})
        links = self.db.rows('SELECT key FROM links')
        self.assertEqual(len(links), 1)
        self.assertEqual(self.db.sources(99, links[0]['key']), [(-1001, 7)])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1]['reply_parameters'], {'message_id': 7})

    async def test_edit_refreshes_album_metadata_without_new_link(self):
        message = dict(chat={'id': -1001, 'type': 'channel'}, message_id=8,
                       video={'file_id': 'old'}, caption='old')
        await self.ui.handle({'channel_post': message})
        await self.ui.handle({'edited_channel_post': dict(message, video={'file_id': 'new'}, caption='new')})
        self.assertEqual(self.db.content(99, -1001, 8), {'type': 'video', 'media': 'new', 'caption': 'new'})
        self.assertEqual(len(self.calls), 1)

    async def test_other_channels_and_bot_posts_do_not_create_links(self):
        await self.ui.handle({'channel_post': dict(chat={'id': -1002, 'type': 'channel'}, message_id=1, text='ignored')})
        await self.ui.handle({'channel_post': dict(chat={'id': -1001, 'type': 'channel'}, message_id=2, text='bot', **{'from': {'is_bot': True}})})
        self.assertEqual(self.db.rows('SELECT key FROM links'), [])
        self.assertEqual(self.calls, [])

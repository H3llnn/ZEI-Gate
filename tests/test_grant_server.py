from test_user_permission_ui import UserPermissionUITests
from subgate.servers import Servers


class GrantServerTests(UserPermissionUITests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.manager.servers = Servers(self.db)
        self.server, code = self.manager.servers.add(1, 'YAHAHA')
        self.manager.servers.enroll(code, 'x'*64)
        self.manager.servers.heartbeat('x'*64, {})

    async def test_new_user_gets_server_question_before_access(self):
        await self.ui.grant(1, 8)
        await self.ui.callback(1, 'm:grant_kind:8:forcesubs', self.message)
        self.assertFalse(self.db.allowed(8))
        self.assertEqual(self.ui.state(1)['kind'], 'grant_server')
        await self.ui.callback(1, f'srv:grant:8:{self.server}', self.message)
        self.assertTrue(self.db.allowed(8, 'forcesubs'))
        self.assertEqual(self.manager.servers.assigned(8), self.server)

    async def test_offline_target_and_stale_callback_do_not_grant_access(self):
        await self.ui.grant(1, 8)
        await self.ui.callback(1, 'm:grant_kind:8:payment', self.message)
        with self.db.conn:
            self.db.conn.execute('UPDATE servers SET last_seen=0')
        with self.assertRaises(ValueError):
            await self.ui.callback(1, f'srv:grant:8:{self.server}', self.message)
        self.assertFalse(self.db.allowed(8))
        self.ui.clear(1)
        with self.assertRaises(ValueError):
            await self.ui.callback(1, 'srv:grant:8:0', self.message)
        self.assertFalse(self.db.allowed(8))

    async def test_main_server_can_be_selected(self):
        await self.ui.grant(1, 8)
        await self.ui.callback(1, 'm:grant_kind:8:userbot', self.message)
        await self.ui.callback(1, 'srv:grant:8:0', self.message)
        self.assertTrue(self.db.allowed(8, 'userbot'))
        self.assertIsNone(self.manager.servers.assigned(8))

from test_database_posts import DatabasePosts


class AdminManagement(DatabasePosts):
    async def test_admin_can_manage_only_own_forcesubs(self):
        self.db.admin(99, 1, 2, True)
        self.db.setting(99, 2, 'database', -1002)
        self.db.target(99, 2, -1003, 'channel', 'https://t.me/example')
        self.db.remove_target(99, 2, -1003)
        self.db.admin(99, 2, 3, True)
        self.assertTrue(self.db.can_manage(99, 2))
        self.assertFalse(self.db.can_manage(99, 4))
        with self.assertRaises(PermissionError):
            self.db.setting(99, 4, 'database', -1004)
        with self.assertRaises(PermissionError):
            self.db.owner(99, 2)
        with self.assertRaises(PermissionError):
            self.db.set_active(2, 99, False)
        self.db.deploy(1, 100, 'payment_bot', 1, 'hash', 'token', 'session', kind='payment')
        self.db.admin(100, 1, 2, True)
        self.assertFalse(self.db.can_manage(100, 2))
        with self.assertRaises(PermissionError):
            self.db.setting(100, 2, 'database', -1004)

    async def test_admin_list_has_name_profile_link_and_escaped_html(self):
        self.db.telegram_profile(2, {'first_name': 'A < B', 'username': 'tester'})
        self.db.admin(99, 1, 2, True)
        await self.ui.admins_menu(2)
        text = next(args['text'] for method, args in self.calls if method=='sendMessage')
        self.assertIn('<a href="tg://user?id=2">A &lt; B</a>', text)
        self.assertNotIn('Admin hanya dapat membuat link', text)

    async def test_add_admin_caches_verified_name(self):
        previous = self.ui.api.call
        async def call(method, **args):
            if method=='getChat':
                return {'id': 3, 'type': 'private', 'first_name': 'Nama Admin'}
            return await previous(method, **args)
        self.ui.api.call = call
        await self.ui.save_setting(1, {'text': '3'}, 'add_admin')
        self.assertEqual(self.db.telegram_profile(3)['name'], 'Nama Admin')
        self.assertTrue(self.db.can_manage(99, 3))

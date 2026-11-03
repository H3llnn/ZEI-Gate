import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pathlib import Path

from subgate.userbot_help import screen, handle
from zei_userbot.runtime import CATEGORIES


class ButtonHelpTests(unittest.IsolatedAsyncioTestCase):
    def test_category_command_detail_navigation_and_prefix(self):
        text, markup = screen(2, '!')
        self.assertNotIn('!ping', text)
        self.assertEqual([b['text'].lower() for row in markup['inline_keyboard'] for b in row], list(CATEGORIES))
        text, markup = screen(2, '!', 'catatan')
        self.assertNotIn('!save', text)
        self.assertEqual(markup['inline_keyboard'][0][0]['text'], 'save')
        self.assertEqual(markup['inline_keyboard'][0][0]['callback_data'], 'uh:2:catatan:save')
        text, markup = screen(2, '!', 'catatan', command='save')
        self.assertIn('!save belanja', text)
        self.assertIn('Balas', text)
        self.assertEqual([b['callback_data'] for row in markup['inline_keyboard'] for b in row], ['uh:2:catatan', 'uh:2:home'])

    def test_every_command_has_example(self):
        for category, commands in CATEGORIES.items():
            for command in commands:
                text, _ = screen(2, '&', category, command=command)
                self.assertIn('&amp;' + command, text)
                self.assertIn('Contoh', text)

    async def test_unauthorized_and_invalid_callbacks_do_not_edit(self):
        for sender, permitted, running, data in [(3, True, True, 'uh:2:dasar:ping'), (2, False, True, 'uh:2:dasar:ping'), (2, True, False, 'uh:2:dasar:ping'), (2, True, True, 'uh:2:dasar:ban'), (2, True, True, 'uh:2:home:ping')]:
            api = SimpleNamespace(call=AsyncMock())
            ui = SimpleNamespace(api=api, db=SimpleNamespace(allowed=lambda *a: permitted), manager=SimpleNamespace(userbots=SimpleNamespace(running={2} if running else set())))
            await handle(ui, {'callback_query': {'id': 'q', 'from': {'id': sender}, 'data': data, 'inline_message_id': 'm'}})
            api.call.assert_awaited_once()
            self.assertTrue(api.call.await_args.kwargs['show_alert'])

    async def test_callback_reads_current_prefix_and_navigates(self):
        api = SimpleNamespace(call=AsyncMock())
        ui = SimpleNamespace(api=api, db=SimpleNamespace(allowed=lambda *a: True), manager=SimpleNamespace(userbots=SimpleNamespace(running={2}, directory=Path('unused'), helper='helper')))
        state = SimpleNamespace(prefix='!', close=lambda: None)
        with patch('subgate.userbot_help.State', return_value=state):
            for destination, expected in [('catatan', 'save'), ('catatan:save', '← Kembali'), ('home', 'Dasar')]:
                api.call.reset_mock()
                await handle(ui, {'callback_query': {'id': 'q', 'from': {'id': 2}, 'data': 'uh:2:' + destination, 'inline_message_id': 'm'}})
                self.assertEqual(api.call.await_args.args[0], 'editMessageText')
                self.assertEqual(api.call.await_args.kwargs['reply_markup']['inline_keyboard'][0][0]['text'], expected)
                if destination.endswith(':save'):
                    self.assertIn('!save belanja', api.call.await_args.kwargs['text'])

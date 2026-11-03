import importlib
import unittest


class RuntimePackageTests(unittest.TestCase):
    def test_legacy_imports_are_same_module(self):
        modules = {
            'service': 'zei_forcesubs.service',
            'child_ui': 'zei_forcesubs.child_ui',
            'payment_ui': 'zei_payment.payment_ui',
            'payment_store': 'zei_payment.payment_store',
            'payment_service': 'zei_payment.payment_service',
            'payment_webhook': 'zei_payment.payment_webhook',
            'saweria': 'zei_payment.saweria',
        }
        for old, new in modules.items():
            with self.subTest(module=old):
                self.assertIs(importlib.import_module('subgate.' + old), importlib.import_module(new))

    def test_telegram_exception_identity_is_preserved(self):
        from subgate.service import TelegramFailure
        from zei_forcesubs.service import TelegramFailure as actual
        from zei_payment.payment_service import TelegramFailure as payment
        self.assertIs(TelegramFailure, actual)
        self.assertIs(payment, actual)

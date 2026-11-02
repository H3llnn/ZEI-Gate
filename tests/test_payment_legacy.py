import json
import tempfile
import unittest
from pathlib import Path
from cryptography.fernet import Fernet
from subgate.store import Store
from subgate.payment_ui import PaymentUI
from test_service import FakeAPI


class LegacyPaymentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Store(Path(self.tmp.name)/'db',Fernet.generate_key(),1)
        self.db.grant(1,2,'both')
        self.db.deploy(2,99,'TestBot',123,'hash','token','session',kind='payment')
        self.key=self.db.link(99,2,[(-100123,7)])
        with self.db.conn:
            self.db.conn.execute('UPDATE bots SET settings=? WHERE id=99',(json.dumps({'legacy_forcesubs':True}),))
            self.db.conn.execute("INSERT INTO targets(bot,chat,kind,url,title) VALUES (99,-1005,'channel','https://t.me/old','Lama')")
        self.api=FakeAPI()
        self.ui=PaymentUI(self.db,99,self.api,provider=object())

    async def asyncTearDown(self):
        await self.ui.close();self.db.close();self.tmp.cleanup()

    async def test_old_link_still_requires_join_and_retry_sends_content(self):
        self.api.members[(-1005,3)]='left'
        await self.ui.message(3,{'text':'/start '+self.key})
        self.assertFalse(any(method=='copyMessage' for method,args in self.api.calls))
        self.assertTrue(any('get:'+self.key in str(args) for method,args in self.api.calls))
        self.api.members[(-1005,3)]='member'
        await self.ui.callback(3,'get:'+self.key,{})
        self.assertTrue(any(method=='copyMessage' for method,args in self.api.calls))
        self.assertTrue(self.db.rows('SELECT * FROM jobs WHERE bot=99'))
        self.assertEqual(self.db.rows('SELECT * FROM payment_orders'),[])

    async def test_ordinary_payment_bot_does_not_enable_legacy_delivery(self):
        await self.ui.close()
        with self.db.conn:self.db.conn.execute("UPDATE bots SET settings='{}' WHERE id=99")
        self.ui=PaymentUI(self.db,99,self.api,provider=object())
        await self.ui.message(3,{'text':'/start '+self.key})
        self.assertFalse(any(method=='copyMessage' for method,args in self.api.calls))

import unittest
import test_payment_integration as fixtures


class BundleUITests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.PaymentIntegrationTests.setUp
    asyncTearDown=fixtures.PaymentIntegrationTests.asyncTearDown
    msg=fixtures.PaymentIntegrationTests.msg
    cb=fixtures.PaymentIntegrationTests.cb

    async def test_owner_creates_bundle_and_buyer_sees_inclusions_and_saving(self):
        self.p.save_package(99,2,name='Channel B',description='',price=2000,target=-1002)
        await self.cb(2,'p:bundle_new')
        self.assertIsNotNone(self.ui.state(2))
        for text in ('Semua Akses','Dua koleksi sekaligus','1500'):
            await self.ui.handle(self.msg(2,text))
        await self.cb(2,'p:bundle_pick:-1001:0')
        await self.cb(2,'p:bundle_pick:-1002:0')
        await self.cb(2,'p:bundle_done')
        bundle=next(p for p in self.p.packages(99) if p['name']=='Semua Akses')
        self.assertEqual(len(bundle['targets']),2)
        await self.cb(3,f'p:package:{bundle["id"]}:0')
        sent=next(a for m,a in reversed(self.api.calls) if m=='sendMessage')
        self.assertIn('Channel B',sent['text'])
        self.assertIn('Hemat Rp1.500',sent['text'])
        self.assertIn('p:buy:',str(sent['reply_markup']))

    async def test_admin_and_buyer_cannot_create_or_edit_bundle_targets(self):
        self.db.admin(99,2,4,True)
        for user in (3,4):
            await self.cb(user,'p:bundle_new')
            self.assertIsNone(self.ui.state(user))
        self.assertEqual(len(self.p.packages(99)),1)

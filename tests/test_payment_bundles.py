import asyncio
import unittest
from subgate.payment_store import PaymentStore
from subgate.payment_service import PaymentService
from subgate.store import Store
from subgate.service import TelegramFailure
import test_payment_store as fixtures
from test_payment_service import FakePayAPI


class BundleTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.PaymentStoreTests.setUp
    tearDown=fixtures.PaymentStoreTests.tearDown

    def bundle(self):
        return self.p.save_package(99,2,name='Semua Akses',description='Hemat',price=1500,
            targets=[{'target':-1001,'name':'Channel A'},{'target':-1002,'name':'Channel B'}])

    def paid_bundle(self):
        ident=self.bundle()
        order=self.p.new_order(99,3,ident)
        self.p.attach(order['id'],'bundle-tx','000201',1500)
        self.p.accept(2,'bundle-tx',1500)
        return ident,order['id']

    def service(self):
        api=FakePayAPI()
        call=api.call
        async def unique(method,**kw):
            if method=='createChatInviteLink':
                await call(method,**kw)
                return {'invite_link':'https://t.me/+'+str(abs(kw['chat_id']))}
            return await call(method,**kw)
        api.call=unique
        return PaymentService(self.db,99,api,None),api

    async def test_bundle_snapshot_and_encrypted_links_survive_restart(self):
        ident,order_id=self.paid_bundle()
        self.p.save_package(99,2,ident,targets=[{'target':-1003,'name':'C'},{'target':-1004,'name':'D'}])
        service,api=self.service()
        await asyncio.gather(service.fulfill(order_id),service.fulfill(order_id))
        creates=[a for m,a in api.calls if m=='createChatInviteLink']
        self.assertEqual({a['chat_id'] for a in creates},{-1001,-1002})
        self.assertEqual(len(creates),2)
        sent=[a for m,a in api.calls if m=='sendMessage' and a['chat_id']==3]
        self.assertEqual(len(sent),1)
        self.assertEqual(len(sent[0]['reply_markup']['inline_keyboard']),2)
        stored=self.db.rows('SELECT accesses FROM payment_orders WHERE id=?',(order_id,))[0]['accesses']
        self.assertNotIn(b'https://t.me/',stored)
        self.db.close();self.db=Store(self.path,self.key,1);self.p=PaymentStore(self.db)
        service,api=self.service();await service.fulfill(order_id)
        self.assertFalse(any(m=='createChatInviteLink' for m,a in api.calls))
        self.assertEqual(len(self.p.order(99,order_id)['accesses']),2)

    async def test_each_link_consumed_independently_and_revoke_retries(self):
        _,order_id=self.paid_bundle();service,api=self.service()
        await service.fulfill(order_id)
        original=api.call
        async def broken(method,**kw):
            if method=='revokeChatInviteLink':raise TelegramFailure(503,'temporary')
            return await original(method,**kw)
        api.call=broken
        await service.join({'chat':{'id':-1001},'new_chat_member':{'status':'member'},'invite_link':{'invite_link':'https://t.me/+1001'}})
        order=self.p.order(99,order_id)
        self.assertTrue(order['accesses'][0]['used'])
        self.assertFalse(order['accesses'][1]['used'])
        self.assertFalse(order['used'])
        self.assertIn(order_id,[r['id'] for r in self.p.work(99)])
        api.call=original;await service.fulfill(order_id)
        self.assertTrue(self.p.order(99,order_id)['accesses'][0]['revoked'])
        self.assertEqual(len(service.access_buttons(self.p.order(99,order_id))),1)

    async def test_ambiguous_second_invite_never_recreated(self):
        _,order_id=self.paid_bundle();service,api=self.service()
        original=api.call
        async def broken(method,**kw):
            if method=='createChatInviteLink' and kw['chat_id']==-1002:
                await original(method,**kw)
                raise TelegramFailure(503,'unknown')
            return await original(method,**kw)
        api.call=broken;await service.fulfill(order_id)
        api.call=original;await service.fulfill(order_id)
        self.assertEqual(sum(m=='createChatInviteLink' for m,a in api.calls),2)
        self.assertFalse(self.p.order(99,order_id)['delivered'])

    async def test_bundle_rejects_duplicate_targets_admin_changes_and_false_discount(self):
        ident=self.bundle()
        self.db.admin(99,2,4,True)
        with self.assertRaises(PermissionError):self.p.save_package(99,4,ident,targets=[])
        with self.assertRaises(ValueError):self.p.save_package(99,2,ident,targets=[{'target':-1001,'name':'A'}]*2)
        self.assertIsNone(self.p.bundle_saving(99,self.p.package(99,ident)))
        self.p.save_package(99,2,name='B',description='',price=2000,target=-1002)
        self.assertEqual(self.p.bundle_saving(99,self.p.package(99,ident)),(3000,1500))

    async def test_stopped_bot_still_retries_partial_bundle_revocation(self):
        from unittest.mock import patch,AsyncMock
        from subgate.runtime import Manager
        _,order_id=self.paid_bundle()
        order=self.p.order(99,order_id)
        order['accesses'][0].update(invite='https://t.me/+1001',used=1)
        order['accesses'][1].update(invite='https://t.me/+1002')
        self.p.update(99,order_id,accesses=order['accesses'],bundle_revoke=1,notified=1,delivered=1)
        with self.db.conn:self.db.conn.execute('UPDATE bots SET active=0 WHERE id=99')
        _,api=self.service();api.close=AsyncMock()
        manager=Manager(self.db,500);manager.restore=AsyncMock()
        with patch('subgate.telegram.API',return_value=api),patch('subgate.runtime.asyncio.sleep',side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):await manager.maintenance()
        self.assertTrue(self.p.order(99,order_id)['accesses'][0]['revoked'])


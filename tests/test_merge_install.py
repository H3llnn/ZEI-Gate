import hashlib
import tempfile
import unittest
from pathlib import Path
from cryptography.fernet import Fernet
from subgate.store import Store
from subgate.payment_store import PaymentStore
from subgate.merge_install import merge


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.keys=[Fernet.generate_key(),Fernet.generate_key()]
        self.folders=[]
        for index,name in enumerate(('force','payment')):
            folder=self.root/name;folder.mkdir();self.folders.append(folder)
            (folder/'config.env').write_text('MASTER_BOT_TOKEN=500:'+('x'*30)+'\nMASTER_OWNER_ID=1\nSECRET_KEY='+self.keys[index].decode()+'\n')
            db=Store(folder/'subgate.sqlite',self.keys[index],1)
            kind='forcesubs' if index==0 else 'payment'
            db.grant(1,2,kind)
            db.deploy(2,99+index,'TestBot',123,'a'*32,'private-token','private-session',kind=kind)
            db.setting(99+index,2,'welcome','Pesan milik pengguna') if index==0 else None
            with db.conn: db.conn.execute('INSERT INTO jobs(id,bot,chat,message_id,due) VALUES (1,?,?,?,1)',(99+index,2,10+index))
            if index==0:
                with db.conn: db.conn.execute("INSERT INTO links VALUES (99,'lama','[]')")
            else:
                pay=PaymentStore(db);pay.account(2,'test','recipient','private-key',True)
                pkg=pay.save_package(100,2,name='Akses',description='Test',price=1000,target=-1001)
                order=pay.new_order(100,3,pkg);self.order=order['id']
                pay.attach(self.order,'tx-test','QR-PRIVATE',1000)
                with db.conn:db.conn.execute('UPDATE payment_orders SET invite=? WHERE id=?',(pay.seal('PRIVATE-INVITE'),self.order))
            db.close()

    def tearDown(self): self.tmp.cleanup()

    def test_preserves_data_reencrypts_secrets_and_retries_without_duplication(self):
        before=[(p/'subgate.sqlite').read_bytes() for p in self.folders]
        result=merge(*self.folders,self.root/'output')
        self.assertEqual((result['bots'],result['payment_orders']),(2,1))
        db=Store(self.root/'output/data/subgate.sqlite',self.keys[0],1)
        try:
            self.assertEqual(db.credentials(100)['session'],'private-session')
            self.assertEqual(db.settings(99)['welcome'],'Pesan milik pengguna')
            self.assertEqual(db.rows('SELECT key FROM links')[0]['key'],'lama')
            self.assertEqual(len(db.rows('SELECT * FROM jobs')),2)
            self.assertTrue(db.allowed(2,'forcesubs'));self.assertTrue(db.allowed(2,'payment'))
            pay=PaymentStore(db)
            self.assertEqual(pay.account(2)['key'],'private-key')
            self.assertEqual(pay.order(100,self.order)['qr'],'QR-PRIVATE')
            self.assertEqual(pay.order(100,self.order)['invite'],'PRIVATE-INVITE')
        finally:db.close()
        self.assertEqual(result,merge(*self.folders,self.root/'output'))
        self.assertEqual(before,[(p/'subgate.sqlite').read_bytes() for p in self.folders])

    def test_same_owner_reused_bot_keeps_old_links_and_payment_history(self):
        db=Store(self.folders[0]/'subgate.sqlite',self.keys[0],1)
        db.deploy(2,100,'TestBot',123,'a'*32,'old-token','old-session')
        db.setting(100,2,'welcome','ForceSubs semula')
        with db.conn:db.conn.execute("INSERT INTO links VALUES (100,'old-file','[]')")
        db.close()
        result=merge(*self.folders,self.root/'output')
        self.assertEqual(result['bots'],2)
        db=Store(self.root/'output/data/subgate.sqlite',self.keys[0],1)
        try:
            self.assertEqual(db.bot(100)['kind'],'payment')
            self.assertTrue(db.settings(100)['legacy_forcesubs'])
            self.assertEqual(db.settings(100)['welcome'],'ForceSubs semula')
            self.assertEqual(db.rows("SELECT key FROM links WHERE bot=100")[0]['key'],'old-file')
            self.assertEqual(PaymentStore(db).order(100,self.order)['qr'],'QR-PRIVATE')
        finally:db.close()

    def test_overlapping_admins_do_not_gain_other_service_privileges(self):
        import asyncio
        from subgate.service import Delivery
        from test_service import FakeAPI
        db=Store(self.folders[0]/'subgate.sqlite',self.keys[0],1)
        db.deploy(2,100,'TestBot',123,'a'*32,'old-token','old-session')
        with db.conn:
            db.conn.execute('INSERT INTO admins VALUES (100,7)')
            db.conn.execute("INSERT INTO targets(bot,chat,kind,url,title) VALUES (100,-1005,'channel','https://t.me/old','Lama')")
        db.close()
        db=Store(self.folders[1]/'subgate.sqlite',self.keys[1],1)
        with db.conn:db.conn.execute('INSERT INTO admins VALUES (100,8)')
        db.close()
        merge(*self.folders,self.root/'output')
        db=Store(self.root/'output/data/subgate.sqlite',self.keys[0],1)
        try:
            self.assertEqual(db.admins(100),[8])
            with self.assertRaises(PermissionError):PaymentStore(db).staff(100,7)
            PaymentStore(db).staff(100,8)
            api=FakeAPI();api.members[(-1005,100)]='administrator';api.members[(-1005,8)]='left'
            delivery=Delivery(db,100,api)
            self.assertEqual(asyncio.run(delivery.missing(7)),[])
            self.assertEqual(len(asyncio.run(delivery.missing(8))),1)
        finally:db.close()

    def test_failed_publication_leaves_no_runnable_target_and_can_retry(self):
        from unittest.mock import patch
        real=Path.write_text
        def fail_receipt(path,*args,**kwargs):
            if path.name=='migration.json':raise OSError('simulated disk failure')
            return real(path,*args,**kwargs)
        with patch.object(Path,'write_text',fail_receipt):
            with self.assertRaises(OSError):merge(*self.folders,self.root/'output')
        self.assertFalse((self.root/'output/config.env').exists())
        self.assertFalse((self.root/'output/data/subgate.sqlite').exists())
        self.assertEqual(merge(*self.folders,self.root/'output')['bots'],2)

    def test_rejects_different_master_without_writing_destination(self):
        p=self.folders[1]/'config.env';p.write_text(p.read_text().replace('MASTER_OWNER_ID=1','MASTER_OWNER_ID=3'))
        with self.assertRaises(ValueError):merge(*self.folders,self.root/'output')
        self.assertFalse((self.root/'output/data/subgate.sqlite').exists())

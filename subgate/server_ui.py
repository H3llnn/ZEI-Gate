"""Owner-only server menus and placement, using the existing conversation UI."""
from .copy import button, h, panel, nav


class ServerUI:
    async def migration_status(self, user, target):
        self.servers_service(user)
        service = getattr(self.manager,'migrations',None)
        job = service.latest(target) if service else None
        if not job:
            raise ValueError('Pengguna belum memiliki proses migrasi.')
        labels = {'export':'Menyimpan dan mengirim data sumber', 'import':'Memeriksa dan memasang data tujuan',
                  'verify':'Menunggu layanan aktif di tujuan', 'cleanup':'Merapikan salinan sumber', 'done':'Migrasi selesai ✅'}
        name = lambda server: self.manager.servers.get(server)['name'] if server else 'Server Utama'
        body = (f'<b>Pengguna:</b> {h(await self.user_name(target))}\n'
                f'<b>Dari:</b> {h(name(job["source"]))}\n<b>Ke:</b> {h(name(job["target"]))}\n'
                f'<b>Status:</b> {h(labels[job["phase"]])}\n\n'
                'Pengaturan, link, transaksi, serta sesi dan catatan Userbot ikut dipindahkan. Cadangan privat tetap disimpan.')
        if job['error']:
            body += '\n\n🔧 Proses menunggu perbaikan koneksi atau data server dan akan mencoba lagi otomatis. Data sumber tetap dicadangkan.'
        await self.text(user,panel('Migrasi layanan 🚚',body),
            [[button('↻ Perbarui Status',f'srv:migration:{target}')], [button('‹ Detail Pengguna',f'm:user:{target}')]])

    async def grant_server_choices(self, user, target, page=0):
        service = self.servers_service(user)
        state = self.state(user)
        if not state or state['kind'] != 'grant_server' or state['target'] != target:
            raise ValueError('Pilihan server berakhir. Tambahkan pengguna kembali.')
        rows = service.all()
        page = max(0,min(page,max(0,(len(rows)-1)//8)))
        buttons = [[button('🖥️ Server Utama',f'srv:grant:{target}:0')]]
        for row in rows[page*8:(page+1)*8]:
            if service.online(row):
                buttons.append([button('🟢 '+row['name'],f'srv:grant:{target}:{row["id"]}')])
        pages = []
        if page:
            pages.append(button('‹ Sebelumnya',f'srv:grant_page:{target}:{page-1}'))
        if (page+1)*8 < len(rows):
            pages.append(button('Berikutnya ›',f'srv:grant_page:{target}:{page+1}'))
        if pages:
            buttons.append(pages)
        buttons.append([button('✕ Batal','x:cancel')])
        return await self.text(user,panel('Tempatkan pengguna 🖥️',
            f'<b>Pengguna:</b> {h(await self.user_name(target))}\n<b>Layanan:</b> {h(state["bot_kind"])}\n\n'
            'Pilih server untuk menjalankan layanan pengguna ini. Izin diberikan setelah server dipilih.'),buttons)

    def servers_service(self, user):
        self.db.master(user)
        service = getattr(self.manager, 'servers', None)
        if service is None:
            raise ValueError('Pengelolaan server belum tersedia.')
        return service

    async def servers_menu(self, user, page=0):
        service = self.servers_service(user)
        self.clear(user)
        rows = service.all()
        page = max(0,min(page,max(0,(len(rows)-1)//8)))
        buttons = [[button('＋ Tambah Server','srv:add')]]
        for row in rows[page*8:(page+1)*8]:
            label = '🟢' if service.online(row) else '⚫'
            buttons.append([button(f'{label} {row["name"]}',f'srv:detail:{row["id"]}')])
        pages = []
        if page:
            pages.append(button('‹ Sebelumnya',f'srv:list:{page-1}'))
        if (page+1)*8 < len(rows):
            pages.append(button('Berikutnya ›',f'srv:list:{page+1}'))
        if pages:
            buttons.append(pages)
        buttons.append([button('⌂ Menu Utama','m:menu')])
        await self.text(user,panel('Kelola Server 🖥️',f'<b>Server terdaftar:</b> {len(rows)}\n\nPilih server untuk melihat koneksi dan bot yang berjalan.'),buttons)

    async def server_detail(self, user, server):
        service = self.servers_service(user)
        row = service.get(server)
        rows = [r for r in self.db.bots() if service.assigned(r['owner']) == server]
        active = sum(service.running(r['id']) for r in rows)
        accounts = [r for r in self.db.rows('SELECT owner FROM userbots') if service.assigned(r['owner']) == server]
        account_active = sum(service.account_running(r['owner']) for r in accounts)
        buttons = [[button('↻ Perbarui',f'srv:detail:{server}')]]
        if not row['token_hash']:
            buttons.append([button('🔑 Buat Kode Baru',f'srv:code:{server}')])
        buttons.append([button('‹ Kelola Server','srv:list:0')])
        await self.text(user,panel('Server milikmu 🖥️',f'<b>Nama:</b> {h(row["name"])}\n'
            f'<b>Koneksi:</b> {"🟢 Terhubung" if service.online(row) else "⚫ Belum terhubung"}\n'
            f'<b>Bot aktif:</b> {active} / {len(rows)}\n<b>Userbot aktif:</b> {account_active} / {len(accounts)}\n\nPilih server untuk klien melalui Daftar Pengguna → Server.'),buttons)

    async def server_code(self, user, server, code):
        service = self.servers_service(user)
        creation = getattr(self.manager,'creation',None)
        origin = creation.public_base if creation else ''
        await self.text(user,panel('Hubungkan servermu 🔑',f'<b>{h(service.get(server)["name"])}</b>\n\n'
            'Unduh pemasang melalui tombol di bawah, lalu unggah <code>install_worker.py</code> ke server Python 3.12 atau lebih baru.\n'
            'Simpan konfigurasi berikut sebagai <code>config.env</code>, atur file startup ke <code>install_worker.py</code>, lalu tekan Start.\n\n'
            f'<pre>ZEI_MODE=worker\nWORKER_GATE_URL={h(origin)}\nWORKER_ENROLL_CODE={h(code)}\nDATA_DIR=./data</pre>\n'
            'Kode berlaku 10 menit untuk satu pemasangan. Setelah terhubung, pilih server ini pada detail pengguna.\n'
            'Pemasang mengambil runtime yang cocok secara otomatis. Simpan kode secara pribadi.'),
                                        [[{'text':'⬇️ Unduh Pemasang Worker','url':'https://raw.githubusercontent.com/H3llnn/ZEI-Gate/main/install_worker.py'}],
                                         [button('↻ Periksa Koneksi',f'srv:detail:{server}')],
                                         [button('‹ Kelola Server','srv:list:0')]])

    async def server_choices(self, user, target, page=0):
        service = self.servers_service(user)
        rows = service.all()
        page = max(0,min(page,max(0,(len(rows)-1)//8)))
        current = service.assigned(target)
        buttons = [[button(('✅ ' if current is None else '')+'Server Utama',f'srv:place:{target}:0')]]
        for row in rows[page*8:(page+1)*8]:
            status = '🟢' if service.online(row) else '⚫'
            buttons.append([button(('✅ ' if current==row['id'] else '')+f'{status} {row["name"]}',f'srv:place:{target}:{row["id"]}')])
        pages=[]
        if page:
            pages.append(button('‹ Sebelumnya',f'srv:choose:{target}:{page-1}'))
        if (page+1)*8 < len(rows):
            pages.append(button('Berikutnya ›',f'srv:choose:{target}:{page+1}'))
        if pages:
            buttons.append(pages)
        buttons.append([button('‹ Detail Pengguna',f'm:user:{target}')])
        await self.text(user,panel('Pilih Server 🖥️',f'<b>Pengguna:</b> {h(await self.user_name(target))}\n\n'
            'ForceSubs, Payment, dan Userbot baru akan dijalankan pada server pilihanmu.\n'
            'Jika sudah ada layanan, pemindahan akan memakai migrasi data dengan cadangan dan pemeriksaan otomatis.'),buttons)

    async def server_callback(self, user, data):
        service = self.servers_service(user)
        parts = data.split(':')
        if parts[1]=='migration':
            return await self.migration_status(user,int(parts[2]))
        if parts[1]=='migrate':
            target,server=int(parts[2]),int(parts[3]) or None
            state=self.state(user)
            if not state or state['kind']!='migration_confirm' or state['target']!=target or state['server']!=server:
                raise ValueError('Konfirmasi berakhir. Pilih server kembali.')
            async with self.manager.lock:
                if service.assigned(target)!=state['source']:
                    raise ValueError('Penempatan berubah. Pilih server kembali.')
                self.manager.migrations.begin(user,target,server)
            self.clear(user)
            return await self.migration_status(user,target)
        if parts[1]=='grant_page':
            return await self.grant_server_choices(user,int(parts[2]),int(parts[3]))
        if parts[1]=='grant':
            target,server=int(parts[2]),int(parts[3]) or None
            state=self.state(user)
            if not state or state['kind']!='grant_server' or state['target']!=target:
                raise ValueError('Pilihan server berakhir. Tambahkan pengguna kembali.')
            async with self.manager.lock:
                with self.db.conn:
                    service.place(user,target,server)
                    self.db.grant(user,target,state['bot_kind'],preserve=True)
            self.clear(user)
            return await self.user_detail(user,target)
        if parts[1]=='list':
            return await self.servers_menu(user,int(parts[2]))
        if parts[1]=='add':
            creation = getattr(self.manager,'creation',None)
            if not creation or not creation.public_base:
                raise ValueError('Aktifkan HTTPS Mini App Gate untuk menghubungkan server.')
            self.wait(user,'server_name',back='srv:list:0')
            return await self.text(user,panel('Tambah Server 🖥️','Kirim nama server, misalnya <b>Server Klien 1</b>.'),nav('srv:list:0'))
        if parts[1]=='detail':
            return await self.server_detail(user,int(parts[2]))
        if parts[1]=='code':
            server=int(parts[2])
            return await self.server_code(user,server,service.renew(user,server))
        if parts[1]=='choose':
            return await self.server_choices(user,int(parts[2]),int(parts[3]))
        if parts[1]=='place':
            target,server=int(parts[2]),int(parts[3]) or None
            migrations=getattr(self.manager,'migrations',None)
            job=migrations.latest(target) if migrations else None
            if job and job['phase']!='done':
                return await self.migration_status(user,target)
            if service.assigned(target)!=server and (self.db.bots(target) or self.db.rows('SELECT owner FROM userbots WHERE owner=?',(target,))):
                if not migrations:
                    raise ValueError('Perbarui Gate untuk mengaktifkan migrasi.')
                source=service.assigned(target)
                name=lambda value:service.get(value)['name'] if value else 'Server Utama'
                self.wait(user,'migration_confirm',target=target,server=server,source=source,back=f'srv:choose:{target}:0')
                return await self.text(user,panel('Pindahkan layanan? 🚚',
                    f'<b>Pengguna:</b> {h(await self.user_name(target))}\n<b>Dari:</b> {h(name(source))}\n<b>Ke:</b> {h(name(server))}\n'
                    f'<b>Bot:</b> {len(self.db.bots(target))}\n\nLayanan berhenti sementara saat data disalin. Tujuan diperiksa sebelum diaktifkan. Cadangan tetap disimpan.'),
                    [[button('🚚 Mulai Migrasi',f'srv:migrate:{target}:{server or 0}')],[button('✕ Batal',f'm:user:{target}')]])
            async with self.manager.lock:
                service.place(user,target,server)
            return await self.user_detail(user,target)
        raise ValueError('Buka menu server terbaru.')

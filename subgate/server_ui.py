"""Owner-only server menus and placement, using the existing conversation UI."""
from .copy import button, h, panel, nav


class ServerUI:
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
        buttons = [[button('↻ Perbarui',f'srv:detail:{server}')]]
        if not row['token_hash']:
            buttons.append([button('🔑 Buat Kode Baru',f'srv:code:{server}')])
        buttons.append([button('‹ Kelola Server','srv:list:0')])
        await self.text(user,panel('Server milikmu 🖥️',f'<b>Nama:</b> {h(row["name"])}\n'
            f'<b>Koneksi:</b> {"🟢 Terhubung" if service.online(row) else "⚫ Belum terhubung"}\n'
            f'<b>Bot aktif:</b> {active} / {len(rows)}\n\nPilih server untuk klien melalui Daftar Pengguna → Server.'),buttons)

    async def server_code(self, user, server, code):
        service = self.servers_service(user)
        creation = getattr(self.manager,'creation',None)
        origin = creation.public_base if creation else ''
        await self.text(user,panel('Hubungkan servermu 🔑',f'<b>{h(service.get(server)["name"])}</b>\n\n'
            'Salin konfigurasi berikut ke <code>config.env</code> server klien, lalu jalankan paket ZΞI Worker.\n\n'
            f'<pre>ZEI_MODE=worker\nWORKER_GATE_URL={h(origin)}\nWORKER_ENROLL_CODE={h(code)}\nDATA_DIR=./data</pre>\n'
            'Kode berlaku 10 menit untuk satu pemasangan. Setelah terhubung, pilih server ini pada detail pengguna.\n'
            'Simpan kode secara pribadi.'),[[button('↻ Periksa Koneksi',f'srv:detail:{server}')],
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
            'Bot ForceSubs dan Payment baru akan dijalankan pada server pilihanmu. Userbot memakai server utama.\n'
            'Pengguna yang sudah memiliki bot perlu migrasi data sebelum pindah server.'),buttons)

    async def server_callback(self, user, data):
        service = self.servers_service(user)
        parts = data.split(':')
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
            async with self.manager.lock:
                service.place(user,target,server)
            return await self.user_detail(user,target)
        raise ValueError('Buka menu server terbaru.')

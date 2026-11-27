# Migrasi melalui bot induk

Buka **Daftar Pengguna → nama pengguna → Server → tujuan → Mulai Migrasi**.
Pemilik bot induk saja yang dapat memulai dan melihat status migrasi. Pengguna
tanpa layanan tetap memakai pemilihan server biasa.

Gate dan kedua Worker harus memakai versi yang mendukung protokol migrasi 1.
Worker lama atau offline ditolak sebelum layanan sumber dihentikan. Server baru
yang memakai `install_worker.py` terbaru mendapatkan dukungan ini otomatis.

Tahap yang tersimpan adalah `export`, `import`, `verify`, `cleanup`, `done`.
Layanan sumber dihentikan sebelum snapshot dibuat, termasuk proses Userbot dan
pekerjaan penghapusan terjadwal. Tujuan baru diaktifkan setelah checksum, jumlah
baris, dan integritas SQLite cocok. Penempatan beralih setelah receipt tujuan
tersimpan; sumber dibersihkan setelah tujuan mengonfirmasi aktivasi dan layanan
yang semula aktif kembali berjalan. Layanan yang semula berhenti tetap berhenti.
Izin, deploy, toggle, dan prefix dikunci selama migrasi.

Data mencakup pengaturan, admin, channel/database, link, pengguna, pekerjaan
terjadwal, katalog akses, pesanan, QR, undangan, akun pembayaran, serta sesi,
prefix dan catatan Userbot. Kredensial dienkripsi ulang memakai key tujuan;
`SECRET_KEY` Gate tidak dibagikan. Snapshot dan potongan disimpan terenkripsi,
dikirim melalui HTTPS dengan identitas Worker, maksimal 4.500 byte per potongan
dan 64 MiB per snapshot. Bila ID katalog Payment berbenturan, hanya ID katalog
yang diimpor dan rujukan pesanannya dipetakan ulang; menu katalog lama perlu
dibuka ulang. Link ForceSubs dan ID pesanan tetap sama.

Tekan **Status Migrasi → Perbarui Status** untuk melihat tahap terakhir.
Koneksi putus atau restart melanjutkan tahap yang sama secara otomatis. Pesan
gangguan tidak menyertakan token atau data pembayaran. Jangan menjalankan
salinan sumber secara manual ketika tujuan sudah aktif.

## Cadangan dan pemulihan

Setiap node menyimpan cadangan privat di
`DATA_DIR/migration-backups/<id-migrasi>/`. Isinya SQLite konsisten, konfigurasi
atau identitas Worker yang tersedia, dan settings Userbot. Cadangan tidak
dihapus otomatis. Simpan key asli; DB terenkripsi memerlukan key node asal.

Jika ada kegagalan, perbaiki koneksi atau perbarui skema kedua node lalu biarkan
retry berjalan. Jika diperlukan rollback manual sebelum `verify`, hentikan
Gate dan kedua Worker, pulihkan hanya baris pengguna serta settings dari cadangan
di sumber dan tujuan, lalu pulihkan penempatan di DB Gate ke sumber. Bersihkan
checkpoint job itu dari `migration_chunks` sebelum `migrations`, dan hold/cache/
receipt/download lokal yang memakai ID job itu. Jangan menimpa seluruh DB bila
layanan pengguna lain sudah menerima data setelah backup dibuat. Pastikan tujuan
tetap berhenti sebelum sumber dijalankan. Setelah `verify`, transaksi baru mungkin
sudah masuk di tujuan: gunakan migrasi balik agar data baru ikut terbawa;
jangan menimpa tujuan dengan backup lama. Restore backup merupakan operasi
pemulihan operator, bukan tombol pembatalan selama layanan sudah aktif.

Payment dengan webhook eksternal membutuhkan penyesuaian URL routing oleh
operator saat server berubah. Alur QRIS dengan pemeriksaan langsung tidak
memerlukan perubahan URL pembeli.

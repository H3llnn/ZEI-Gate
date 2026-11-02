# ZΞI Project — versi 0.1.1

## Pemeriksaan perangkat lunak

- 134 tes Gate dan 5 tes Userbot lulus pada instalasi Python 3.13 di Windows.
- Pemasangan dependensi dan pip check berhasil pada lingkungan baru.
- Migrasi diuji dengan kunci enkripsi berbeda, pengaturan/link/pesanan tersimpan, percobaan ulang tanpa duplikasi, serta kegagalan penulisan hasil.
- Peninjauan kode menemukan dan memperbaiki pemisahan peran admin saat bot berganti layanan dan publikasi migrasi yang harus atomik. Tes kedua masalah gagal sebelum perbaikan dan lulus sesudahnya.
- Bot Payment hasil migrasi tetap melayani link ForceSubs lama beserta syarat join dan penghapusan otomatis. Bot Payment biasa tidak mengaktifkan kompatibilitas tersebut.
- README utama memakai branding ZΞI. Lisensi dan referensi tetap tersedia pada berkas atribusi.

## Batas pemeriksaan

Aktivasi akun, OTP/2FA, mode inline Telegram dan uji transaksi nyata ditunda atas permintaan pemilik.
Tidak ada poller bot induk/anak yang dijalankan untuk pengujian ini. HTTPS tetap diperlukan saat formulir akan diaktifkan.
38 perintah Userbot tersedia; daftar fitur tambahan di inventaris referensi belum seluruhnya diimplementasikan.
Paket distribusi publik tidak berisi konfigurasi pribadi, database pengguna, sesi akun, atau cadangan lokal.

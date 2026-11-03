# ZΞI Project — status pemeriksaan

Diperbarui 3 November 2026.

## Pemeriksaan perangkat lunak

- 155 tes Gate lulus pada pemeriksaan 3 November 2026 di Windows. Lima tes Userbot juga lulus pada pemeriksaan pemisahan runtime.
- Pemasangan dependensi dan pip check berhasil pada lingkungan baru.
- Migrasi diuji dengan kunci enkripsi berbeda, pengaturan/link/pesanan tersimpan, percobaan ulang tanpa duplikasi, serta kegagalan penulisan hasil.
- Peninjauan kode menemukan dan memperbaiki pemisahan peran admin saat bot berganti layanan dan publikasi migrasi yang harus atomik. Tes kedua masalah gagal sebelum perbaikan dan lulus sesudahnya.
- Bot Payment hasil migrasi tetap melayani link ForceSubs lama beserta syarat join dan penghapusan otomatis. Bot Payment biasa tidak mengaktifkan kompatibilitas tersebut.
- README utama memakai branding ZΞI. Lisensi dan referensi tetap tersedia pada berkas atribusi.

## Batas pemeriksaan

Bot induk dan alamat HTTPS Mini App telah dipasang pada hosting. Mode inline bot induk telah terverifikasi aktif. Pemeriksaan penerapan tidak menggantikan uji pembayaran, bergabung, login OTP/2FA, dan penggunaan tombol bantuan secara langsung pada versi terbaru. Tes otomatis tidak menjalankan transaksi atau login akun nyata. HTTPS tetap diperlukan untuk Mini App.
38 perintah Userbot tersedia; daftar fitur tambahan di inventaris referensi belum seluruhnya diimplementasikan.
Paket distribusi publik tidak berisi konfigurasi pribadi, database pengguna, sesi akun, atau cadangan lokal.

## Pemisahan runtime

ForceSubs dan Payment diekstrak menjadi paket Python terpisah. Suite 155 tes mencakup identitas modul kompatibilitas dan kelas exception. Skema data dan konfigurasi tidak diubah. Penerapan hosting versi empat repo belum dilakukan.

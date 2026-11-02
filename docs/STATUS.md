# Status implementasi · 2 November 2026

- Fondasi Gate + Mini App + runtime Userbot dibuat di source terpisah, bukan dipasang ke bot yang sedang berjalan.
- 127 tes Gate termasuk 110 regresi sebelumnya dan 17 tes baru login/izin/HTTP; 5 tes runtime Userbot lulus pada pemeriksaan lokal.
- Alur UI seluler choose → API → nomor → OTP → 2FA → ringkasan → sukses diperiksa dengan server simulasi lokal. Data login simulasi bukan akun nyata. JavaScript lolos pemeriksaan sintaks Node.
- 38 perintah tersedia; tidak seluruh modul Man-Userbot. Lihat MODULES.md repo Userbot untuk batas porting.
- Belum diuji: login Telegram nyata, QRIS nyata ulang setelah perubahan ini, hak admin grup nyata, inline mode pada bot milik pengguna, deployment Docker/VPS dan HTTPS domain nyata.
- Source disiapkan untuk repo H3llnn/ZEI-Gate dan H3llnn/ZEI-Userbot. Publikasi source tidak berarti bot produksi sudah diperbarui. Workflow Gate menguji pemasangan runtime dari repo Userbot.
- Migrasi bersifat penambahan tabel/perizinan, tidak menghapus konten/pesanan. Rollback: hentikan proses, pulihkan backup config/data sebelum pembaruan; jangan mengganti SECRET_KEY.

# Update dan cadangan

## Sebelum memperbarui

1. Catat versi sumber yang sedang dipakai dan lokasi `DATA_DIR`.
2. Hentikan proses bot induk dan layanan terkait agar database tidak berubah saat disalin.
3. Salin `config.env` serta seluruh folder `DATA_DIR` ke lokasi cadangan pribadi.
4. Simpan juga sumber versi lama. Pastikan cadangan dapat dibaca sebelum melanjutkan.

`SECRET_KEY` harus sesuai dengan data terenkripsi. Kehilangan kunci dapat membuat sesi dan kredensial lama tidak bisa dibaca.

## Memasang sumber baru

Ganti berkas sumber aplikasi dengan versi baru. Pertahankan konfigurasi pribadi, `SECRET_KEY`, dan lokasi data lama. Jangan menyalin `sample_config.env` di atas konfigurasi aktif.

Ikuti catatan pembaruan versi yang dituju, pasang dependensi yang dibutuhkan, lalu jalankan kembali dengan cara yang sesuai pemasanganmu: `RUN.cmd` untuk pemasangan Windows, atau startup hosting yang sudah dikonfigurasi.

Untuk Docker, pertahankan nama proyek Compose dan volume data yang dipakai sebelumnya. Jangan gunakan `docker compose down -v` untuk pembaruan; opsi tersebut menghapus volume.

## Periksa setelah menyala

- Bot induk merespons `/start` dan izin pengguna masih sesuai.
- Mini App terbuka melalui tombol Telegram.
- Layanan anak yang diperlukan berjalan dan pengaturan lamanya tersedia.
- Link konten, bantuan Userbot, dan alur pembayaran diperiksa sesuai layanan yang kamu gunakan.

Uji transaksi nyata secara terkontrol sebelum membuka penjualan. Tes otomatis tidak melakukan pembayaran nyata.

## Jika perlu kembali ke versi lama

Hentikan seluruh proses, lalu pulihkan sumber, konfigurasi, dan data dari satu cadangan yang konsisten. Jangan memasangkan database terbaru dengan sumber lama tanpa memeriksa kompatibilitas skemanya.

Pemulihan cadangan mengembalikan data ke waktu cadangan dibuat. Rekonsiliasi transaksi yang terjadi setelah waktu tersebut sebelum membuka layanan kembali.

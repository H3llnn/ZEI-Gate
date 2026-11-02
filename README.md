# ZΞI Gate

**ZΞI Project · Maintained by Zeisss**

Satu bot induk untuk bot ForceSubs, bot Payment, dan akun Userbot milik pengguna yang diizinkan. Nama bot anak mengikuti akun bot Telegram masing-masing. Pengaturan dan transaksi tetap di Telegram; halaman web khusus proses pembuatan/koneksi ulang.

## Yang tersedia

- Izin per layanan atau kombinasi ketiganya; hanya pemilik bot induk yang mengatur izin.
- Formulir Mini App tema gelap/ungu: API ID + Hash setiap deploy, verifikasi token bot, atau nomor → OTP → 2FA → ringkasan untuk Userbot.
- Identitas pembuka divalidasi dengan tanda tangan Telegram. Akun Userbot harus sama dengan ID pembuka; satu akun per pengguna.
- Sesi akun tersimpan terenkripsi dengan SECRET_KEY Gate. OTP dan password 2FA tidak disimpan dalam database; data formulir sementara dibersihkan saat batal/kedaluwarsa.
- Sesi formulir berakhir setelah 10 menit tidak aktif. Minimize tidak membatalkan. Menutup aplikasi bukan sinyal yang dapat diandalkan; pembersihan memakai timeout atau tombol Batalkan.
- Koneksi ulang mempertahankan proses lama sampai pengganti terverifikasi dan siap. Pengaturan tetap tersimpan.
- Cabut izin menghentikan layanan terkait. Beri izin kembali mengharuskan deploy/koneksi ulang, bukan otomatis hidup lagi.
- .help Userbot hanya menerima perintah dari akun pemilik, dengan prefix yang bisa diganti. Mode inline bot induk mengaktifkan kategori bertombol; bantuan teks tetap tersedia sebagai cadangan.
- ForceSubs dan Payment beserta pengaturan, link, pesanan, dan jadwal lama tetap dipertahankan. [Panduan fitur sebelumnya](docs/SUBGATE-LEGACY.md).

## Jalankan di laptop

Letakkan dua folder berdampingan:

`	ext
ZEI-Project/
  ZEI-Gate/
  ZEI-Userbot/
`

Di terminal folder ZEI-Gate:

````powershell
python install.py
```
`

Untuk instalasi baru, salin sample_config.env menjadi config.env dan isi token bot induk, ID pemilik, SECRET_KEY. Buat kunci dengan .venv\Scripts\python.exe -m subgate.keygen.

Untuk pembaruan, cadangkan config.env dan seluruh folder data ketika bot berhenti. **Pertahankan SECRET_KEY dan DATA_DIR lama.** Jangan menimpa keduanya dengan contoh kosong. Jalankan RUN.cmd setelah konfigurasi siap.

## Aktifkan formulir pembuatan

````ini
CREATION_ENABLE=1
CREATION_PUBLIC_BASE=https://domain-milikmu.example
CREATION_BIND=127.0.0.1
CREATION_PORT=8081
`

Domain HTTPS diarahkan melalui reverse proxy ke port 8081. Ini untuk Mini App, bukan kebutuhan webhook Payment. Pembayaran sederhana tetap tidak membutuhkan tunnel. Untuk uji laptop sementara dapat memakai tunnel ke port **8081**; jika alamat berubah, perbarui konfigurasi dan restart. Jangan menggunakan alamat tunnel lama yang sudah berhenti.

Bot induk menampilkan tombol Buka Ruang Pembuatan ketika alamat tersebut diaktifkan. Pembuka wajib dari tombol Telegram; membuka URL biasa tidak memberi akses. Atur inline mode melalui BotFather /setinline untuk bot induk agar .help dapat menampilkan tombol. Login akun dan kode OTP dilakukan sendiri oleh pemilik melalui formulir.

## Docker / VPS

Jalankan docker compose up -d --build di ZEI-Gate di folder ZEI-Gate. Image memasang runtime Userbot dari commit yang dipin; build context hanya folder Gate. Port host hanya terikat localhost. Pasang HTTPS reverse proxy di depan port 8081. Pada pembaruan Docker, pertahankan nama proyek Compose lama dengan opsi -p agar volume subgate-data lama tetap digunakan; jangan menjalankan down -v. Cadangkan volume data dan SECRET_KEY bersama-sama; kehilangan kunci membuat sesi lama tidak dapat dibaca.

Proses Userbot terpisah per akun, tanpa shell/eval dan tanpa modul pihak ketiga yang dimuat otomatis. Pemisahan proses bukan sandbox OS; pengelola server tetap memiliki akses ke penyimpanan. Jalankan hanya di server yang kamu percaya.

## Pengujian

````powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```
`

Tes lokal memakai Telegram dan pembayaran tiruan, tidak membuat pembayaran nyata atau login akun pengguna. Hasil dan batas pemeriksaan terdapat pada [status rilis](docs/STATUS.md).

## Lisensi

GPL-3.0. Nama produk baru tidak menghapus hak cipta kode terdahulu. Lihat LICENSE dan THIRD_PARTY_NOTICES.md. Referensi kebutuhan Man-Userbot dicatat pada repo ZEI-Userbot; kesetaraan semua modul belum dinyatakan selesai.

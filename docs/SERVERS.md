# Server klien melalui bot induk

Owner bot induk dapat menambahkan server dan memilih tempat menjalankan bot ForceSubs, Payment, dan akun Userbot baru.

## Menghubungkan server

1. Pasang versi Gate yang mendukung menu Kelola Server. Aktifkan HTTPS Mini App Gate.
2. Buka bot induk → Kelola Server → Tambah Server. Kirim nama server.
3. Bot memberikan konfigurasi dengan kode pemasangan. Kode berlaku 10 menit dan hanya bisa dipakai satu pemasangan. Kode baru dapat dibuat selama server belum pernah dipasangkan.
4. Unggah paket Worker ke server klien. Pada hosting Python pilih Python 3.12, startup `main.py`, dan `requirements.txt`.
5. Simpan konfigurasi dari bot sebagai `config.env` pada server klien, lalu jalankan. Tidak perlu menyalin token bot induk atau SECRET_KEY Gate ke server klien.
6. Tekan Periksa Koneksi. Setelah terhubung, buka Daftar Pengguna → nama klien → Server → pilih server tersebut.
7. Atur izin layanan melalui tombol izin yang sudah ada. Klien membuat bot atau menghubungkan Userbot melalui ruang pembuatan. Login nomor, OTP, dan 2FA dilakukan pada Mini App Gate. Sesi akun dikirim melalui HTTPS ke server pilihan klien dan disimpan terenkripsi. Gate menunggu laporan akun aktif sebelum menampilkan hasil berhasil.

Setiap server menghubungi endpoint `/servers/enroll` dan `/servers/sync` pada origin HTTPS Gate. Reverse proxy harus meneruskan kedua path tersebut ke proses Gate yang sama dengan Mini App. Server klien cukup memiliki koneksi keluar HTTPS. Akses endpoint memerlukan kode sekali pakai atau token server yang terikat ke identitas server.

## Izin, koneksi, dan status

Sinkronisasi berlangsung sekitar lima detik sekali, di luar waktu penerapan snapshot. Pembuatan bot menunggu laporan aktif dari server selama maksimal 25 detik. Bila konfirmasi belum diterima, Gate menandai bot berhenti dan pengguna dapat mencoba deploy lagi setelah koneksi pulih.

Pencabutan izin mengubah status yang dikehendaki pada Gate. Server menerimanya pada sinkronisasi berikutnya, menghentikan bot terkait dan membatalkan pesanan yang belum dibayar. Beri izin kembali, lalu deploy ulang untuk mengaktifkannya kembali.

Saat koneksi terputus, server menggunakan izin terakhir hingga 120 detik sejak permintaan sinkronisasi terakhir yang berhasil. Sesudah masa itu, permintaan Telegram baru diblokir dan proses bot dihentikan. Permintaan jaringan yang sudah dikirim bisa selesai selama batas waktu transportnya. Status Terhubung memakai heartbeat 20 detik terakhir dan bukan jaminan setiap bot sehat.

Gate tidak menjalankan salinan lokal bot yang ditempatkan di server klien. Kegagalan server klien tidak memindahkan bot secara otomatis. Worker yang restart menunggu snapshot Gate baru sebelum mengaktifkan kembali bot.

## Data dan pemindahan

Gate menyimpan izin, penempatan pengguna, metadata bot, dan kredensial deployment terenkripsi. Data operasional bot anak, seperti pengaturan, link konten, pesanan, serta undangan berada di database server klien. Tiap server memiliki kunci penyimpanan sendiri dalam `DATA_DIR/worker-identity.json`. Cadangkan seluruh DATA_DIR server klien dan konfigurasi bersama-sama secara privat.

Pengguna yang sudah memiliki bot atau Userbot tidak dapat dipindahkan melalui tombol Server. Ini mencegah hilangnya link, transaksi, prefix, dan catatan akibat menjalankan database kosong di server tujuan. Migrasi instalasi lama memerlukan pemindahan data secara terpisah.

Prefix dapat diubah melalui akun sendiri atau menu bot induk. Menu bot induk menunggu konfirmasi penerapan dari server. Bantuan inline `.help` menggunakan laporan prefix dan status akun pada server. Perubahan prefix dari akun sendiri muncul setelah sinkronisasi berikutnya. Notifikasi pencabutan Userbot mengikuti alur yang tersedia pada Gate.

Saat izin Userbot dicabut, server menutup proses akun terkait. Pemberian izin kembali memerlukan login ulang melalui Mini App. Saat lease koneksi habis, Worker menutup akun Userbot beserta prosesnya. Penutupan proses memiliki batas tunggu 10 detik sebelum dihentikan paksa.

Simpan `worker-identity.json` secara pribadi. Identitas ini terikat ke satu origin Gate dan satu instalasi server. Jangan menjalankan salinan DATA_DIR worker yang sama pada beberapa server sekaligus. Daftarkan server baru bila pemasangan perlu diganti.

## Pemeriksaan sebelum membuka layanan

Periksa pairing, pemilihan server, deploy satu bot percobaan, status aktif pada bot induk, pencabutan izin, dan pemulihan setelah putus koneksi. Uji pembayaran nyata dilakukan pemilik setelah alur kontrol ini terverifikasi. Tes otomatis menggunakan database sementara dan objek Telegram tiruan.

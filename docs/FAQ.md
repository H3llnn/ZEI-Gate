# Pertanyaan umum

### Apa beda bot induk dan bot anak?

Bot induk menjadi pusat izin dan pembuatan layanan. Bot anak ForceSubs atau Payment menjalankan layanan milik masing-masing pengguna. Userbot berjalan melalui akun Telegram pribadi, bukan identitas bot anak.

### Siapa yang boleh membuat layanan?

Pengguna yang diberi izin oleh pemilik bot induk. Izin Userbot, Payment, dan ForceSubs bisa diaktifkan atau dicabut secara terpisah. Pencabutan menghentikan layanan terkait; setelah izin dipulihkan, pengguna perlu deploy atau menghubungkan ulang.

### Mini App dibuka di mana?

Dari tombol ruang pembuatan di bot induk. Tampilannya berada di Telegram, sementara halamannya dilayani server melalui HTTPS. Membuka alamatnya langsung di browser tidak menggantikan autentikasi Telegram.

### Harus memakai Cloudflare?

Tidak. Yang diperlukan Mini App adalah alamat HTTPS yang mengarah ke server. Domain dengan reverse proxy dapat digunakan. Tunnel sementara berguna untuk percobaan di laptop dan alamatnya dapat berubah.

### Payment memerlukan webhook atau stream key?

Mode Payment sederhana di proyek ini dikonfigurasi melalui username Saweria di pengaturan bot anak. Mode tersebut tidak memerlukan webhook, stream key, atau PAYMENT_PUBLIC_BASE. HTTPS Mini App merupakan kebutuhan terpisah. Integrasi tetap bergantung pada ketersediaan layanan pembayaran.

### Bagaimana akses gabungan bekerja?

Pemilik menggabungkan minimal dua tujuan akses dan menentukan harga gabungan. Setelah pembayaran terverifikasi, pembeli mendapat link untuk masing-masing tujuan. Setiap link sekali pakai dan dicabut setelah digunakan. Perubahan harga atau isi berikutnya tidak mengubah isi pesanan yang sudah dibuat.

### Mengapa tombol bantuan Userbot tidak muncul?

Aktifkan mode inline bot induk melalui `/setinline` di BotFather. Ketik `.help` dari akun pemilik yang sudah terhubung dan berizin. Bila prefix diganti, gunakan prefix yang baru. Bantuan teks menjadi cadangan ketika inline tidak tersedia.

### Apakah laptop boleh dimatikan?

Jika proses berjalan di laptop, layanan ikut berhenti saat laptop mati atau tidur. Jika proses sudah dipasang dan berjalan di hosting, laptop tidak perlu tetap menyala.

### Berapa bot yang bisa dijalankan?

Kapasitas tergantung RAM, jumlah proses, ukuran media, dan aktivitas pengguna. Tidak ada angka kapasitas yang sudah dibuktikan lewat uji beban proyek ini. Mulai dari sedikit layanan dan pantau penggunaan sumber daya hosting.

### Data apa yang perlu dicadangkan?

`config.env` dan seluruh direktori yang ditunjuk `DATA_DIR`, termasuk kunci `SECRET_KEY` yang sesuai. Simpan secara privat. Jangan unggah konfigurasi, database, sesi, atau cadangan ke repository publik. Lihat [panduan pembaruan](UPDATE-GUIDE.md).

### Apakah semua fitur sudah diuji langsung?

Tes otomatis menggunakan objek Telegram dan pembayaran tiruan. Hasilnya tidak menggantikan uji login, pembayaran, pengiriman link, dan bergabung dengan akun nyata. Batas pemeriksaan dicatat di [status proyek](STATUS.md).

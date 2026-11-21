# Menambahkan server klien

1. Pada bot induk, buka **Kelola Server → Tambah Server** dan beri nama.
2. Unduh `install_worker.py` dari tombol **Unduh Pemasang Worker**.
3. Pada hosting Python 3.12 atau lebih baru, unggah file tersebut di folder utama.
4. Buat `config.env` menggunakan konfigurasi yang diberikan bot induk. Kode pemasangan berlaku 10 menit; buat kode baru jika diperlukan.
5. Atur file startup menjadi `install_worker.py`, lalu tekan **Start**. Pemasang mengunduh Gate dan pasangan versi ForceSubs, Payment, serta Userbot secara otomatis.
6. Setelah server terhubung, pilih **Daftar Pengguna → nama klien → Server** dan pilih server tersebut, lalu beri izin layanan yang sesuai.

Tidak perlu mengunggah empat repo atau memasukkan versi runtime secara manual. Biarkan startup menggunakan `install_worker.py`; setelah pemasangan pertama, restart langsung menjalankan Worker yang sudah terpasang tanpa mengunduh ulang.

Pemasang mengambil commit Gate `main` saat pemasangan dimulai dan menggunakan `runtime-versions.json` dari commit yang sama. Server yang sudah berjalan tidak diperbarui otomatis pada setiap restart. Pemasang menolak pemasangan baru jika folder data sudah berisi data tanpa penanda pemasangan, supaya tidak menimpa instalasi lama.

Perpindahan bot yang sudah ada tetap memerlukan migrasi data. Simpan `config.env` dan seluruh folder `data` sebagai cadangan privat, termasuk identitas Worker dan kunci enkripsinya.

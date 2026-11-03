# Empat repo, satu pusat kendali

| Repo | Pemilik kode | Paket Python |
| :--- | :--- | :--- |
| [ZEI-Gate](https://github.com/H3llnn/ZEI-Gate) | Bot induk, izin, database, API Telegram, UI bersama, Mini App, supervisor | `subgate` |
| [ZEI-ForceSubs](https://github.com/H3llnn/ZEI-ForceSubs) | Pengaturan ForceSubs, link, batch, pengiriman dan penghapusan konten | `zei_forcesubs` |
| [ZEI-Payment](https://github.com/H3llnn/ZEI-Payment) | Checkout QRIS, pesanan, akses gabungan, undangan dan webhook opsional | `zei_payment` |
| [ZEI-Userbot](https://github.com/H3llnn/ZEI-Userbot) | Runtime akun pribadi dan perintah | `zei_userbot` |

Pemisahan repo tidak menambah bot induk atau server. ForceSubs dan Payment tetap berjalan dari proses Gate seperti sebelumnya. Keduanya memakai objek Store dan API Telegram yang diberikan Gate; runtime bukan aplikasi mandiri. Payment menggunakan Delivery ForceSubs untuk kompatibilitas link konten lama.

## Instalasi folder

```text
ZEI-Project/
  ZEI-Gate/
  ZEI-ForceSubs/
  ZEI-Payment/
  ZEI-Userbot/
```

Jalankan `python install.py` dari Gate. Installer memasang ketiga paket runtime ke virtual environment Gate. Data tetap disimpan satu kali pada `DATA_DIR` Gate; tidak perlu memindahkan atau membagi database. Pertahankan `SECRET_KEY` dan konfigurasi lama saat update.

Untuk panel hosting tanpa installer, paket distribusi hosting memuat `subgate`, `zei_forcesubs`, `zei_payment`, dan `zei_userbot` berdampingan dengan `main.py`. Jangan mengunggah ZIP sumber Gate saja tanpa runtime lainnya.

## Kompatibilitas

Modul `subgate.child_ui`, `subgate.service`, `subgate.payment_ui`, `subgate.payment_service`, `subgate.payment_store`, `subgate.payment_webhook`, dan `subgate.saweria` tetap tersedia sebagai alias modul runtime yang sama. Kode layanan hanya memiliki satu implementasi. Tidak ada migrasi skema tambahan akibat pemisahan ini.

Runtime ForceSubs dan Payment versi awal `0.1.0` dirilis bersama perubahan Gate ini. Gunakan commit runtime yang dipin oleh rilis Gate untuk deployment yang bisa diulang. Tes integrasi tetap berada di Gate karena membutuhkan Store, supervisor, dan kedua runtime; setiap repo runtime menjalankan suite Gate dalam CI.

## Update dan rollback

Cadangkan konfigurasi serta data saat proses berhenti sebelum memasang versi baru. Pengembangan dan pengujian tidak mengubah hosting aktif. Untuk kembali, gunakan sumber dan lingkungan dependensi dari versi sebelum pemisahan. Data tidak perlu dikonversi karena schema dan kunci tidak berubah.

Lihat juga [update dan cadangan](UPDATE-GUIDE.md). Login Telegram, pembayaran nyata, dan pengiriman undangan di hosting tetap memerlukan uji langsung setelah deployment.

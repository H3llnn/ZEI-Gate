# Pemisahan runtime ZΞI

**Tujuan:** empat repo sumber dengan satu bot induk dan perilaku layanan tetap sama.

**Batas:** tanpa perubahan skema database, kunci, token, izin, caption, atau aturan transaksi. Hosting aktif tetap memakai versi lama sampai pemasangan baru diverifikasi.

**Arsitektur:** Gate memiliki Store, Telegram API, UI bersama, supervisor, dan Mini App. `zei_forcesubs` memiliki ChildUI dan Delivery. `zei_payment` memiliki PaymentUI, PaymentStore, PaymentService, webhook, dan Saweria. Keduanya adalah paket runtime untuk Gate, bukan aplikasi yang memerlukan bot induk baru. Impor `subgate.*` lama menjadi alias modul yang sama untuk menjaga identitas exception dan monkeypatch integrasi. Database tetap satu milik Gate; runtime menerima objek Store yang sama.

**Alternatif:** menyalin seluruh Gate ke tiap repo membuat izin dan database berpotensi berbeda; membuat layanan HTTP baru menambah protokol dan proses. Pemisahan paket Python mempertahankan arsitektur yang sudah berjalan dengan perubahan paling kecil.

- [ ] Jalankan 153 tes Gate sebelum perubahan; simpan salinan sumber nonprivat sebelum pemindahan.
- [ ] Tambahkan tes identitas modul/exception, pemilihan runner kedua layanan, dan kepemilikan sumber. Jalankan untuk membuktikan gagal sebelum pemindahan.
- [ ] Pindahkan tujuh modul layanan ke dua paket; ubah hanya impor dan tambahkan alias kompatibilitas Gate.
- [ ] Sesuaikan installer empat folder, CI, Docker dengan commit runtime yang dipin, dan dokumentasi tiap repo; pertahankan lisensi/atribusi.
- [ ] Ulangi seluruh tes Gate/Userbot dan uji paket terpasang tanpa folder sumber runtime pada sys.path.
- [ ] Publikasikan repo runtime dahulu, baru Gate yang merujuk commit tersebut. Buat paket sumber dan hosting tanpa konfigurasi pribadi.

**Verifikasi:** API TelegramFailure tetap satu kelas; patch impor lama mengenai modul baru yang sama; Payment tetap bisa melayani link ForceSubs lama; cleanup dan pencabutan tetap diuji suite yang sama. Tes otomatis tidak melakukan transaksi atau login nyata.

**Rollback:** sumber lama dicadangkan sebelum pemindahan. Pemisahan tidak menyentuh data; gunakan kembali sumber lama beserta lingkungan dependensinya. Untuk pemulihan instalasi aktif, hentikan proses dahulu dan pertahankan konfigurasi serta data yang sesuai.

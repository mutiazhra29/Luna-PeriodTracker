# Luna

Luna adalah aplikasi desktop pencatat siklus menstruasi yang bekerja offline.
Catatan disimpan di folder `LunaData` di samping source aplikasi atau file
`Luna.exe`; aplikasi tidak membuat akun, mengirim telemetri, atau memerlukan
koneksi internet.

## Menjalankan

Gunakan Python 3.11+ pada Windows:

```powershell
python main.py
```

UI menggunakan Tkinter yang disertakan bersama Python. Tidak ada dependensi
runtime pihak ketiga.

## Fitur

- Onboarding tiga langkah, profil, pengaturan tema dan awal minggu.
- Beranda dengan fase siklus, perkiraan haid/ovulasi/masa subur, dan tindakan
  cepat mulai/selesai haid.
- Kalender bulanan interaktif dan catatan harian untuk aliran, gejala, mood,
  teks, suhu, berat badan, dan air; perubahan tersimpan otomatis.
- Ringkasan statistik, grafik panjang siklus, dan ekspor CSV.
- PIN empat digit yang disimpan sebagai hash scrypt; mode samaran.
- Backup/pemulihan database SQLite dan backup otomatis mingguan.
- Semua prediksi berlabel perkiraan dan disertai disclaimer medis.

Prediksi menggunakan panjang siklus terukur yang valid (15–60 hari), hingga
enam siklus terakhir; bila belum tersedia dua panjang siklus, digunakan nilai
default profil. Variasi besar ditampilkan sebagai rentang ketidakpastian.

## Pengujian

```powershell
python -m unittest discover -v
```

## Membuat executable portabel Windows

Pasang PyInstaller hanya pada mesin build:

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Luna main.py
```

Executable dibuat di `dist\Luna.exe`. Jalankan dari folder yang dapat ditulis
agar Luna dapat membuat `LunaData\luna.db` dan `LunaData\backup\` di sampingnya.
Salin folder `LunaData` bersama executable saat memindahkan perangkat/data.

## Catatan cakupan

PDF, enkripsi database, bahasa Inggris, serta toast Windows native belum
termasuk rilis MVP ini. PIN mengunci layar aplikasi, tetapi tidak mengenkripsi
file database; lindungi folder data dan cadangan sesuai kebutuhan privasimu.
Luna bukan alat medis maupun metode kontrasepsi.
# Luna-PeriodTracker

# SOP SURVEY WI-FI
## Kelompok 2 — Gedung F Lantai 3

### Mata Kuliah
Jaringan Nirkabel

### Fokus Survey
Wi-Fi 5 GHz — SSID `WiFi-UB.x`

### Tanggal Survey
9 Oktober 2026

### Waktu Target
± 09.00 WIB

---

# 1. IDENTITAS KELOMPOK

| Keterangan | Detail |
|---|---|
| Kelompok | Kelompok 2 |
| Gedung | Gedung F |
| Lantai | Lantai 3 |
| Jumlah titik | 34 titik |
| Titik | L3-001 s.d. L3-034 |
| Survey utama | Passive Survey |
| Survey lanjutan | Active Survey |
| SSID target | `WiFi-UB.x` |

---

# 2. TUJUAN SURVEY

Survey dilakukan untuk memperoleh data kondisi jaringan Wi-Fi 5 GHz pada Gedung F Lantai 3.

Data yang dikumpulkan digunakan untuk:

1. Mengukur kekuatan sinyal Wi-Fi (`RSSI`) pada setiap titik.
2. Mengidentifikasi area dengan kualitas sinyal rendah.
3. Mengamati AP/BSSID dan kanal Wi-Fi yang terdeteksi.
4. Membandingkan kondisi sinyal dengan kondisi lingkungan pada setiap titik.
5. Menentukan titik yang akan digunakan untuk active survey.
6. Menyediakan dataset mentah untuk proses analisis dan pembuatan peta kualitas Wi-Fi.

---

# 3. PEMBAGIAN AREA SURVEY

Pembagian area mengikuti denah Lantai 3 Gedung F yang digunakan oleh kelompok.

## 3.1 Interior

Area Interior ditandai dengan kotak biru pada denah.

### Anggota

- **Taqiya — Scanner**
- **Zhafif — Observer**

### Titik

L3-001 dan L3-012 s.d. L3-034.

Jumlah: **24 titik**

---

## 3.2 Exterior

Area Exterior ditandai dengan kotak merah pada denah.

### Anggota

- **Maulana — Scanner**
- **Fikri — Observer**

### Titik

L3-002 s.d. L3-011.

Jumlah: **10 titik**

---

# 4. PEMBAGIAN TUGAS

## 4.1 Scanner

Scanner bertanggung jawab untuk:

1. Membawa dan mengoperasikan laptop.
2. Menjalankan `scan_point.py`.
3. Melakukan **3 scan pada setiap titik**.
4. Memastikan posisi laptop sesuai prosedur.
5. Memastikan command menggunakan `--ssid "WiFi-UB.x"`.
6. Menyimpan hasil scan ke CSV milik scanner.
7. Tidak mengubah isi CSV hasil scan secara manual.

### Scanner

| Nama | Area | File |
|---|---|---|
| Taqiya | Interior | `data/passive_L3_Taqiya.csv` |
| Maulana | Exterior | `data/passive_L3_Maulana.csv` |

---

## 4.2 Observer

Observer bertanggung jawab untuk:

1. Mengoperasikan WiFiAnalyzer.
2. Mengambil screenshot WiFiAnalyzer pada setiap titik.
3. Menggunakan tab **Access Points** dengan filter **5 GHz**.
4. Mencatat kondisi lingkungan.
5. Mencatat perkiraan jumlah orang.
6. Mencatat kondisi pintu terbuka/tertutup.
7. Memastikan scanner berada pada titik yang benar.
8. Membantu memastikan urutan titik tidak terlewat.

### Observer

| Nama | Area | Tugas |
|---|---|---|
| Zhafif | Interior | WiFiAnalyzer + kondisi lingkungan |
| Fikri | Exterior | WiFiAnalyzer + kondisi lingkungan |

---

# 5. PERALATAN

## 5.1 Laptop

Minimal satu laptop untuk masing-masing tim zona.

Laptop digunakan untuk menjalankan:

- `scan_point.py`
- `active_point.py` jika mendapat tugas active survey.

Laptop harus mendukung Wi-Fi 5 GHz.

## 5.2 Smartphone

Observer menggunakan Android dengan aplikasi:

**WiFiAnalyzer**

WiFiAnalyzer digunakan sebagai validasi/pembanding visual terhadap hasil passive scan laptop.

Screenshot menggunakan:

- Tab: `Access Points`
- Filter: `5 GHz`

---

# 7. PERSIAPAN SEBELUM SURVEY

Pastikan:

- [ ] Laptop scanner menyala dan Wi-Fi aktif.
- [ ] Laptop dapat mendeteksi jaringan 5 GHz.
- [ ] Python dapat dijalankan.
- [ ] Script tersedia.
- [ ] WiFiAnalyzer sudah terpasang.
- [ ] Observer dapat melakukan scan 5 GHz.
- [ ] Denah dan daftar titik tersedia.
- [ ] Folder output sudah dibuat.
- [ ] Nama file CSV sudah disepakati.

Untuk Windows 11 24H2 atau lebih baru, izin **Location** untuk desktop apps harus aktif agar hasil scan Wi-Fi dapat diperoleh.

---

# 8. UJI SEBELUM SURVEY

Sebelum survey lapangan, lakukan uji menggunakan:

```bat
python scan_point.py --titik UJI --slot T0 --device laptopA --out uji.csv --n 1 --ssid "WiFi-UB.x"
```

Uji dinyatakan berhasil apabila program dapat:

1. Melakukan scan.
2. Mendeteksi BSSID.
3. Menampilkan jumlah jaringan 5 GHz.
4. Menampilkan RSSI `WiFi-UB.x` 5 GHz apabila terdeteksi.

---

# 9. PROSEDUR PASSIVE SURVEY

## 9.1 Prinsip

Setiap titik dilakukan **3 kali scan menggunakan satu laptop scanner**.

Observer tidak menjalankan `scan_point.py`, tetapi melakukan WiFiAnalyzer dan pencatatan kondisi lingkungan.

---

## 9.2 Posisi di Titik

Pada setiap titik:

1. Scanner dan observer berdiri tepat pada titik sesuai denah.
2. Laptop diposisikan sekitar **±1 meter** dari lantai.
3. Arah layar laptop dibuat konsisten.
4. Scanner tidak berdiri di antara laptop dan arah AP terdekat.
5. Observer berada di posisi yang tidak menghalangi laptop.
6. Kondisi lingkungan dicatat sesuai keadaan sebenarnya.

---

# 10. COMMAND PASSIVE SCAN

Format command:

```bat
python scan_point.py --titik <TITIK_ID> --slot T1 --device <NAMA_DEVICE> --out <FILE_OUTPUT> --n 3 --ssid "WiFi-UB.x"
```

## 10.1 Tim A — Taqiya

Contoh:

```bat
python scan_point.py --titik L3-001 --slot T1 --device laptop-taqiya --out data\passive_L3_Taqiya.csv --n 3 --ssid "WiFi-UB.x"
```

Untuk titik berikutnya, tetap gunakan file output yang sama dan ganti `TITIK_ID`.

Contoh:

```bat
python scan_point.py --titik L3-012 --slot T1 --device laptop-taqiya --out data\passive_L3_Taqiya.csv --n 3 --ssid "WiFi-UB.x"
```

---

## 10.2 Tim B — Maulana

Contoh:

```bat
python scan_point.py --titik L3-002 --slot T1 --device laptop-maulana --out data\passive_L3_Maulana.csv --n 3 --ssid "WiFi-UB.x"
```

Untuk titik berikutnya, tetap gunakan file output yang sama dan ganti `TITIK_ID`.

Contoh:

```bat
python scan_point.py --titik L3-003 --slot T1 --device laptop-maulana --out data\passive_L3_Maulana.csv --n 3 --ssid "WiFi-UB.x"
```

---

# 11. PROSEDUR DI SETIAP TITIK

## STEP 1 — Datang ke titik

Scanner dan observer menuju titik yang sama.

Contoh:

```text
L3-015
```

## STEP 2 — Persiapan posisi

### Scanner

- Posisikan laptop ±1 m dari lantai.
- Arah layar konsisten.
- Jangan menghalangi arah AP.

### Observer

- Siapkan WiFiAnalyzer.
- Pastikan berada pada titik yang sama.

## STEP 3 — Sinkronisasi

Gunakan aba-aba:

```text
3... 2... 1... klik!
```

Pada saat yang sama:

**Scanner**
→ menjalankan passive scan.

**Observer**
→ mengambil screenshot WiFiAnalyzer.

Tidak harus pada detik yang benar-benar sama, tetapi harus berada pada sesi pengukuran dan kondisi lingkungan yang sama.

## STEP 4 — Passive scan

Scanner menjalankan:

```bat
python scan_point.py --titik L3-015 --slot T1 --device laptop-taqiya --out data\passive_L3_Taqiya.csv --n 3 --ssid "WiFi-UB.x"
```

Program melakukan 3 scan.

## STEP 5 — Catat RSSI

Perhatikan output:

```text
WiFi-UB.x 5 GHz terkuat: ... dBm
```

RSSI terkuat SSID kampus tersebut dicatat pada sketsa di samping nomor titik.

## STEP 6 — WiFiAnalyzer

Observer mengambil screenshot:

```text
L3-015.png
```

Screenshot menggunakan:

```text
WiFiAnalyzer
→ Access Points
→ Filter 5 GHz
```

## STEP 7 — Kondisi lingkungan

Observer mencatat:

- Perkiraan jumlah orang.
- Pintu terbuka/tertutup.
- Kondisi kelas.
- Kondisi koridor.
- Kondisi khusus lainnya.

Contoh:

```text
Jumlah orang : ±18
Pintu         : terbuka
Kondisi       : koridor cukup ramai
Catatan       : banyak mahasiswa di depan kelas
```

Kondisi dicatat **sesuai keadaan sebenarnya**, bukan dibuat-buat.

## STEP 8 — Pindah

Pastikan:

```text
Passive scan ✓
RSSI dicatat ✓
WiFiAnalyzer ✓
Kondisi ✓
```

Kemudian lanjut ke titik berikutnya.

---

# 12. KALIBRASI

## 12.1 Ketentuan sumber

README dosen menetapkan titik kalibrasi sebagai:

```text
L3-000
```

dan meminta semua laptop melakukan **5 scan bersamaan**.

## 12.2 Penyesuaian Kelompok 2

Pada denah Kelompok 2, penomoran titik dimulai dari:

```text
L3-001
```

Oleh karena itu, kelompok menggunakan:

```text
L3-001
```

sebagai titik kalibrasi.

**Catatan:** penggunaan `L3-001` merupakan keputusan operasional Kelompok 2, bukan perubahan terhadap ketentuan asli README dosen.

### Pelaksanaan

- Taqiya menggunakan laptop scanner Tim A.
- Maulana menggunakan laptop scanner Tim B.
- Zhafif dan Fikri menggunakan WiFiAnalyzer.
- Semua pengukuran dilakukan pada titik dan kondisi yang sama.

### Jumlah scan

Kalibrasi:

```text
5 scan
```

Passive survey biasa:

```text
3 scan/titik
```

---

# 13. DATA YANG DIHASILKAN

`scan_point.py` menghasilkan data dengan kolom:

```text
timestamp
lantai
titik_id
x_px
y_px
slot_waktu
device
scan_ke
ssid
bssid
freq_mhz
channel
band
width_mhz
rssi_dbm
noise_dbm
sta_count
ch_util_pct
security
pmf
catatan
```

Data mentah harus dipertahankan dan tidak diedit secara manual.

---

# 14. ATURAN DATA PASSIVE

## 14.1 Satu file per scanner

Tim A:

```text
passive_L3_Taqiya.csv
```

Tim B:

```text
passive_L3_Maulana.csv
```

Satu file dapat berisi seluruh titik yang dikerjakan scanner tersebut.

## 14.2 Jangan membuat satu CSV untuk setiap titik

Jangan membuat:

```text
L3-001.csv
L3-002.csv
L3-003.csv
...
```

Gunakan satu CSV per scanner.

---

# 15. WIFIANALYZER

Observer menggunakan WiFiAnalyzer untuk validasi silang.

Pada setiap titik:

1. Buka WiFiAnalyzer.
2. Pilih `Access Points`.
3. Filter `5 GHz`.
4. Pastikan kondisi scan sesuai titik.
5. Ambil screenshot.
6. Simpan dengan nama titik.

Contoh:

```text
raw/android/
├── L3-001.png
├── L3-002.png
├── L3-003.png
└── ...
```

---

# 16. ACTIVE SURVEY

Active survey dilakukan setelah passive survey selesai dan RSSI seluruh titik telah diperoleh.

Pilih **6–8 titik** berdasarkan hasil passive survey:

### 3 titik RSSI terendah

- RSSI terendah.
- Atau `WiFi-UB.x` tidak terdeteksi.

### 2 titik RSSI terbaik

Digunakan sebagai titik pembanding.

### 1–3 titik suspicious

RSSI terlihat bagus tetapi terdapat indikasi masalah, misalnya:

- Area ramai.
- Banyak AP terdengar.
- Potensi interferensi/channel congestion.

## 16.1 Active test

Laptop dihubungkan ke:

```text
WiFi-UB.x
```

Kemudian jalankan:

```bat
python active_point.py --titik L3-017 --out data\active_L3.csv
```

Ganti `L3-017` dengan titik yang dipilih.

---

# 17. PEMBAGIAN ACTIVE SURVEY

Untuk menjaga beban kerja tetap seimbang:

**Tim B — Fikri + Maulana**

menangani active survey.

### Maulana

- Operator laptop.
- Menjalankan `active_point.py`.

### Fikri

- Mencatat hasil.
- Dokumentasi.
- Mencatat kondisi titik.

Pemilihan titik active tetap berdasarkan hasil passive seluruh 34 titik, bukan dibatasi hanya pada 10 titik Exterior.

---

# 18. GIT DAN PENGUMPULAN DATA

Setiap scanner menyimpan hasil pada branch masing-masing.

## Taqiya

```bash
git switch -c survey/Taqiya
git add data/passive_L3_Taqiya.csv
git commit -m "data: passive survey Taqiya"
git push -u origin survey/Taqiya
```

## Fikri

```bash
git switch -c survey/Fikri
git add data/passive_L3_Maulana.csv
git commit -m "data: passive survey Fikri"
git push -u origin survey/Fikri
```

Observer mengunggah screenshot dan catatan sesuai pembagian folder yang telah disepakati.

---

# 19. MERGE DATA

Setelah survey selesai:

```text
passive_L3_Taqiya.csv
          +
passive_L3_Maulana.csv
          ↓
    passive_L3.csv
```

Merge berarti **menggabungkan data mentah**, bukan mengubah nilai RSSI.

Data asli tetap disimpan:

```text
passive_L3_Taqiya.csv
passive_L3_Maulana.csv
```

Jangan menghapus raw data setelah merge.

---

# 20. CHECKLIST TIM A

## Taqiya — Scanner

- [ ] Laptop siap.
- [ ] `scan_point.py` berjalan.
- [ ] Wi-Fi 5 GHz terdeteksi.
- [ ] Output `passive_L3_Taqiya.csv` tersedia.
- [ ] L3-001 selesai.
- [ ] L3-012 selesai.
- [ ] L3-013 selesai.
- [ ] L3-014 selesai.
- [ ] L3-015 selesai.
- [ ] L3-016 selesai.
- [ ] L3-017 selesai.
- [ ] L3-018 selesai.
- [ ] L3-019 selesai.
- [ ] L3-020 selesai.
- [ ] L3-021 selesai.
- [ ] L3-022 selesai.
- [ ] L3-023 selesai.
- [ ] L3-024 selesai.
- [ ] L3-025 selesai.
- [ ] L3-026 selesai.
- [ ] L3-027 selesai.
- [ ] L3-028 selesai.
- [ ] L3-029 selesai.
- [ ] L3-030 selesai.
- [ ] L3-031 selesai.
- [ ] L3-032 selesai.
- [ ] L3-033 selesai.
- [ ] L3-034 selesai.

## Zhafif — Observer

- [ ] WiFiAnalyzer siap.
- [ ] Filter 5 GHz.
- [ ] Screenshot setiap titik.
- [ ] Jumlah orang dicatat.
- [ ] Kondisi pintu dicatat.
- [ ] Kondisi lingkungan dicatat.

---

# 21. CHECKLIST TIM B

## Maulana — Scanner

- [ ] Laptop siap.
- [ ] `scan_point.py` berjalan.
- [ ] Wi-Fi 5 GHz terdeteksi.
- [ ] Output `passive_L3_Maulana.csv` tersedia.
- [ ] L3-002 selesai.
- [ ] L3-003 selesai.
- [ ] L3-004 selesai.
- [ ] L3-005 selesai.
- [ ] L3-006 selesai.
- [ ] L3-007 selesai.
- [ ] L3-008 selesai.
- [ ] L3-009 selesai.
- [ ] L3-010 selesai.
- [ ] L3-011 selesai.

## Fikri — Observer

- [ ] WiFiAnalyzer siap.
- [ ] Filter 5 GHz.
- [ ] Screenshot setiap titik.
- [ ] Jumlah orang dicatat.
- [ ] Kondisi pintu dicatat.
- [ ] Kondisi lingkungan dicatat.
- [ ] Membantu active survey.

---

# 22. CHECKLIST AKHIR PASSIVE SURVEY

Sebelum meninggalkan lantai:

- [ ] Semua 34 titik telah disurvei.
- [ ] Setiap titik memiliki 3 scan.
- [ ] RSSI `WiFi-UB.x` telah dicatat.
- [ ] Screenshot WiFiAnalyzer tersedia.
- [ ] Kondisi lingkungan tersedia.
- [ ] `passive_L3_Taqiya.csv` tersimpan.
- [ ] `passive_L3_Maulana.csv` tersimpan.
- [ ] Tidak ada file CSV yang rusak.
- [ ] Data telah dibackup.
- [ ] Data belum diubah secara manual.

---

# 23. ETIKA DAN KEAMANAN

Survey dilakukan secara pasif dan active test hanya dilakukan pada jaringan yang memang berhak digunakan.

Dilarang melakukan:

- Deauthentication.
- Jamming.
- Rogue AP / evil twin.
- Cracking.
- Packet capture terhadap traffic pengguna lain.
- Flooding.

---

# 24. ALUR UTAMA SURVEY

```text
1 titik
   ↓
1 scanner + 1 observer
   ↓
3 passive scan
   ↓
RSSI dicatat
   ↓
WiFiAnalyzer screenshot
   ↓
Kondisi lingkungan dicatat
   ↓
Data disimpan
   ↓
Titik berikutnya
```

Hasil passive survey:

```text
34 titik
×
3 scan
×
1 scanner pada masing-masing zona
```

Data tetap mempertahankan identitas:

```text
titik_id
device
scan_ke
BSSID
RSSI
channel
frequency
dan parameter lainnya
```

Data tersebut kemudian digunakan untuk menentukan titik active survey dan proses analisis berikutnya.

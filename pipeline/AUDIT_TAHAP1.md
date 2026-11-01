# Audit Kelayakan Data (Tahap 1): Pilot ScrapeCreators

Penelitian: *Politik Islam dalam Ekosistem Digital* (PKS, PKB, PPP, PAN; Instagram, TikTok, YouTube, X)
Tanggal pilot: 1 November 2026 (WIB) · Kredit terpakai: 11 (7.100 → 7.089) · Pelaksana: Claude, via konektor ScrapeCreators

Dokumen ini hanya memuat hal yang teramati langsung dalam pilot atau tertulis di deskripsi endpoint.
Belum ada data penelitian yang dikumpulkan dan belum ada temuan substantif.

## 1. Ringkasan keputusan

| Platform | Kelayakan untuk SNA | Alasan utama |
|---|---|---|
| Instagram | **Layak, dengan catatan** | Komentar memuat ID dan username pengguna serta timestamp presisi. Balasan (edge reply) mahal: 15 kredit/halaman. |
| YouTube | **Layak, volume kecil** | Kanal resmi PKS berkomentar sedikit (±276 komentar untuk 30 video). Tanggal komentar berupa perkiraan. |
| TikTok | **Belum teruji** | Akun kandidat ditemukan. Struktur komentar belum diuji pada respons nyata. |
| X | **Tidak layak lewat endpoint ini** | Hanya ±100 tweet *populer* (bukan kronologis), tanpa relasi reply/repost. Butuh API resmi atau dataset arsip yang sah (sesuai protokol V.D). |

## 2. Verifikasi akun seed

| Partai | Platform | Handle | Status | Dasar |
|---|---|---|---|---|
| PKS | X | @PKSejahtera | verified | Profil: "DPP PKS", centang verifikasi, 483.277 pengikut. Disebut sebagai akun resmi dalam laporan Netray (Jan 2024). |
| PKS | Instagram | @pk_sejahtera | verified | Disebut sebagai akun resmi di beberapa artikel jurnal. Owner ID 690269097. |
| PKS | TikTok | @pksejahtera | verified | Nickname "Partai Keadilan Sejahtera", 114.206 pengikut. Ditautkan dari pks.id. |
| PKS | YouTube | @pkstvindonesia (PKSTV) | verified | Badge Verified, ±300 ribu subscriber. pks.id menautkan youtube.com/PKSTVIndonesia. |
| PKS | Telegram | PK_Sejahtera | (tambahan) | Ditautkan dari pks.id. Belum didukung pipeline. |
| PAN | X, IG, TikTok, YouTube | @Official_PAN, @amanatnasional, @amanat_nasional, PAN TV (@pantv12) | verified | Diberikan peneliti. Kanal PAN TV ("dikelola Media Center PAN") menautkan X dan IG yang sama. TikTok bercentang verifikasi; X dan YouTube tanpa badge. |
| PKB | X, IG, TikTok, YouTube | @DPP_PKB, @dpp_pkb (IG/TikTok/YouTube) | verified | Diberikan peneliti dan ditautkan dari pkb.id. X, TikTok, dan YouTube bercentang verifikasi (cek 1 Nov 2026). |
| PPP | X, IG, TikTok | @DPP_PPP, @dpp.ppp (IG/TikTok) | verified | Diberikan peneliti. Bio X: "Twitter Resmi Partai Persatuan Pembangunan". TikTok tanpa badge. IG belum dicek via API. |
| PPP | YouTube | Petiga TV (UC5Y2Be3lI78Y7lwajocg9og) | verified* | *Tanpa badge. Menyebut diri kanal resmi DPP PPP tetapi **dikelola tim Kaukus Muda PPP**, sehingga tidak setara langsung dengan kanal humas DPP partai lain. |

**Seed lengkap:** keempat partai sudah terverifikasi di 4 platform (1 Nov 2026).

**Ketimpangan audiens (cek profil 1 Nov 2026):**

| Partai | X | TikTok | YouTube |
|---|---|---|---|
| PKS | 483.277 | 114.206 | ±300 rb |
| PKB | 164.539 | 115.767 | 41,7 rb |
| PPP | 50.744 | 86.620 | 33 rb |
| PAN | 77.223 | 1.020.533 | 85,3 rb |

Akibatnya, tanpa pembatasan, jaringan komentar TikTok akan didominasi PAN dan jaringan X didominasi PKS.
Pipeline sudah membatasi jumlah post dan halaman komentar **per akun** secara seragam. Meski begitu, laporkan metrik jaringan
per partai (bukan hanya gabungan) dan nyatakan bahwa jumlah pengikut tidak sama dengan pengaruh (protokol X). Pengumpulan data **belum boleh dimulai**
sebelum keempat partai punya seed setara. Kalau tidak, perbandingan antarpartai bias sejak tahap sampling.
Langkah selanjutnya: isi handle di `config.yaml`, jalankan `python sc_pipeline.py verify`, lalu putuskan status secara manual.

## 3. Temuan per platform (teramati di pilot)

**Instagram**
- `user/posts`: 12 post per halaman, 1 kredit. Rentang tanggal 12 post terbaru: 19 Okt–1 Nov 2026.
- **7 dari 12 post di feed @pk_sejahtera dimiliki akun lain** (post kolaborasi, misalnya akun DPW dan akun Presiden PKS).
  Pipeline menandainya dengan kolom `owned_by_seed`. Perlu keputusan eksplisit apakah post kolaborasi diikutkan.
- `post/comments`: 1 halaman = 8 komentar = 1 kredit (satu sampel; ukuran halaman bisa berbeda). Field tersedia: ID komentar,
  teks, jumlah like, timestamp ISO, ID dan username pengguna. `child_comment_count` bernilai null.
- Post dengan 552 komentar akan butuh puluhan halaman bila ukuran halaman tetap sekecil itu. Ini perlu diukur ulang sebelum anggaran ditetapkan.
- Balasan (`include_replies`) = 15 kredit per halaman, dan menurut dokumentasi tingkat keberhasilannya ±90%.
- **Pencarian profil tercemar:** kueri "Partai Keadilan Sejahtera" dan "Partai Persatuan Pembangunan" juga mengembalikan
  akun partai lain (misalnya media internal Golkar, akun pengurus NasDem dan Gerindra). Pencarian kata kunci tidak bisa dipakai sebagai sampling tanpa penyaringan manual.

**YouTube (PKSTV)**
- `channel-videos`: 30 video per halaman, 1 kredit. Video terbit 31 Agu–29 Okt 2026.
- Jumlah komentar per video kecil: total ±276 komentar untuk 26 video yang punya angka komentar (4 video null), maksimum 87.
- `publishedTime` video tampak diturunkan dari label relatif (banyak video punya jam identik 15:53:22.750Z), sedangkan
  `publishDate` presisi. Pipeline memakai `publishDate`.
- Menurut dokumentasi, tanggal komentar adalah perkiraan dari label relatif. Pipeline menandainya `date_precision = approx_relative`.
  Implikasinya, analisis temporal harian pada komentar YouTube tidak valid. Gunakan agregasi mingguan atau bulanan.

**TikTok**
- Pencarian pengguna "PKS Partai Keadilan Sejahtera" didominasi akun yang tidak relevan, termasuk akun partai Malaysia (PKR).
- Struktur respons `profile/videos` dan `video/comments` di pipeline disusun dari deskripsi endpoint dan **belum diuji pada respons nyata**.

**X**
- `user-tweets`: 101 tweet dalam 1 kredit, tetapi rentang tanggalnya 12 Apr 2019–22 Okt 2026 dan tidak kronologis
  (deskripsi endpoint: ±100 tweet paling populer). Dari 101 tweet: 0 reply, 0 retweet, 8 mention.
- Endpoint pencarian berbasis indeks Google, tidak lengkap, dan tidak memuat repost.
- Kesimpulan: kebutuhan protokol V.D (post, mention, reply, repost, timestamp) **tidak bisa dipenuhi** lewat ScrapeCreators.

## 4. Kesesuaian dengan protokol

- **V (prioritas open-source):** ScrapeCreators adalah layanan komersial pihak ketiga, bukan API resmi platform.
  Hal ini wajib dilaporkan di bagian metode beserta biayanya, dan reviewer jurnal Q1 bisa mempertanyakan kepatuhannya terhadap ToS platform.
  Untuk YouTube, YouTube Data API v3 (resmi, gratis dengan kuota) lebih kuat secara metodologis dan memberi timestamp komentar yang presisi.
- **V.F.3 (tanpa bypass proteksi):** pipeline tidak melakukan bypass. Catatan: mode *stealth* Scrapling dipasarkan untuk
  melewati proteksi anti-bot. Karena itu Scrapling tidak dipakai, karena bertentangan dengan butir ini. (Klaim fitur Scrapling perlu diverifikasi di dokumentasinya.)
- **V.F.5 (anonimisasi):** akun non-institusional dipseudonimkan dengan HMAC-SHA256 dan salt rahasia. Akun resmi partai,
  serta tokoh publik yang Anda masukkan ke `public_figures`, tetap bernama.
  Data mentah (`data/raw/`) **masih memuat username asli**, jadi simpan terenkripsi dan jangan dibagikan.
- **V.F.6–7 (log dan kegagalan):** setiap request tercatat di `data/collection_log.csv`. Kegagalan dirangkum di `audit_build.md`.
- **XIII (longitudinal):** jangkauan historis tiap endpoint terbatas (pagination feed, ±100 tweet). Jadwalkan pengambilan
  rutin sejak 2026 alih-alih berharap bisa menarik data mundur pada 2029.

## 5. Yang belum diverifikasi

1. Path endpoint bertanda `(cek)` di `config.yaml`. Base URL dan header `x-api-key` sudah terkonfirmasi.
2. Struktur respons komentar YouTube (dari contoh tutorial resmi) dan TikTok (dari deskripsi endpoint).
3. Ukuran halaman komentar Instagram secara umum. Pilot baru mengambil satu sampel.
4. Profil Instagram keempat partai belum dicek lewat API (dasar verifikasinya tautan silang dan informasi peneliti).

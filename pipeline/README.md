# Pipeline Data: Politik Islam dalam Ekosistem Digital

Tahap 2–3 protokol: skrip pengumpulan (ScrapeCreators API) → 4 tabel penelitian + jaringan + CSV untuk SNA Explorer.
Baca `AUDIT_TAHAP1.md` lebih dulu: berisi hasil pilot dan keterbatasan per platform.

## Instalasi (Windows / Python 3.10+)
```
pip install requests pyyaml pytest
python -m pytest -q tests          # uji offline dengan fixture, tidak memakai kredit
```

## Kunci rahasia (jangan disimpan di repo/config)
```
set SCRAPECREATORS_API_KEY=xxxxx      # PowerShell: $env:SCRAPECREATORS_API_KEY="xxxxx"
set ANON_SALT=string-acak-panjang     # simpan di password manager; salt beda = ID anonim beda
```

## Alur kerja
1. **Lengkapi seed** di `config.yaml` (handle akun resmi keempat partai).
2. `python sc_pipeline.py verify` → `data/processed/account_verification.csv`. Periksa nama, bio, dan pengikut,
   lalu ubah `status` menjadi `verified` hanya untuk akun yang sudah Anda konfirmasi.
3. Atur `period` dan `budget`. Mulai kecil (misalnya `max_credits_per_run: 100`) untuk mengukur biaya nyata per platform.
4. `python sc_pipeline.py collect` → respons mentah di `data/raw/<run_id>/`, log setiap request di `data/collection_log.csv`.
   Pipeline berhenti otomatis saat batas kredit tercapai.
5. `python sc_pipeline.py build` → `data/processed/`:

| File | Isi |
|---|---|
| `content_dataset.csv` | Tabel 1 (+ `seed_account`, `owned_by_seed` untuk post kolaborasi) |
| `comment_dataset.csv` | Tabel 2. Kolom sentimen/aspek/topik kosong, diisi di Tahap 5. `date_precision` menandai tanggal YouTube yang berupa perkiraan. |
| `network_dataset.csv` | Tabel 3. Edge berarah `comment` (komentator → pemilik konten), `reply` (pembalas → penulis induk), `mention`. Bobot = jumlah interaksi. |
| `account_dataset.csv` | Tabel 4. Afiliasi partai hanya diisi untuk akun seed resmi. |
| `sna_explorer.csv` | Siap untuk SNA Explorer: satu baris per interaksi, kolom `text` (teks komentar, bisa dimatikan lewat `sna_export_text`), `platform`, `party`. comment/reply → jaringan Reply; mention → jaringan Mention. |
| `audit_build.md` | Ringkasan jumlah, post kolaborasi, struktur tak dikenal, dan request gagal. |

## Catatan metodologis
- **Gelombang longitudinal:** jalankan collect secara berkala dengan `period` yang konsisten. Setiap run punya `run_id` sendiri,
  jadi `build --runs <id...>` bisa membangun dataset per gelombang.
- **Bias sampling:** data hanya mencakup audiens yang berinteraksi di akun seed, bukan populasi pengguna (protokol V.F.9).
- **X:** endpoint ScrapeCreators tidak memenuhi kebutuhan reply/repost. Gunakan API resmi X atau dataset arsip yang sah.
- **Data mentah memuat username asli.** Simpan terenkripsi, batasi akses, dan hapus sesuai rencana pengelolaan data/etik.

## Memuat data ke SNA Explorer
Kirim `data/processed/sna_explorer.csv` ke Claude untuk dipasang sebagai data bawaan (`data/default.csv`) di artifact,
atau unggah langsung lewat tombol **Unggah CSV** di aplikasi. Komentar duplikat antar-run dilewati otomatis.

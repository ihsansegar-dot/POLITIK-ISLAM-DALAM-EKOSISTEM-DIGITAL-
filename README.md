# Politik Islam dalam Ekosistem Digital

*Islamic Politics in the Digital Ecosystem: Social Network Analysis, Islamic Identity, and Political Mobilization Ahead of Indonesia's 2029 Election*

Objek: PKS, PKB, PPP, PAN · Platform: Instagram, TikTok, YouTube, X · Periode: 2026–2029

## Isi repositori
| Folder/berkas | Isi |
|---|---|
| `pipeline/` | Pengumpulan data via ScrapeCreators API → 4 tabel penelitian (content, comment, network, account), pseudonimisasi HMAC, log, audit. Lihat `pipeline/README.md` dan `pipeline/AUDIT_TAHAP1.md`. |
| `sna-explorer/` | Aplikasi web SNA (degree, betweenness, PageRank, Louvain, VOS mapping, ekspor GEXF). Buka `index.html` lewat server lokal (`python -m http.server`). Bila ada `sna-explorer/data/default.csv`, aplikasi memuatnya; bila tidak, memakai data sintetis. |
| `jalankan.ps1` | Menjalankan verify → collect → build di Windows. |

## Status (1 November 2026)
- Tahap 1 (audit kelayakan) selesai: lihat `pipeline/AUDIT_TAHAP1.md`.
- Akun resmi keempat partai di empat platform sudah terverifikasi (`pipeline/config.yaml`).
- Belum ada data penelitian yang dikumpulkan.

## Etika dan data
Data mentah dan hasil olahan **tidak** disimpan di repositori ini (lihat `.gitignore`), karena data mentah memuat username asli dan teks komentar.
Simpan `ANON_SALT` terpisah. Repositori publik hanya boleh memuat kode dan dokumentasi.

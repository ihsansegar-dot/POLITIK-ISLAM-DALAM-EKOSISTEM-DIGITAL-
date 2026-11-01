# Audit media online (run 2 Nov 2026, 01:43–03:34 WIB)

## Metode
| Sumber | Cakupan | Catatan |
|---|---|---|
| Indeks per tanggal (`indeks`) | Jan 2024 – Nov 2026 | liputan6 (news), detik (news), cnnindonesia (nasional), kompas (nasional); 138 hari sampel (4/bulan, berbenih 2029, bersarang); semua halaman per hari |
| Sitemap resmi (`sitemaps`) | ~2 minggu terakhir | hanya artikel terbaru |
| GDELT DOC (`discover`) | 3 bulan terakhir | arsip lebih lama tidak andal (uji: PKS 2024 = 0 / error); banyak respons error |
| Teks (`fetch`) | sampel 15/partai/bulan | 718/728 berhasil (98,6%) |

Dikeluarkan: tempo.co (sitemap dijaga tantangan Cloudflare, tidak dilewati), antaranews (tanpa sitemap), republika & kumparan (tanpa indeks tanggal yang terbaca).

## Hasil
- 1.129 artikel, 1.162 edge media→partai. Edge: PKB 468, PKS 292, PAN 215, PPP 187.
- Penyebut (judul menyebut partai / total artikel di hari sampel): kompas 2,9%, cnnindonesia 2,5%, liputan6 2,0%, detik 1,9% (lihat `media_cakupan.csv`).
- Pola waktu: 2024 dominan (pemilu, pilkada); lonjakan PAN Mei 2024, PKS Jun–Jul 2024, PKB Agt 2024 dan Jul 2026, PPP Jun & Sep 2025.

## Batasan
1. Edge = partai disebut di **judul**. Judul yang hanya menyebut tokoh (mis. "Cak Imin" tanpa "PKB") tidak tertangkap. Partai yang hanya muncul di badan berita dicatat di `parties_in_text` (96 artikel), tidak dijadikan edge.
2. Sampel 4 hari/bulan: hitungan bulanan rentan efek hari peristiwa (mis. 2024-08-25: 49 artikel). Gunakan proporsi + `media_cakupan.csv`, bukan hitungan mentah.
3. Hanya 4 media utama untuk arsip; outlet lain (jawapos, viva, jpnn, dll.) hanya dari GDELT/sitemap periode terbaru → tidak sebanding antarwaktu.
4. Graf media hampir bipartit lengkap (4 media utama menyebut keempat partai): metrik sentralitas kurang bermakna; analisis sebaiknya pada bobot dan tren.
5. Kanal: liputan6/detik = rubrik news; cnnindonesia/kompas = nasional. Bukan seluruh situs.
